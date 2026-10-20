//! B8 probe (local, not part of ZLUDA): rewrite shader code and pipeline words in place at one USC address and
//! check that every launch runs the code written just before it.
//!
//! The kernel is the pinned control main (`mov_imm r2, IMM` stored to out[8 + i]); each iteration writes a new
//! immediate (tag << 16 | iteration), so stale code shows up as a stale value. Even iterations use 16 GPR halves and
//! 16 uniform halves, odd ones 24 GPR halves and 42 uniform halves, so the pipeline words change too.
//! `b8_code_reuse ITERS BARRIER` with BARRIER = 1 (Mesa's stream barrier with the USC cache invalidate after the
//! launch, as agx_runtime emits) or 0 (no barrier word: launch, then terminate).
use agx_runtime::*;
use std::time::Duration;

const CONTROL: &str = "f20510040e05c2865800000062000000522842a218006209785634120e0508206400000045112c0e00c012003800520e000000008800";

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let iters: u32 = a.get(1).map_or(1000, |s| s.parse().unwrap());
    let barrier = a.get(2).map_or(true, |s| s != "0");
    let code: Vec<u8> = (0..CONTROL.len() / 2).map(|i| u8::from_str_radix(&CONTROL[2 * i..2 * i + 2], 16).unwrap()).collect();
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    const N: usize = 256;
    let mut out = vm.alloc_data(0x4000).unwrap();
    let mut unif = vm.alloc_data(0x4000).unwrap();
    let mut usc = vm.alloc_usc(0x1000).unwrap();
    let usc_off = (usc.va - vm.usc_base) as u32;
    let mut cdm = vm.alloc_data(0x4000).unwrap();
    let mut queue = Queue::new(&mut vm).unwrap();
    queue.timeout = Duration::from_secs(5);
    let (mut bad, mut stale) = (0u32, 0u32);
    let mut ns = Vec::new();
    for it in 0..iters {
        let odd = it % 2 == 1;
        let imm: u32 = (if odd { 0x2222u32 } else { 0x1111 }) << 16 | (it & 0xffff);
        // uniforms: u4 = 0 (offset), u5 = N (count), u6_u7 = output VA; odd iterations preload up to u20
        let u = unif.as_mut_slice();
        u[16..20].copy_from_slice(&0u32.to_le_bytes());
        u[20..24].copy_from_slice(&(N as u32).to_le_bytes());
        u[24..32].copy_from_slice(&out.va.to_le_bytes());
        let n_halves = if odd { 42 } else { 16 };
        let pipeline = Pipeline {
            code: usc_off + 0x400,
            gpr_halves: if odd { 24 } else { 16 },
            uniforms: vec![(0, n_halves, unif.va)],
            shared_bytes: 0,
        };
        let words = pipeline.usc_words();
        let s = usc.as_mut_slice();
        s[..0x400].fill(0);
        s[..words.len()].copy_from_slice(&words);
        let mut c = code.clone();
        c[24..28].copy_from_slice(&imm.to_le_bytes());
        s[0x400..0x400 + c.len()].copy_from_slice(&c);
        let o = out.as_mut_slice();
        for w in o.chunks_mut(4) { w.copy_from_slice(&0xcdcdcdcdu32.to_le_bytes()); }
        let mut stream = cdm_dispatch(usc_off, pipeline.uniform_halves(), dev.g14x(), [N as u32, 1, 1], [32, 1, 1]);
        if !barrier {
            // drop the barrier word (3 << 29 | 0xfffff), keep launch + terminate
            let pos = stream.chunks(4).position(|w| u32::from_le_bytes(w.try_into().unwrap()) == (3 << 29 | 0xfffff)).unwrap() * 4;
            stream.drain(pos..pos + 4);
        }
        cdm.as_mut_slice()[..stream.len()].copy_from_slice(&stream);
        let t = queue.run_compute(cdm.va, cdm.va + stream.len() as u64).unwrap();
        ns.push(t.end.wrapping_sub(t.start));
        let o = out.as_slice();
        let prev: u32 = (if odd { 0x1111u32 } else { 0x2222 }) << 16 | (it.wrapping_sub(1) & 0xffff);
        for i in 0..N {
            let v = u32::from_le_bytes(o[4 * (8 + i)..4 * (8 + i) + 4].try_into().unwrap());
            if v != imm { bad += 1; if it > 0 && v == prev { stale += 1; } }
        }
        if std::env::var("B8_DEBUG").is_ok() {
            let v = |i: usize| u32::from_le_bytes(o[4 * i..4 * i + 4].try_into().unwrap());
            println!("it {} imm {:#x} out[8] {:#x} out[9] {:#x} out[263] {:#x} words {:02x?}", it, imm, v(8), v(9), v(263), &words);
        }
    }
    ns.sort();
    println!("{{\"iters\":{},\"barrier\":{},\"threads\":{},\"bad_words\":{},\"stale_words\":{},\"fw_ticks_median\":{}}}",
             iters, barrier, N, bad, stale, ns[ns.len() / 2]);
}
