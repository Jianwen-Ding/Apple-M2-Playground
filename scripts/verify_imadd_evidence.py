#!/usr/bin/env python3
"""Independent offline verification of stored imadd addend-C evidence.

Reads only retained evidence: reference/patched/stale blobs, patch.json
claims, record/summary JSON, readback buffers and child stdout logs.
Recomputes every hash, the wrapper SHA1, the exact container byte diff,
the full readback oracle (leading guards, active words, rounded inactive
padding, trailing guards, patterned control tail) and the child API event
sequence. No driver calls, no GPU, no decoder import, writes nothing.

The instruction layout below is an independent restricted transcription of
Mesa 25.3.6 agx_pack.c for this one pinned instruction site; it never
decodes arbitrary bytes. The pinned control blob is only accepted
byte-for-byte (SHA256), so any metadata change is refused first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

CONTROL_SHA256 = 'd0b99dace1de6eb2467c64ce872e8f5c02458d1edae0a3f74b9ed2c17cff0ba3'
WRAPPER_SIZE = 2572
WRAPPED_SHA1_SPAN = (48, 68)
DRIVER_ID = 26
UUID_HEX = '2313bd7c3909b8ad0f31883eab5c412e'
CODE_START, CODE_SIZE = 0x8bc, 336
MAIN_START, MAIN_SIZE, PREAMBLE_START = 0x80, 78, 0x100
TARGET = 0x96                      # native main-relative offset
TARGET_BLOB = CODE_START + TARGET  # 0x952
TARGET_SIZE = 8
OLD_INSTRUCTION = bytes.fromhex('9e09820659000000')
MULTIPLIER, XOR_LITERAL = 0x9e3779b9, 0x12345678
INCOMPATIBLE_SHADER_BINARY = 1000482000
# Independent field transcription for this one site (bit offset, width).
IMADD_BITS = {'opcode': (0, 6, 0x1e), 'const15': (15, 1, 0), 'S': (6, 1, None),
              'N': (27, 1, None), 'Dt': (7, 2, None), 'D': (9, 6, None), 'Dx': (60, 2, None),
              'A': (16, 6, None), 'Ax': (58, 2, None), 'At': (22, 4, None), 'As': (26, 1, None),
              'B': (28, 6, None), 'Bx': (56, 2, None), 'Bt': (34, 4, None), 'Bs': (38, 1, None),
              'C': (40, 6, None), 'Cx': (54, 2, None), 'Ct': (46, 4, None), 'Cs': (50, 1, None),
              's1': (39, 1, None), 's2': (52, 2, None)}
UNCOVERED_BITS = (51, 62, 63)      # must read zero on this pinned site
EXPECTED_FIELDS = {'S': 0, 'N': 0, 'Dt': 3, 'D': 4, 'At': 10, 'As': 1, 'A': 2,
                   'Bt': 6, 'Bs': 1, 'B': 16, 'Ct': 0, 'Cs': 0, 'C': 0, 's': 0}
ALLOWED_BITS = (0x3f << 40) | (0x3 << 54)   # immediate C low/high parts only
REFERENCE_CANDIDATES = (
    '/scratch/apple-m2-playground/vulkan-compute-runs/20261004T214520738226Z/index.bin',)
BASELINE_RUN = Path('/scratch/apple-m2-playground/vulkan-compute-runs/20261004T214520738226Z')


def read_blob(path):
    path = Path(path)
    if path.is_file():
        return path.read_bytes()
    return bytes.fromhex(Path(str(path) + '.hex').read_text())


def blob_exists(path):
    return path.is_file() or Path(str(path) + '.hex').is_file()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def wrapped_sha1(data):
    zeroed = bytearray(data)
    zeroed[WRAPPED_SHA1_SPAN[0]:WRAPPED_SHA1_SPAN[1]] = bytes(WRAPPED_SHA1_SPAN[1] - WRAPPED_SHA1_SPAN[0])
    return hashlib.sha1(zeroed).digest()


def check(name, ok, detail=''):
    return {'name': name, 'ok': bool(ok), 'detail': str(detail)}


def decode_site(number):
    """Decode the pinned imadd site from the transcribed bit layout."""
    def part(key):
        off, width, _ = IMADD_BITS[key]
        return (number >> off) & ((1 << width) - 1)
    fields = {'S': part('S'), 'N': part('N'), 'Dt': part('Dt'),
              'D': part('D') | (part('Dx') << 6), 'A': part('A') | (part('Ax') << 6),
              'At': part('At'), 'As': part('As'), 'B': part('B') | (part('Bx') << 6),
              'Bt': part('Bt'), 'Bs': part('Bs'), 'C': part('C') | (part('Cx') << 6),
              'Ct': part('Ct'), 'Cs': part('Cs'), 's': part('s1') | (part('s2') << 1)}
    opcode = part('opcode')
    covered = 0
    for off, width, _ in IMADD_BITS.values():
        covered |= ((1 << width) - 1) << off
    remainder = number & ~covered & ((1 << 64) - 1)
    return fields, opcode, part('const15'), remainder


def expected_instruction(addend):
    if not 0 <= addend <= 255:
        raise ValueError('addend out of 8-bit immediate range')
    number = int.from_bytes(OLD_INSTRUCTION, 'little')
    number |= (addend & 0x3f) << 40 | (addend >> 6) << 54
    return number.to_bytes(TARGET_SIZE, 'little')


def oracle(count, addend, control=False):
    """Independent host uint32 oracle for the full child buffer."""
    rounded = (count + 31) // 32 * 32
    words = [0xcdcdcdcd] * (8 + rounded + 8) + [0xa5a50000 + j for j in range(16)]
    if not control:
        for i in range(count):
            words[8 + i] = (((i * MULTIPLIER) + addend) & 0xffffffff) ^ XOR_LITERAL
    return words


def region(index, count):
    rounded = (count + 31) // 32 * 32
    if index < 8:
        return 'leading-guard'
    if index < 8 + count:
        return 'active'
    if index < 8 + rounded:
        return 'inactive-padding'
    if index < 16 + rounded:
        return 'trailing-guard'
    return 'control-tail'


def check_blob_wrapper(data, tag):
    checks = [check(f'{tag}.size', len(data) == WRAPPER_SIZE, f'{len(data)} bytes'),
              check(f'{tag}.magic', data[:16] == b'MesaVkShaderBin\0', data[:16].hex())]
    if len(data) < WRAPPER_SIZE:
        return checks + [check(f'{tag}.readable', False, 'truncated')]
    checks += [
        check(f'{tag}.driver_id', struct.unpack_from('<I', data, 16)[0] == DRIVER_ID,
              str(struct.unpack_from('<I', data, 16)[0])),
        check(f'{tag}.uuid', data[20:36].hex() == UUID_HEX, data[20:36].hex()),
        check(f'{tag}.version', struct.unpack_from('<I', data, 36)[0] == 0,
              str(struct.unpack_from('<I', data, 36)[0])),
        check(f'{tag}.size_field', struct.unpack_from('<Q', data, 40)[0] == len(data),
              str(struct.unpack_from('<Q', data, 40)[0])),
        check(f'{tag}.sha1', data[WRAPPED_SHA1_SPAN[0]:WRAPPED_SHA1_SPAN[1]] == wrapped_sha1(data),
              f'stored {data[48:68].hex()}')]
    return checks


def check_reference(data):
    """Pinned control blob: full hash first, then wrapper and site decode."""
    checks = [check('R.sha256', sha256(data) == CONTROL_SHA256, sha256(data))]
    checks += check_blob_wrapper(data, 'R')
    if sha256(data) != CONTROL_SHA256:
        return checks + [check('R.pinned_layout', False, 'refused: unrecognized control blob')]
    checks += [
        check('R.stage', data[0x48] == 5, str(data[0x48])),
        check('R.lengths', struct.unpack_from('<II', data, CODE_START - 8) == (CODE_SIZE, 0),
              str(struct.unpack_from('<II', data, CODE_START - 8))),
        check('R.agx_info', struct.unpack_from('<II', data, 0x419) == (5, CODE_SIZE),
              str(struct.unpack_from('<II', data, 0x419))),
        check('R.main_size', struct.unpack_from('<I', data, 0x83d)[0] == MAIN_SIZE,
              str(struct.unpack_from('<I', data, 0x83d)[0])),
        check('R.has_preamble', data[0x841] == 1, str(data[0x841])),
        check('R.entries', struct.unpack_from('<II', data, 0x845) == (PREAMBLE_START, MAIN_START),
              str(struct.unpack_from('<II', data, 0x845))),
        check('R.rodata', struct.unpack_from('<IHH', data, 0x879) == (0, 16, 4),
              str(struct.unpack_from('<IHH', data, 0x879))),
        check('R.instruction', data[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] == OLD_INSTRUCTION,
              data[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE].hex())]
    fields, opcode, const15, remainder = decode_site(int.from_bytes(
        data[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], 'little'))
    checks += [check('R.opcode', opcode == 0x1e, hex(opcode)),
               check('R.const15', const15 == 0, str(const15)),
               check('R.remainder', remainder == 0, hex(remainder)),
               check('R.uncovered_zero', all((int.from_bytes(data[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE],
                                                             'little') >> b) & 1 == 0 for b in UNCOVERED_BITS),
                     str(UNCOVERED_BITS)),
               check('R.fields', fields == EXPECTED_FIELDS, json.dumps(fields, sort_keys=True))]
    return checks


def check_patched(reference, patched, addend, tag='P'):
    """Byte diff, derived instruction, wrapper SHA1, everything else preserved."""
    checks = check_blob_wrapper(patched, tag)
    new = expected_instruction(addend)
    old_number = int.from_bytes(reference[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], 'little')
    new_number = int.from_bytes(patched[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], 'little')
    diff_bits = [b for b in range(64) if (old_number ^ new_number) >> b & 1]
    changed = [i for i, (a, b) in enumerate(zip(reference, patched)) if a != b]
    payload = [i for i in changed if not WRAPPED_SHA1_SPAN[0] <= i < WRAPPED_SHA1_SPAN[1]]
    expected_payload = [TARGET_BLOB + k for k, (a, b) in enumerate(
        zip(reference[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], new)) if a != b]
    outside = [i for i in changed
               if not (WRAPPED_SHA1_SPAN[0] <= i < WRAPPED_SHA1_SPAN[1]
                       or TARGET_BLOB <= i < TARGET_BLOB + TARGET_SIZE)]
    fields, opcode, const15, remainder = decode_site(new_number)
    unchanged_outside_c = all((old_number >> b) & 1 == (new_number >> b) & 1
                              for b in range(64) if not (40 <= b <= 45 or 54 <= b <= 55))
    checks += [
        check(f'{tag}.instruction', patched[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] == new,
              f'{patched[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE].hex()} expected {new.hex()}'),
        check(f'{tag}.diff_offsets', payload == expected_payload, f'{[hex(i) for i in payload]}'),
        check(f'{tag}.outside_preserved', not outside, f'{[hex(i) for i in outside]}'),
        check(f'{tag}.bits', (old_number ^ new_number) & ~ALLOWED_BITS == 0,
              f'changed bits {diff_bits}'),
        check(f'{tag}.opcode', opcode == 0x1e, hex(opcode)),
        check(f'{tag}.const15', const15 == 0, str(const15)),
        check(f'{tag}.remainder', remainder == 0, hex(remainder)),
        check(f'{tag}.fields', fields == EXPECTED_FIELDS | {'C': addend},
              json.dumps(fields, sort_keys=True)),
        check(f'{tag}.non_addend_fields', unchanged_outside_c, 'instruction bits outside C')]
    return checks


def check_stale(reference, stale, addend, tag='S'):
    """Stale variant: only the instruction bytes change; SHA1 stays original."""
    changed = [i for i, (a, b) in enumerate(zip(reference, stale)) if a != b]
    payload = [i for i in changed if not WRAPPED_SHA1_SPAN[0] <= i < WRAPPED_SHA1_SPAN[1]]
    new = expected_instruction(addend)
    expected_payload = [TARGET_BLOB + k for k, (a, b) in enumerate(
        zip(reference[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], new)) if a != b]
    return [check(f'{tag}.only_instruction', payload == expected_payload, f'{[hex(i) for i in payload]}'),
            check(f'{tag}.sha1_stale', stale[48:68] == reference[48:68], stale[48:68].hex()),
            check(f'{tag}.sha1_invalid', stale[48:68] != wrapped_sha1(stale), 'digest not refreshed')]


def check_readback(data, count, addend, control=False, tag='B'):
    """Entire-buffer oracle: guards, active, padding, tail, exact equality."""
    expected = oracle(count, addend, control)
    rounded = (count + 31) // 32 * 32
    if len(data) != 4 * len(expected) or len(data) % 4:
        return [check(f'{tag}.length', False, f'{len(data)} bytes, expected {4 * len(expected)}')]
    words = list(struct.unpack('<' + 'I' * len(expected), data))
    mismatch = next(((i, region(i, count)) for i, (a, b) in enumerate(zip(words, expected)) if a != b), None)
    checks = [check(f'{tag}.length', True, f'{len(words)} words'),
              check(f'{tag}.full_buffer', mismatch is None,
                    'first mismatch %s word %d: %08x expected %08x' % (mismatch[1], mismatch[0],
                    words[mismatch[0]], expected[mismatch[0]]) if mismatch else f'{len(words)} words'),
              check(f'{tag}.leading_guards', words[:8] == [0xcdcdcdcd] * 8,
                    ' '.join(f'{w:08x}' for w in words[:8])),
              check(f'{tag}.active', words[8:8 + count] == expected[8:8 + count],
                    f'words 8..{8 + count - 1}'),
              check(f'{tag}.inactive_padding', words[8 + count:8 + rounded] == [0xcdcdcdcd] * (rounded - count),
                    f'words {8 + count}..{8 + rounded - 1}'),
              check(f'{tag}.trailing_guards', words[8 + rounded:16 + rounded] == [0xcdcdcdcd] * 8,
                    f'words {8 + rounded}..{16 + rounded - 1}'),
              check(f'{tag}.control_tail', words[-16:] == [0xa5a50000 + j for j in range(16)],
                    f'last word {words[-1]:08x}')]
    return checks


def check_child_stdout(text, count, control, tag='C'):
    """Child API log: identity, single create/submit/fence, completion marker."""
    try:
        events = [json.loads(line) for line in text.decode().splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError) as exc:
        return [check(f'{tag}.stdout_json', False, str(exc))]
    if not all(isinstance(e, dict) for e in events):
        return [check(f'{tag}.stdout_json', False, 'non-object event')]
    api = [e for e in events if 'api' in e]
    identity = next((e['identity'] for e in events if 'identity' in e), {})
    memory = next((e['memory'] for e in events if 'memory' in e), {})
    rounded = (count + 31) // 32 * 32
    required = {name: [e for e in api if e['api'] == name]
                for name in ('vkCreateShadersEXT', 'vkQueueSubmit', 'vkWaitForFences')}
    last = events[-1] if events else {}
    checks = [
        check(f'{tag}.api_results', all(e.get('result') == 0 for e in api),
              str([(e['api'], e['result']) for e in api if e.get('result') != 0])),
        check(f'{tag}.single_create_submit_fence',
              all(len(v) == 1 for v in required.values()),
              str({k: len(v) for k, v in required.items()})),
        check(f'{tag}.identity', identity.get('name') == 'Apple M2 Max (G14C B1)'
              and identity.get('info') == 'Mesa 25.3.6'
              and identity.get('uuid') == UUID_HEX and identity.get('binary_version') == 0,
              json.dumps(identity, sort_keys=True)),
        check(f'{tag}.render_node', isinstance(identity.get('render_major'), int)
              and isinstance(identity.get('render_minor'), int),
              f"{identity.get('render_major')}:{identity.get('render_minor')}"),
        check(f'{tag}.memory_words', memory.get('words') == 8 + rounded + 8 + 16,
              str(memory.get('words'))),
        check(f'{tag}.completion', last == {'completed': True, 'dispatch': not control,
              'count': count, 'words': 8 + rounded + 8 + 16}, json.dumps(last, sort_keys=True))]
    return checks


def check_patch_json(path, reference, patched, stale, addend):
    """Every stored patch claim must match recomputation from the blobs."""
    try:
        claims = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return [check('J.readable', False, str(exc))]
    hexes = {'input_hex': reference, 'patched_hex': patched}
    if stale is not None:
        hexes['stale_hex'] = stale
    checks = [check(f'J.{key}', bytes.fromhex(claims[key]) == blob, claims[key][:24] + '...')
              for key, blob in hexes.items() if key in claims]
    checks += [
        check('J.reference_sha256', claims.get('reference_sha256', claims.get('input_sha256'))
              == sha256(reference), str(claims.get('reference_sha256', claims.get('input_sha256')))),
        check('J.patched_sha256', claims.get('patched_sha256') == sha256(patched),
              str(claims.get('patched_sha256'))),
        check('J.old_instruction', claims.get('old_instruction')
              == reference[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE].hex(), str(claims.get('old_instruction'))),
        check('J.new_instruction', claims.get('new_instruction')
              == patched[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE].hex(), str(claims.get('new_instruction'))),
        check('J.changed_offsets', claims.get('changed_byte_offsets')
              == [i for i, (a, b) in enumerate(zip(reference, patched)) if a != b],
              str(claims.get('changed_byte_offsets'))),
        check('J.before_fields', claims.get('before_fields') == EXPECTED_FIELDS,
              json.dumps(claims.get('before_fields'), sort_keys=True)),
        check('J.after_fields', claims.get('after_fields') == EXPECTED_FIELDS | {'C': addend},
              json.dumps(claims.get('after_fields'), sort_keys=True)),
        check('J.wrapper_sha1_before', claims.get('wrapper_sha1_before') == reference[48:68].hex(),
              str(claims.get('wrapper_sha1_before'))),
        check('J.wrapper_sha1_after', claims.get('wrapper_sha1_after') == patched[48:68].hex(),
              str(claims.get('wrapper_sha1_after'))),
        check('J.target_offsets', claims.get('target_blob_offset', claims.get('target_code_offset')) in (TARGET_BLOB, TARGET),
              str(claims.get('target_blob_offset', claims.get('target_code_offset'))))]
    optional = [
        ('J.stale_sha256', 'stale_sha256', sha256(stale) if stale is not None else None),
        ('J.changed_bits', 'changed_instruction_bits',
         [b for b in range(64) if (int.from_bytes(reference[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], 'little')
                                   ^ int.from_bytes(patched[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE], 'little')) >> b & 1]),
        ('J.main_size', 'main_size', MAIN_SIZE)]
    checks += [check(f'J.{key}', claims[key] == expected, str(claims[key]) if key in claims else 'not recorded')
               for name, key, expected in optional if key in claims]
    return checks


def check_case(case, run, reference, patched, layout):
    """One recorded case: readback oracle, hashes, stored oracle, child log."""
    name, count, addend = case['name'], case['count'], case.get('addend', 0)
    control = case.get('mode') == 'control' or (layout == 'snapshot' and case.get('mode') == 'control')
    checks = []
    readback = run / (name + '.readback')
    try:
        data = read_blob(readback)
    except OSError as exc:
        return [check(f'{name}.readback', False, str(exc))]
    checks += check_readback(data, count, addend, control, tag=name)
    checks.append(check(f'{name}.readback_sha256', case.get('readback_sha256') == sha256(data),
                        str(case.get('readback_sha256'))))
    oracle_path = run / (name + '-oracle.json')
    if oracle_path.is_file():
        try:
            stored = json.loads(oracle_path.read_text())
            expected = oracle(count, addend, control)
            actual = list(struct.unpack('<' + 'I' * (len(data) // 4), data)) if len(data) % 4 == 0 else []
            checks += [check(f'{name}.oracle_passed', stored.get('passed') is True, str(stored.get('passed'))),
                       check(f'{name}.oracle_expected', stored.get('expected') == expected, 'stored expected vector'),
                       check(f'{name}.oracle_actual', stored.get('actual') == actual, 'stored actual vector')]
        except (OSError, ValueError) as exc:
            checks.append(check(f'{name}.oracle_json', False, str(exc)))
    stdout_path = run / name / 'stdout.txt'
    checks.append(check(f'{name}.stdout_present', stdout_path.is_file(), ''))
    if stdout_path.is_file():
        checks += check_child_stdout(stdout_path.read_bytes(), count, control, tag=name)
        events = [json.loads(line) for line in stdout_path.read_text().splitlines() if line.strip()]
        checks.append(check(f'{name}.recorded_events', case.get('api_events') == events, ''))
    command_path = run / name / 'command.json'
    try:
        command = json.loads(command_path.read_text())
        checks.append(check(f'{name}.command_success', command.get('returncode') == 0
                            and not command.get('timed_out'), ''))
    except (OSError, ValueError) as exc:
        checks.append(check(f'{name}.command_success', False, str(exc)))
    blob = {'no-dispatch': None, 'index-source-33': None}.get(name)
    if layout == 'snapshot':
        blob = reference if name.startswith(('before-', 'after-')) else \
            run / f"addend-{addend}" / 'patched.bin' if name.startswith('addend-') else None
    else:
        blob = reference if name.startswith(('imadd-before', 'imadd-after')) else \
            patched if name.startswith('imadd-patched') else blob
    if blob is not None:
        try:
            data = blob.read_bytes() if isinstance(blob, Path) else blob
            checks.append(check(f'{name}.input_sha256', case.get('input_sha256') == sha256(data),
                                str(case.get('input_sha256'))))
        except OSError as exc:
            checks.append(check(f'{name}.input_sha256', False, str(exc)))
    return checks


def verify_run(run, args):
    """Detect the recorded layout and verify everything retained in it."""
    checks = [check('run.directory', run.is_dir(), str(run))]
    if not run.is_dir():
        return checks
    record_path = run / 'record.json' if (run / 'record.json').is_file() else \
        run / 'summary.json' if (run / 'summary.json').is_file() else None
    if record_path is None:
        return checks + [check('run.layout', False, 'no record.json/summary.json')]
    layout = 'final' if record_path.name == 'record.json' else 'snapshot'
    try:
        record = json.loads(record_path.read_text())
    except (OSError, ValueError) as exc:
        return checks + [check('run.record_json', False, str(exc))]
    checks.append(check('run.layout', True, layout))
    reference_path = run / 'index.bin' if layout == 'final' else run / 'sources/index-reference.bin'
    if args.reference and not blob_exists(reference_path):
        reference_path = Path(args.reference)
    try:
        reference = read_blob(reference_path)
    except OSError as exc:
        return checks + [check('run.reference', False, str(exc))]
    checks += check_reference(reference)
    patched_path = run / 'imadd-patch/patched.bin' if layout == 'final' else None
    stale_path = run / 'imadd-patch/stale-integrity.bin' if layout == 'final' else None
    addend = 1
    patch_json = run / 'imadd-patch/patch.json' if layout == 'final' else None
    if layout == 'snapshot':
        addend_dirs = sorted(p for p in run.glob('addend-*') if p.is_dir())
        for directory in addend_dirs:
            try:
                value = json.loads((directory / 'patch.json').read_text())['addend']
                blob = (directory / 'patched.bin').read_bytes()
            except (OSError, ValueError, KeyError) as exc:
                checks.append(check(f'patch.{directory.name}', False, str(exc)))
                continue
            checks += check_patched(reference, blob, value, tag=f'patch{value}')
            checks += check_patch_json(directory / 'patch.json', reference, blob, None, value)
            patched_path = patched_path or (directory / 'patched.bin')
        snapshot_hashes = record.get('snapshot_hashes', {})
        for rel, expected in sorted(snapshot_hashes.items()):
            path = run / rel
            try:
                checks.append(check(f'snapshot.{rel}', sha256(path.read_bytes()) == expected, expected))
            except OSError as exc:
                checks.append(check(f'snapshot.{rel}', False, str(exc)))
    try:
        patched = read_blob(patched_path)
    except (OSError, TypeError) as exc:
        return checks + [check('run.patched', False, str(exc))]
    checks += check_patched(reference, patched, addend)
    stale = None
    if stale_path is not None and blob_exists(stale_path):
        stale = read_blob(stale_path)
        checks += check_stale(reference, stale, addend)
    if patch_json is not None and patch_json.is_file():
        checks += check_patch_json(patch_json, reference, patched, stale, addend)
    required = {'no-dispatch', 'index-source-33', 'imadd-before-33', 'imadd-patched-33', 'imadd-patched-257', 'imadd-after-33'}
    if layout == 'final':
        names = [c.get('name') for c in record.get('cases', [])]
        checks.append(check('run.required_cases', len(names) == 6 and set(names) == required, str(names)))
        for name in ('stale-integrity', 'wrong-node'):
            checks.append(check('run.required_' + name, (run / name).is_dir(), ''))
    for case in record.get('cases', []):
        checks += check_case(case, run, reference, patched, layout)
    if layout == 'final':
        stale_dir = run / 'stale-integrity'
        if stale_dir.is_dir():
            try:
                command = json.loads((stale_dir / 'command.json').read_text())
                events = [json.loads(line) for line in (stale_dir / 'stdout.txt').read_text().splitlines() if line.strip()]
                create = [e for e in events if e.get('api') == 'vkCreateShadersEXT']
                checks += [
                    check('stale.returncode', command.get('returncode') == 1, str(command.get('returncode'))),
                    check('stale.rejected', len(create) == 1 and create[0].get('result') == INCOMPATIBLE_SHADER_BINARY,
                          str(create)),
                    check('stale.no_submit', not any(e.get('api') == 'vkQueueSubmit' for e in events), ''),
                    check('stale.no_readback', not (run / 'stale.readback').exists(), '')]
            except (OSError, ValueError) as exc:
                checks.append(check('stale.record', False, str(exc)))
        wrong = run / 'wrong-node'
        if wrong.is_dir():
            try:
                command = json.loads((wrong / 'command.json').read_text())
                stdout = (wrong / 'stdout.txt').read_bytes()
                checks += [check('wrong_node.returncode', command.get('returncode') == 1, str(command.get('returncode'))),
                          check('wrong_node.before_device', b'vkCreateDevice' not in stdout, ''),
                          check('wrong_node.no_readback', not (run / 'wrong.readback').exists(), '')]
            except OSError as exc:
                checks.append(check('wrong_node.record', False, str(exc)))
        checks += [
            check('run.passed', record.get('passed') is True, str(record.get('passed', record.get('error')))),
            check('run.index_binary_pin', record.get('index_binary', {}).get('sha256') == CONTROL_SHA256,
                  str(record.get('index_binary'))),
            check('run.index_validation', record.get('index_validation', {}).get('result') == 0, ''),
            check('run.wrong_node_control', record.get('wrong_node_control_passed') is True, ''),
            check('run.no_dispatch_rejected', record.get('no_dispatch_rejected_as_dispatch') is True, ''),
            check('run.stale_control', record.get('stale_integrity_control', {}).get('passed') is True, '')]
        executable = run / 'vulkan_compute'
        if executable.is_file():
            checks.append(check('run.executable', record.get('executable_sha256') == sha256(executable.read_bytes()),
                                str(record.get('executable_sha256'))))
    else:
        checks.append(check('run.passed', record.get('passed') is True, str(record.get('passed', record.get('error')))))
    return checks


def verify_patch_dir(directory, reference, addend):
    checks = [check('patch_dir.directory', directory.is_dir(), str(directory))]
    try:
        patched = (directory / 'patched.bin').read_bytes()
    except OSError as exc:
        return checks + [check('patch_dir.patched', False, str(exc))]
    checks += check_patched(reference, patched, addend)
    stale = directory / 'stale-integrity.bin'
    if stale.is_file():
        checks += check_stale(reference, stale.read_bytes(), addend)
    patch_json = directory / 'patch.json'
    if patch_json.is_file():
        checks += check_patch_json(patch_json, reference, patched,
                                  stale.read_bytes() if stale.is_file() else None, addend)
    return checks


def tamper_readback(count, addend, index, xor):
    words = oracle(count, addend)
    words[index] ^= xor
    return b''.join(w.to_bytes(4, 'little') for w in words)


def self_test(reference):
    """The verifier must accept the real patch and reject known tampering."""
    checks = []
    for addend in (1, 63, 64, 255):
        new = expected_instruction(addend)
        patched = bytearray(reference)
        patched[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] = new
        patched[48:68] = wrapped_sha1(patched)
        checks += [c for c in check_patched(reference, bytes(patched), addend, tag=f'T{addend}')
                   if c['name'].startswith(f'T{addend}.')]
    extra = bytearray(reference)
    extra[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] = expected_instruction(1)
    extra[TARGET_BLOB + 6] ^= 0x40            # Cx bit with addend 1: not the derived bytes
    extra[48:68] = wrapped_sha1(extra)
    result = check_patched(reference, bytes(extra), 1)
    checks += [check('selftest.extra_bit_rejected',
                     any(not c['ok'] for c in result), 'addend-1 plus bit 54 must fail')]
    nonc = bytearray(reference)
    nonc[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] = expected_instruction(1)
    nonc[TARGET_BLOB + 4] ^= 0x01            # B-field bit, outside C/Cx
    nonc[48:68] = wrapped_sha1(nonc)
    result = check_patched(reference, bytes(nonc), 1)
    checks.append(check('selftest.non_addend_bit_rejected',
                        any(not c['ok'] for c in result), 'B-field bit must fail'))
    metadata = bytearray(reference)
    metadata[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] = expected_instruction(1)
    metadata[0x49] ^= 0xff                   # hk metadata byte
    metadata[48:68] = wrapped_sha1(metadata)
    result = check_patched(reference, bytes(metadata), 1)
    checks.append(check('selftest.metadata_rejected',
                        any(not c['ok'] for c in result), 'metadata byte must fail'))
    stale_digest = bytearray(reference)
    stale_digest[TARGET_BLOB:TARGET_BLOB + TARGET_SIZE] = expected_instruction(1)
    result = check_patched(reference, bytes(stale_digest), 1)
    checks.append(check('selftest.stale_sha1_rejected',
                        any(not c['ok'] for c in result), 'unrefreshed SHA1 must fail'))
    tampered_ref = bytearray(reference)
    tampered_ref[0x941] ^= 0x80              # instruction-adjacent byte
    tampered_ref[48:68] = wrapped_sha1(tampered_ref)
    result = check_reference(bytes(tampered_ref))
    checks.append(check('selftest.reference_tamper_rejected',
                        any(not c['ok'] for c in result), 'mutated control must be refused'))
    for tag, index in (('guard', 3), ('active', 8), ('padding', 8 + 33), ('trailing', 8 + 64), ('tail', -1)):
        result = check_readback(tamper_readback(33, 1, index, 1), 33, 1, tag='T')
        names = {'guard': 'T.leading_guards', 'active': 'T.active', 'padding': 'T.inactive_padding',
                 'trailing': 'T.trailing_guards', 'tail': 'T.control_tail'}[tag]
        checks.append(check(f'selftest.{tag}_tamper_rejected',
                            any(not c['ok'] for c in result if c['name'] == names), names))
    truncated = tamper_readback(33, 1, 3, 0)[:-4]
    result = check_readback(truncated, 33, 1, tag='T')
    checks.append(check('selftest.truncated_rejected',
                        any(not c['ok'] for c in result if c['name'] == 'T.length'), 'T.length'))
    good = check_readback(tamper_readback(33, 1, 3, 0), 33, 1, tag='T')
    checks.append(check('selftest.clean_readback_accepted', all(c['ok'] for c in good), ''))
    return checks


def find_reference(explicit):
    if explicit:
        return Path(explicit)
    for candidate in (str(Path(__file__).resolve().parents[1] / 'novel-results/2026-10-04-imadd-addend/index.bin'),) + REFERENCE_CANDIDATES:
        path = Path(candidate)
        if blob_exists(path):
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', type=Path, help='run or patch directories')
    parser.add_argument('--reference', help='pinned control blob (index.bin)')
    parser.add_argument('--addend', type=int, default=1, help='addend for --patch-dir mode (default 1)')
    parser.add_argument('--patch-dir', type=Path, help='patched.bin/patch.json directory')
    parser.add_argument('--baseline-run', type=Path, default=BASELINE_RUN,
                        help='retained baseline run for unchanged-control cross-link')
    parser.add_argument('--self-test', action='store_true', help='tamper-discrimination check')
    args = parser.parse_args()
    checks = []
    reference = None
    if args.paths or args.patch_dir or args.self_test:
        path = find_reference(args.reference)
        if path is not None:
            reference = read_blob(path)
            checks += check_reference(reference)
    for run in args.paths:
        checks += verify_run(run.resolve(), args)
    if args.patch_dir:
        if reference is None:
            checks.append(check('patch_dir.reference', False, 'no pinned reference available'))
        else:
            checks += verify_patch_dir(args.patch_dir.resolve(), reference, args.addend)
    if args.baseline_run.is_dir():
        base = args.baseline_run
        for n in (1, 32, 33, 257):
            path = base / f'index-import-{n}.readback'
            if path.is_file():
                checks += check_readback(path.read_bytes(), n, 0, tag=f'baseline{n}')
        for name, n in (('index-import-33', 33), ('index-import-257', 257)):
            path = base / f'{name}.readback'
            if path.is_file():
                checks.append(check(f'baseline.pin_{n}', sha256(path.read_bytes()) in
                                    ('ac28bb344417d7efd5bad65118332e22ecad5b6b711878f0143437dfb00b4fcc',
                                     'bfee50b2bdcf12dfdbf8f108e0afd20bc3ff3c68318d4ec3a5ced75bd2618578'),
                                    sha256(path.read_bytes())))
    if args.self_test:
        if reference is None:
            checks.append(check('selftest.reference', False, 'no pinned reference available'))
        else:
            checks += self_test(reference)
    if not checks:
        parser.error('nothing to verify: pass run/patch directories, --patch-dir or --self-test')
    failures = [c for c in checks if not c['ok']]
    for c in checks:
        print(('ok   ' if c['ok'] else 'FAIL ') + c['name'] + ('  ' + c['detail'] if c['detail'] else ''))
    summary = {'passed': not failures, 'checks': len(checks),
               'failures': [c['name'] for c in failures]}
    print(json.dumps(summary))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
