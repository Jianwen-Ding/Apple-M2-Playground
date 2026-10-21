//! B42 follow-up (local): `b42_ts CODE N` queues N launches of CODE (count.bin: 64 lanes, each adds 1 to its launch's
//! own counter) on one queue without waiting, waits only for the last, then reports per command whether its counter
//! is right and whether its firmware timestamps were written.
use agx_runtime::*;
use std::time::Duration;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let code = std::fs::read(&a[1]).unwrap();
    let n: usize = a[2].parse().unwrap();
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    let mut q = Queue::new(&mut vm).unwrap();
    let mut keep = Vec::new();
    let mut fences = Vec::new();
    for _ in 0..n {
        let out = vm.alloc_data(0x1000).unwrap();
        let table = vm.alloc_data(0x1000).unwrap();
        let mut unif = vm.alloc_data(0x1000).unwrap();
        let u = unif.as_mut_slice();
        u[20..24].copy_from_slice(&u32::MAX.to_le_bytes());
        u[24..32].copy_from_slice(&out.va.to_le_bytes());
        u[32..40].copy_from_slice(&table.va.to_le_bytes());
        let mut usc = vm.alloc_usc(0x2000).unwrap();
        let off = (usc.va - vm.usc_base) as u32;
        let p = Pipeline { code: off + 0x400, gpr_halves: 32, uniforms: vec![(0, 20, unif.va)], shared_bytes: 0, spill_bucket: 0 };
        let w = p.usc_words();
        usc.as_mut_slice()[..w.len()].copy_from_slice(&w);
        usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(&code);
        let c = cdm_dispatch(off, p.uniform_halves(), dev.g14x(), [64, 1, 1], [32, 1, 1]);
        let mut cdm = vm.alloc_data(0x1000).unwrap();
        cdm.as_mut_slice()[..c.len()].copy_from_slice(&c);
        fences.push(q.submit_compute(cdm.va, cdm.va + c.len() as u64, &[]).unwrap());
        keep.push((out, table, unif, usc, cdm));
    }
    let last = *fences.last().unwrap();
    // the raw syncobj wait only (agx_runtime's wait also applies the zero-timestamp check)
    let r = q.wait(last, Duration::from_secs(10));
    let mut bad_count = Vec::new();
    let mut zero_ts = Vec::new();
    for (i, (f, k)) in fences.iter().zip(&keep).enumerate() {
        let cnt = u32::from_le_bytes(k.1.as_slice()[0..4].try_into().unwrap());
        if cnt != 64 { bad_count.push(i) }
        if let Some((s, e)) = q.timing(*f) { if s == 0 && e == 0 { zero_ts.push(i) } }
    }
    println!("{{\"queued\":{n},\"wait\":{:?},\"wrong_results\":{:?},\"zero_timestamps\":{:?}}}", r.map_err(|e| e.to_string()), bad_count, zero_ts);
}
