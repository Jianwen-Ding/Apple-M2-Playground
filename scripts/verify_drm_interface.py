"""Offline check of the host-side Asahi DRM interface limits (results/2026-10-16-drm-interface).

Re-reads the recorded drm_limits output and checks every claim made in docs/drm-interface.md.
No device access."""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT / 'results/2026-10-16-drm-interface'
EINVAL, ENOENT, ENOSPC = 22, 2, 28


def main():
    rows = {}
    for line in (R / 'drm-limits.jsonl').read_text().splitlines():
        rows.update(json.loads(line))
    fails = []

    def check(name, ok):
        print(('ok   ' if ok else 'FAIL ') + name)
        if not ok: fails.append(name)

    src = hashlib.sha256((ROOT / 'tests/drm_limits.c').read_bytes()).hexdigest()
    check('probe source matches the recorded hash', src == (R / 'drm_limits.c.sha256').read_text().strip())
    check('no GPU work submitted', rows['done'] is True and rows['submits'] == 0)
    p = rows['params']
    check('identity G14C rev 0x11 chip 6021', (p['gpu_generation'], p['gpu_variant'], p['gpu_revision'], p['chip_id']) == (14, 'C', 0x11, '6021'))
    check('4 clusters x 10 logical cores, 38 enabled', p['num_clusters_total'] == 4 and p['num_cores_per_cluster'] == 10
          and sum(bin(m).count('1') for m in p['core_masks']) == 38)
    check('soft faults on (features bit 0)', p['features'] & 1 == 1)
    check('command timestamps at 1 GHz', p['command_timestamp_frequency_hz'] == 10**9)
    check('64 commands per submission, 16 attachments', (p['max_commands_per_submission'], p['max_attachments']) == (64, 16))
    check('VA window 16 KiB .. 2^39 - 32 KiB, kernel carve-out >= 512 MiB',
          p['vm_start'] == 16384 and p['vm_end'] == 2**39 - 32768 and p['vm_kernel_min_size'] == 512 << 20)
    g = rows['get_params']
    check('GET_PARAMS: group 1 rejected, short buffer honoured, oversized buffer accepted',
          g['group1_errno'] == EINVAL and g['size8_errno'] == 0 and g['size8_wrote_only_8'] == 1 and g['size4096_errno'] == 0)
    check('GET_TIME works, nonzero flags rejected', rows['get_time']['errno'] == 0 and rows['get_time']['flags1_errno'] == EINVAL)
    check('VM_CREATE rejects small / outside / flipped kernel ranges', set(rows['vm_create_bad'].values()) == {EINVAL})
    check('at least 256 VMs per process', rows['vm_count']['created'] == 256)
    gf = rows['gem_flags']
    check('GEM flags: 0 / WRITEBACK / VM_PRIVATE ok, unknown bits and vm_id without VM_PRIVATE rejected',
          (gf['none'], gf['writeback'], gf['vm_private'], gf['bit2'], gf['bit31'], gf['vm_id_without_private']) == (0, 0, 0, EINVAL, EINVAL, EINVAL))
    check('GEM size 0 -> ENOSPC, unaligned size accepted', gf['size0'] == ENOSPC and gf['size_unaligned_20k'] == 0)
    check('GEM create up to 64 GiB (unpinned) succeeds', rows['gem_size']['largest_ok'] == 64 << 30)
    b = rows['vm_bind']
    check('bind needs READ or WRITE; R, W, RW accepted', (b['rw'], b['read_only'], b['write_only'], b['no_perm']) == (0, 0, 0, EINVAL))
    check('bind rejects 4 KiB-aligned VA/offset, ranges past the BO, unknown flags',
          all(b[k] == EINVAL for k in ('va_unaligned_4k', 'offset_unaligned_4k', 'range_past_bo', 'flag_bit4')))
    check('bind window: vm_start ok; below vm_start, kernel carve-out and vm_end rejected',
          b['at_vm_start'] == 0 and all(b[k] == EINVAL for k in ('below_vm_start', 'top_page_of_vm', 'at_vm_end')))
    check('rebind over a bound range and unbind of an unmapped range both succeed', b['overlapping_rebind'] == 0 and b['unbind_unmapped'] == 0)
    check('SINGLE_PAGE binds up to 64 GiB of VA', b['single_page_16MiB'] == 0 and rows['single_page_range']['largest_ok'] == 64 << 30)
    check('regular pinned bind of 4 GiB', rows['regular_bind']['largest_ok'] == 4 << 30)
    q = rows['queue_create']
    check('queue priority 0/1 ok, 2/3/4 EINVAL (not EPERM)', q['priority_errno'] == [0, 0, EINVAL, EINVAL, EINVAL])
    check('queue flags rejected, unknown VM / queue -> ENOENT', q['flags1'] == EINVAL and q['bad_vm'] == ENOENT and q['destroy_unknown'] == ENOENT)
    check('at least 64 queues on one VM', rows['queue_count']['created'] == 64)
    print(f'{len(fails)} failures')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
