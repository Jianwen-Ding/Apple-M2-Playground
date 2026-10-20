//! B8 probe (local, not part of ZLUDA): one straight-line shader of SIZE MiB.
//! Control main with its `mov_imm r2, IMM` replaced by `mov_imm r2, 0` + N x `iadd r2, r2.sx, 1`; every thread
//! must store N. `b8_big_code SIZE_MIB [SKIP_MIB]`: SKIP_MIB of USC heap is allocated first, so the shader starts
//! that far into the 4 GiB USC range (its 32-bit code address grows).
use agx_runtime::*;
use std::time::{Duration, Instant};

const CONTROL: &str = "f20510040e05c2865800000062000000522842a218006209785634120e0508206400000045112c0e00c012003800520e000000008800";

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let mib: u64 = a.get(1).map_or(1, |s| s.parse().unwrap());
    let skip: u64 = a.get(2).map_or(0, |s| s.parse().unwrap());
    let control: Vec<u8> = (0..CONTROL.len() / 2).map(|i| u8::from_str_radix(&CONTROL[2 * i..2 * i + 2], 16).unwrap()).collect();
    let n = ((mib << 20) / 8) as u32;
    let mut code = control[..22].to_vec();
    code.extend_from_slice(&[0x62, 0x09, 0, 0, 0, 0]); // mov_imm r2, 0
    for _ in 0..n { code.extend_from_slice(&[0x0e, 0x09, 0x44, 0x16, 0, 0, 0, 0]); } // iadd r2, r2.sx, 1
    code.extend_from_slice(&control[28..]);
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    let _filler = if skip > 0 { Some(vm.alloc_usc(skip << 20).unwrap()) } else { None };
    const N: usize = 256;
    let out = vm.alloc_data(0x4000).unwrap();
    let mut unif = vm.alloc_data(0x4000).unwrap();
    let mut usc = vm.alloc_usc(0x400 + code.len() as u64 + 64).unwrap();
    let usc_off = (usc.va - vm.usc_base) as u32;
    let mut cdm = vm.alloc_data(0x4000).unwrap();
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&(N as u32).to_le_bytes());
    u[24..32].copy_from_slice(&out.va.to_le_bytes());
    let pipeline = Pipeline { code: usc_off + 0x400, gpr_halves: 16, uniforms: vec![(0, 16, unif.va)], shared_bytes: 0 };
    let words = pipeline.usc_words();
    usc.as_mut_slice()[..words.len()].copy_from_slice(&words);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(&code);
    let stream = cdm_dispatch(usc_off, pipeline.uniform_halves(), dev.g14x(), [N as u32, 1, 1], [32, 1, 1]);
    cdm.as_mut_slice()[..stream.len()].copy_from_slice(&stream);
    let mut queue = Queue::new(&mut vm).unwrap();
    queue.timeout = Duration::from_secs(20);
    let h = Instant::now();
    let t = queue.run_compute(cdm.va, cdm.va + stream.len() as u64);
    let host_ms = h.elapsed().as_secs_f64() * 1e3;
    match t {
        Ok(t) => {
            let o = out.as_slice();
            let bad = (0..N).filter(|&i| u32::from_le_bytes(o[4 * (8 + i)..4 * (8 + i) + 4].try_into().unwrap()) != n).count();
            println!("{{\"mib\":{},\"code_bytes\":{},\"code_usc_offset\":{},\"iadds\":{},\"bad\":{},\"first\":{},\"fw_ticks\":{},\"host_ms\":{:.1}}}",
                     mib, code.len(), usc_off + 0x400, n, bad, u32::from_le_bytes(o[32..36].try_into().unwrap()), t.end.wrapping_sub(t.start), host_ms);
        }
        Err(e) => println!("{{\"mib\":{},\"error\":\"{}\",\"host_ms\":{:.1}}}", mib, e, host_ms),
    }
}
