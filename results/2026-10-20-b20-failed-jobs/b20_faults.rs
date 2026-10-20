//! B20 probe (local, not part of ZLUDA): how a failed compute command is reported, and what still works after it.
//! `b20_faults MODE` with MODE = store39 (control kernel storing to VA 2^39, unbound), op54 (undecoded opcode 0x54,
//! a recovered fault in the 2026-10-11 scan) or jumpout (jmp_exec_any +1 GiB, into unmapped USC space).
//! Sequence: control on queue A; MODE on queue A; control on queue A; control on a new queue B (same VM);
//! control on a new VM; then on a new queue C: MODE and control submitted back to back without waiting, each
//! fence waited and reported separately.
use agx_runtime::*;
use std::time::{Duration, Instant};

const CONTROL: &str = "f20510040e05c2865800000062000000522842a218006209785634120e0508206400000045112c0e00c012003800520e000000008800";
const N: u32 = 256;

struct Kern { usc: Bo, unif: Bo, cdm: Bo, out: Bo, len: u64 }

fn kernel(dev: &Device, vm: &mut Vm, body: Option<&[u8]>, out_va_override: Option<u64>) -> Kern {
    let control: Vec<u8> = (0..CONTROL.len() / 2).map(|i| u8::from_str_radix(&CONTROL[2 * i..2 * i + 2], 16).unwrap()).collect();
    let mut code = control[..22].to_vec();
    code.extend_from_slice(body.unwrap_or(&control[22..28]));
    code.extend_from_slice(&control[28..]);
    let mut out = vm.alloc_data(0x4000).unwrap();
    for w in out.as_mut_slice().chunks_mut(4) { w.copy_from_slice(&0xcdcdcdcdu32.to_le_bytes()); }
    let mut unif = vm.alloc_data(0x4000).unwrap();
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&N.to_le_bytes());
    u[24..32].copy_from_slice(&out_va_override.unwrap_or(out.va).to_le_bytes());
    let mut usc = vm.alloc_usc(0x1000).unwrap();
    let usc_off = (usc.va - vm.usc_base) as u32;
    let p = Pipeline { code: usc_off + 0x400, gpr_halves: 16, uniforms: vec![(0, 16, unif.va)], shared_bytes: 0 };
    let words = p.usc_words();
    usc.as_mut_slice()[..words.len()].copy_from_slice(&words);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(&code);
    let stream = cdm_dispatch(usc_off, p.uniform_halves(), dev.g14x(), [N, 1, 1], [32, 1, 1]);
    let mut cdm = vm.alloc_data(0x4000).unwrap();
    cdm.as_mut_slice()[..stream.len()].copy_from_slice(&stream);
    Kern { usc, unif, cdm, out, len: stream.len() as u64 }
}

fn control_ok(k: &Kern) -> bool {
    let o = k.out.as_slice();
    (0..N as usize).all(|i| u32::from_le_bytes(o[4 * (8 + i)..4 * (8 + i) + 4].try_into().unwrap()) == 0x12345678)
}

fn run(name: &str, q: &mut Queue, k: &Kern, check: bool) {
    let h = Instant::now();
    let r = q.run_compute(k.cdm.va, k.cdm.va + k.len);
    let ms = h.elapsed().as_secs_f64() * 1e3;
    match r {
        Ok(t) => println!("{{\"step\":\"{}\",\"ok\":true,\"fw_ticks\":{},\"host_ms\":{:.2}{}}}", name, t.end.wrapping_sub(t.start), ms,
                          if check { format!(",\"output_ok\":{}", control_ok(k)) } else { String::new() }),
        Err(e) => println!("{{\"step\":\"{}\",\"ok\":false,\"error\":\"{}\",\"errno\":{:?},\"cuda\":{},\"host_ms\":{:.2}}}", name,
                           e.to_string().replace('"', "'"), error::errno(&e), error::cuda_error(&e), ms),
    }
}

fn main() {
    let mode = std::env::args().nth(1).expect("mode");
    let body: Vec<u8> = match mode.as_str() {
        "store39" => vec![0x62, 0x09, 0x78, 0x56, 0x34, 0x12],
        "op54" => vec![0x54, 0x09, 0x38, 0x00, 0x38, 0x00, 0x38, 0x00],
        "jumpout" => vec![0x00, 0xc0, 0x00, 0x00, 0x00, 0x40],
        _ => panic!("mode"),
    };
    let out39 = (mode == "store39").then_some(1u64 << 39);
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    println!("{{\"mode\":\"{}\",\"features\":{}}}", mode, dev.params.features);
    let mut vm = Vm::new(&dev).unwrap();
    let c1 = kernel(&dev, &mut vm, None, None);
    let f = kernel(&dev, &mut vm, Some(&body), out39);
    let c2 = kernel(&dev, &mut vm, None, None);
    let c3 = kernel(&dev, &mut vm, None, None);
    let mut qa = Queue::new(&mut vm).unwrap();
    qa.timeout = Duration::from_secs(10);
    run("control_before", &mut qa, &c1, true);
    run("fault", &mut qa, &f, false);
    run("control_same_queue", &mut qa, &c2, true);
    let mut qb = Queue::new(&mut vm).unwrap();
    qb.timeout = Duration::from_secs(10);
    run("control_new_queue_same_vm", &mut qb, &c3, true);
    {
        let mut vm2 = Vm::new(&dev).unwrap();
        let c4 = kernel(&dev, &mut vm2, None, None);
        let mut q2 = Queue::new(&mut vm2).unwrap();
        q2.timeout = Duration::from_secs(10);
        run("control_new_vm", &mut q2, &c4, true);
    }
    // back-to-back on a fresh queue: per-command fence status
    let f2 = kernel(&dev, &mut vm, Some(&body), out39);
    let c5 = kernel(&dev, &mut vm, None, None);
    let mut qc = Queue::new(&mut vm).unwrap();
    let ff = qc.submit_compute(f2.cdm.va, f2.cdm.va + f2.len, &[]).unwrap();
    let fc = qc.submit_compute(c5.cdm.va, c5.cdm.va + c5.len, &[]).unwrap();
    let rf = qc.wait(ff, Duration::from_secs(10));
    let rc = qc.wait(fc, Duration::from_secs(10));
    let s = |r: &std::io::Result<()>| match r { Ok(()) => "ok".to_string(), Err(e) => format!("{} (errno {:?})", e, error::errno(e)).replace('"', "'") };
    println!("{{\"step\":\"back_to_back\",\"fault_fence\":\"{}\",\"control_fence\":\"{}\",\"control_output_ok\":{}}}", s(&rf), s(&rc), control_ok(&c5));
    let _ = (&c1.usc, &c1.unif, &f.usc, &f.unif);
}
