//! B22 probe (local, not part of ZLUDA): launch CODE (a control-shaped counting kernel: lanes with gid & 31 == 0 add 1
//! to table word 0) with any global / local size, building the CDM stream by hand (no 1,024-thread assert).
//! `b22_limits CODE GX GY GZ LX LY LZ` prints the fence result, firmware time and the counter.
use agx_runtime::*;
use std::time::{Duration, Instant};

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let code = std::fs::read(&a[1]).unwrap();
    let n: Vec<u32> = a[2..8].iter().map(|s| s.parse().unwrap()).collect();
    let (global, local) = ([n[0], n[1], n[2]], [n[3], n[4], n[5]]);
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    let out = vm.alloc_data(0x10000).unwrap();
    let table = vm.alloc_data(0x4000).unwrap();
    let mut unif = vm.alloc_data(0x4000).unwrap();
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&u32::MAX.to_le_bytes());          // u5 = count: every gid passes the bounds check
    let _ = &out;
    u[24..32].copy_from_slice(&(1u64 << 39).to_le_bytes());       // u6_u7 = 2^39, outside the VM: every output store is dropped (soft faults)
    u[32..40].copy_from_slice(&table.va.to_le_bytes());          // u8_u9: counter at word 0
    let mut usc = vm.alloc_usc(0x1000).unwrap();
    let usc_off = (usc.va - vm.usc_base) as u32;
    let p = Pipeline { code: usc_off + 0x400, gpr_halves: 32, uniforms: vec![(0, 20, unif.va)], shared_bytes: 0 };
    let words = p.usc_words();
    usc.as_mut_slice()[..words.len()].copy_from_slice(&words);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(&code);
    let mut c: Vec<u8> = Vec::new();
    let mut put = |v: u32| c.extend_from_slice(&v.to_le_bytes());
    put(p.uniform_halves().div_ceil(64).max(1) << 1);
    put(usc_off);
    if dev.g14x() { put(0); put(1 << 30); }
    for g in global { put(g); }
    for l in local { put(l); }
    put(3 << 29 | 0xfffff);
    put(2 << 29); put(0);
    let mut cdm = vm.alloc_data(0x4000).unwrap();
    cdm.as_mut_slice()[..c.len()].copy_from_slice(&c);
    let mut q = Queue::new(&mut vm).unwrap();
    q.timeout = Duration::from_secs(120);
    let h = Instant::now();
    let r = q.run_compute(cdm.va, cdm.va + c.len() as u64);
    let host = h.elapsed().as_secs_f64();
    let counter = u32::from_le_bytes(table.as_slice()[0..4].try_into().unwrap());
    let simd_groups: u64 = (0..3).map(|i| (global[i] / local[i]) as u64).product::<u64>() * (local.iter().map(|&x| x as u64).product::<u64>()).div_ceil(32);
    match r {
        Ok(t) => println!("{{\"global\":{:?},\"local\":{:?},\"ok\":true,\"fw_ms\":{:.3},\"host_s\":{:.3},\"counter\":{},\"expected_if_x_lanes\":{}}}",
                          global, local, t.end.wrapping_sub(t.start) as f64 / 1e6, host, counter, simd_groups),
        Err(e) => println!("{{\"global\":{:?},\"local\":{:?},\"ok\":false,\"error\":\"{}\",\"host_s\":{:.3},\"counter\":{}}}", global, local, e, host, counter),
    }
}
