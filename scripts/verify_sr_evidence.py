#!/usr/bin/env python3
"""Verify embedded special-register scan evidence without GPU/vendor dependencies."""
import copy
import hashlib
import json
import struct
import sys

CODE_START = 0x8BC
CODE_SIZE = 336
SITE = CODE_START + 0x96
CONTROL_SHA256 = "b79bd25941bdea1a0095b219fe0333ac5c18822225de811c9308a38702e9e098"
KNOWN = {
    80: lambda i: i, 0: lambda i: i // 32, 4: lambda i: 32,
    5: lambda i: 1, 6: lambda i: 1, 48: lambda i: i % 32,
    51: lambda i: i % 32, 52: lambda i: i % 32, 53: lambda i: 0,
}
DOUBLE = bytes.fromhex("0e05422664000000")
INCREMENT = bytes.fromhex("0e05012064000000")
DELAY = bytes.fromhex("0e09014064000000")
WAIT = bytes.fromhex("3800")
CONSTANT = bytes.fromhex("620978563412")
PARITY = bytes.fromhex("7e0942128000")
CONDITION = bytes.fromhex("520844020000")


def fail(message):
    raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def wrapped_sha1(data):
    zeroed = bytearray(data)
    zeroed[48:68] = b"\0" * 20
    return hashlib.sha1(zeroed).digest()


def read_record(path):
    with open(path, encoding="utf-8") as f:
        value = json.load(f)
    if isinstance(value, dict) and isinstance(value.get("record"), dict):
        value = value["record"]
    if not isinstance(value, dict):
        fail("record must be an object")
    return value


def derived_blob(record, patch):
    base = bytes.fromhex(record["control_hex"])
    if len(base) != 2572 or sha256(base) != CONTROL_SHA256:
        fail("invalid control baseline")
    selector = patch["selector"]
    if type(selector) is not int or not 0 <= selector <= 255:
        fail("invalid selector")
    raw = 0x72 | (2 << 7) | (4 << 9) | ((selector & 63) << 16) | ((selector >> 6) << 26)
    read = raw.to_bytes(4, "little")
    expected_site = read + WAIT
    pair = patch.get("pair_gap") is not None
    sparse = patch.get("sparse_even") is True
    out = bytearray(base)
    if sparse:
        read1 = CONSTANT if patch.get("constant_control") else expected_site
        main = base[CODE_START + 0x80:SITE] + PARITY + CONDITION + read1
        main += base[CODE_START + 0x9C:CODE_START + 0xAE]
        main += base[CODE_START + 0xAE:CODE_START + 0xB4]
        main += base[CODE_START + 0xAE:CODE_START + 0xB6]
        if patch.get("main_hex") != main.hex() or patch.get("main_size") != len(main) + 16:
            fail("sparse main mismatch")
        if len(main) + 16 > 128:
            fail("sparse main exceeds slot")
        out[CODE_START + 0x80:CODE_START + 0x100] = main + bytes(128 - len(main))
        struct.pack_into("<I", out, 0x83D, len(main) + 16)
    elif not pair:
        if patch.get("old") != base[SITE:SITE + 6].hex():
            fail("simple patch old bytes mismatch")
        if patch.get("new") != expected_site.hex():
            fail("simple patch selector bytes mismatch")
        if patch.get("fields") != {"Dt": 2, "D": 4, "SR": selector}:
            fail("simple patch fields mismatch")
        out[SITE:SITE + 6] = expected_site
    else:
        gap = patch["pair_gap"]
        if patch.get("main_size") != len(bytes.fromhex(patch["main_hex"])) // 1 + 16:
            # main_hex is the complete instruction stream, not metadata padding.
            fail("pair main_size inconsistent with main_hex")
        if not 0 <= gap <= 256:
            fail("invalid pair gap")
        prefix = base[CODE_START + 0x80:SITE]
        address = base[CODE_START + 0x9C:CODE_START + 0xA4]
        store = base[CODE_START + 0xA4:CODE_START + 0xAC]
        old_wait = base[CODE_START + 0xAC:CODE_START + 0xAE]
        end = base[CODE_START + 0xAE:CODE_START + 0xB6]
        read1 = CONSTANT if patch.get("constant_control") else read
        expected_main = prefix + read1 + DOUBLE + address + store + old_wait
        expected_main += DELAY * gap + read1 + INCREMENT + store + old_wait + end
        main = bytes.fromhex(patch["main_hex"])
        if main != expected_main:
            fail("pair main does not match derived baseline")
        if patch.get("main_size") != len(main) + 16:
            fail("pair main_size must include 16-byte post-stop padding")
        preamble_offset = patch["preamble_offset"]
        code_size = patch["code_size"]
        if preamble_offset != (0x80 + len(main) + 16 + 127) // 128 * 128:
            fail("pair preamble offset mismatch")
        if code_size != preamble_offset + CODE_SIZE - 0x100:
            fail("pair code size mismatch")
        code = base[CODE_START:CODE_START + 0x80] + main
        preamble = base[CODE_START + 0x100:CODE_START + CODE_SIZE]
        code += bytes(preamble_offset - len(code)) + preamble
        if len(code) != code_size:
            fail("pair code length mismatch")
        out = bytearray(base[:CODE_START] + code)
        struct.pack_into("<I", out, 0x41D, code_size)
        struct.pack_into("<I", out, 0x83D, len(main) + 16)
        struct.pack_into("<I", out, 0x845, preamble_offset)
        struct.pack_into("<I", out, CODE_START - 8, code_size)
        struct.pack_into("<Q", out, 40, len(out))
    out[48:68] = wrapped_sha1(out)
    expected_offsets = [i for i, (old, new) in enumerate(zip(base, out)) if old != new]
    if not pair and not sparse and patch.get("changed_offsets") != expected_offsets:
        fail("simple patch offsets mismatch")
    if patch.get("patched_sha256") != sha256(out):
        fail("patched shader SHA-256 mismatch")
    if patch.get("input_sha256") != CONTROL_SHA256:
        fail("patch input SHA-256 mismatch")
    if patch.get("assembler_sha256") and len(patch["assembler_sha256"]) != 64:
        fail("malformed assembler digest")
    return bytes(out)


def check_sample(sample, count, pairs, expected, sparse=False):
    if (sample.get("passed") is not True or
            bool(sample.get("pairs", False)) is not pairs or
            bool(sample.get("even_mask", False)) is not sparse):
        fail("sample status/pair flag mismatch")
    raw = bytes.fromhex(sample["readback_hex"])
    rounded = (count + 31) // 32 * 32
    if len(raw) != (rounded + 32) * 4:
        fail("readback length mismatch")
    if sample.get("readback_sha256") != sha256(raw):
        fail("readback SHA-256 mismatch")
    words = list(struct.unpack("<" + "I" * (rounded + 32), raw))
    active = count * (2 if pairs else 1)
    if active > rounded:
        fail("active output exceeds allocation")
    initial = [0xCDCDCDCD] * (rounded + 16) + [0xA5A50000 + i for i in range(16)]
    untouched = list(range(8)) + list(range(8 + active, rounded + 16)) + list(range(rounded + 16, rounded + 32))
    if any(words[i] != initial[i] for i in untouched):
        fail("guard or padding word changed")
    values = words[8:8 + active]
    if sparse and any(values[i] != 0xCDCDCDCD for i in range(1, len(values), 2)):
        fail("sparse odd lane is not sentinel")
    if sample.get("values") != values:
        fail("embedded values do not match readback")
    if expected is not None:
        if sparse:
            for i, value in enumerate(values):
                if i % 2 == 0 and value != expected(i):
                    fail("known sparse selector oracle mismatch")
        else:
            oracle = [expected(i) for i in range(count) for _ in range(2 if pairs else 1)]
            if values != oracle:
                fail("known selector oracle mismatch")
    events = sample.get("events", [])
    if not events or any("api" in e and e.get("result") != 0 for e in events):
        fail("API event failure")
    identities = [e.get("identity") for e in events if isinstance(e.get("identity"), dict)]
    if len(identities) != 1 or not all(identities[0].get(k) for k in ("name", "driver", "info", "uuid")):
        fail("missing device identity")
    if "Mesa" not in identities[0]["info"]:
        fail("unexpected driver info")
    for api in ("vkCreateShadersEXT", "vkQueueSubmit", "vkWaitForFences"):
        if sum(e.get("api") == api and e.get("result") == 0 for e in events) != 1:
            fail("missing Vulkan success event: " + api)
    if events[-1] != {"completed": True, "dispatch": True, "count": count, "words": rounded + 32}:
        fail("completion event mismatch")
    before, after = sample.get("host_before_ns"), sample.get("host_after_ns")
    if not isinstance(before, int) or not isinstance(after, int) or not 0 < before < after:
        fail("invalid host bracket")
    return identities[0]


def verify(record, partial=False):
    if record.get("passed") is not True or record.get("complete") is not True:
        fail("record is incomplete or failed")
    count, repeats, gap = record.get("count"), record.get("repeats"), record.get("pair_gap")
    if not isinstance(count, int) or not isinstance(repeats, int) or not (1 <= count <= 257 and 2 <= repeats <= 5):
        fail("unexpected scan dimensions")
    if not partial and (repeats != 3 or count != (16 if gap is not None else 257)):
        fail("unexpected full-scan dimensions")
    requested = record.get("requested")
    if (not isinstance(requested, list) or not requested or
            len(set(requested)) != len(requested) or any(type(x) is not int or not 0 <= x <= 255 for x in requested) or
            (not partial and set(requested) != set(range(256)))):
        fail("required selector set missing")
    if record.get("failures") != []:
        fail("record contains failures")
    if gap is not None and gap != 128:
        fail("unexpected pair gap")
    observations = record.get("observations", [])
    if len(observations) != len(requested):
        fail("incomplete selector observations")
    seen = [o.get("selector") for o in observations]
    if set(seen) != set(requested) or len(seen) != len(set(seen)):
        fail("observed selectors do not equal requested selectors")
    identity = None
    last_after = 0
    for observation in observations:
        selector = observation.get("selector")
        if not observation.get("completed") or len(observation.get("samples", [])) != repeats:
            fail("incomplete selector repeats")
        patch = observation["patch"]
        if patch.get("selector") != selector:
            fail("patch selector does not match observation")
        derived = derived_blob(record, patch)
        if patch.get("main_size") and gap is not None:
            if patch["code_size"] != struct.unpack_from("<I", derived, 0x41D)[0]:
                fail("derived code-size metadata mismatch")
        for sample in observation["samples"]:
            if sample.get("shader_sha256") != sha256(derived):
                fail("sample shader SHA-256 mismatch")
            identity = check_sample(sample, count, gap is not None, KNOWN.get(selector),
                                    patch.get("sparse_even", False))
            if sample["host_before_ns"] <= last_after:
                fail("host brackets are not ordered")
            last_after = sample["host_after_ns"]
    controls = record.get("controls", [])
    if len(controls) < (18 if not partial else 1) or any(c.get("passed") is not True for c in controls):
        fail("control oracle/checkpoint failure")
    names = {c.get("name") for c in controls}
    if not {"unchanged-before", "unchanged-after"} <= names:
        fail("missing unchanged controls")
    if len(names)!=len(controls):fail('duplicate control names')
    for ordinal in range(16,len(requested)+1,16):
        if f'control-after-{ordinal}' not in names:fail('missing periodic control')
    control_patch=record.get('paired_control_patch') or record.get('sparse_control_patch')
    expected_control=sha256(derived_blob(record,control_patch)) if control_patch else CONTROL_SHA256
    for control in controls:
        check_sample(control,count,bool(control.get('pairs')),lambda i:0x12345678,bool(control.get('even_mask')))
        expected_hash=CONTROL_SHA256 if control.get('name')=='original-before' else expected_control
        if control.get('shader_sha256')!=expected_hash:fail('control shader hash mismatch')
    deltas = {}
    for observation in observations:
        values = [s["values"] for s in observation["samples"]]
        if gap is not None:
            deltas[observation["selector"]] = sorted(set(
                sample[i + 1] - sample[i] for sample in values for i in range(0, len(sample), 2)))
    return deltas


def selftest(record):
    verify(record)
    mutations = []
    bad = copy.deepcopy(record)
    sample = bad["observations"][0]["samples"][0]
    raw = bytearray.fromhex(sample["readback_hex"])
    raw[0] ^= 1
    sample["readback_hex"] = raw.hex()
    sample["readback_sha256"] = sha256(raw)
    mutations.append(bad)
    bad = copy.deepcopy(record)
    del bad["observations"][0]["samples"][-1]
    mutations.append(bad)
    bad = copy.deepcopy(record)
    bad["observations"][1]["selector"] = bad["observations"][0]["selector"]
    mutations.append(bad)
    bad = copy.deepcopy(record)
    bad["observations"][0]["samples"][0]["shader_sha256"] = "0" * 64
    mutations.append(bad)
    for candidate in mutations:
        try:
            verify(candidate)
        except ValueError:
            continue
        return False
    return True


def main(argv):
    if len(argv) not in (2, 3) or (len(argv) > 1 and argv[1] == "--help"):
        print("usage: verify_sr_evidence.py [--partial] RECORD.json | --selftest RECORD.json")
        return 0 if len(argv) == 2 else 2
    try:
        record = read_record(argv[-1])
        if len(argv) == 3 and argv[1] == "--selftest":
            if not selftest(record):
                fail("selftest corruption was accepted")
            print(json.dumps({"passed": True, "selftest": True}))
        else:
            partial = len(argv) == 3 and argv[1] == "--partial"
            deltas = verify(record, partial=partial)
            ticking = {str(k): v for k, v in deltas.items() if any(v)}
            print(json.dumps({"passed": True, "selectors": len(record["requested"]),
                              "repeats": record["repeats"],
                              "pair_gap": record.get("pair_gap"), "first_second_delta": deltas,
                              "ticking_candidates": ticking}, sort_keys=True))
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print("verify_sr_evidence: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
