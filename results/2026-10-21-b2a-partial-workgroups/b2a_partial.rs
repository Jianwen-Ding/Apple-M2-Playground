//! B2a probe (local, not part of ZLUDA): launch CODE (every lane atomically adds 1 to table word 0 and stores its gid at
//! out[8 + gid]) with a global size that need not be a multiple of the local size, building the CDM stream by hand.
//! `b2a_partial CODE GX GY GZ LX LY LZ` prints the fence result, the counter and which gids were written.
use agx_runtime::*;
use std::time::Duration;

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let code = std::fs::read(&a[1]).unwrap();
    let n: Vec<u32> = a[2..8].iter().map(|s| s.parse().unwrap()).collect();
    let (global, local) = ([n[0], n[1], n[2]], [n[3], n[4], n[5]]);
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    let mut out = vm.alloc_data(0x40000).unwrap();
    for w in out.as_mut_slice().chunks_mut(4) { w.copy_from_slice(&0xcdcdcdcdu32.to_le_bytes()); }
    let table = vm.alloc_data(0x4000).unwrap();
    let mut unif = vm.alloc_data(0x4000).unwrap();
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&u32::MAX.to_le_bytes());          // u5 = count: every gid passes the bounds check
    u[24..32].copy_from_slice(&out.va.to_le_bytes());             // u6_u7 = output
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
    q.timeout = Duration::from_secs(10);
    let r = q.run_compute(cdm.va, cdm.va + c.len() as u64);
    let counter = u32::from_le_bytes(table.as_slice()[0..4].try_into().unwrap());
    let o = out.as_slice();
    let words = o.len() / 4 - 8;
    let (mut written, mut wrong, mut last) = (0u32, 0u32, -1i64);
    for i in 0..words {
        let v = u32::from_le_bytes(o[4 * (8 + i)..4 * (9 + i)].try_into().unwrap());
        if v != 0xcdcdcdcd { written += 1; last = i as i64; if v != i as u32 { wrong += 1; } }
    }
    let status = match r { Ok(t) => format!("\"ok\":true,\"fw_us\":{:.1},\"ts_valid\":{}", t.end.wrapping_sub(t.start) as f64 / 1e3, t.start != 0 && t.end > t.start),
                           Err(e) => format!("\"ok\":false,\"error\":\"{}\"", e) };
    println!("{{\"global\":{:?},\"local\":{:?},{},\"counter\":{},\"written\":{},\"last_gid\":{},\"wrong\":{}}}",
             global, local, status, counter, written, last, wrong);
}
