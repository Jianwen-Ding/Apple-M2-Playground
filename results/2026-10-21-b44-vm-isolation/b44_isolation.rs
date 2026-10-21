//! B44 probe (local, not part of ZLUDA): `b44_isolation DIR LAYOUT` (LAYOUT = vms | queues). VM A (or queue A) runs a
//! disturbance while B runs a stream of 20 control kernels (each its own buffers; every lane must write 0x12345678),
//! submitted right behind A without waiting. Cases: none (B alone, the baseline), op54 (an instruction fault, B20) and
//! deadlock (B26's over-budget barrier, ended by the firmware after ~0.5 s). Times are GPU ns from GET_TIME taken just
//! before A's submit; a command whose timestamps stay 0 faulted.
use agx_runtime::*;
use std::time::Duration;

struct K { _usc: Bo, _unif: Bo, cdm: Bo, out: Bo, len: u64, n: u32 }

fn kernel(dev: &Device, vm: &mut Vm, code: &[u8], n: u32, wg: u32, halves: u32) -> K {
    let mut out = vm.alloc_data(0x4000.max(4 * (n as u64 + 64))).unwrap();
    for w in out.as_mut_slice().chunks_mut(4) { w.copy_from_slice(&0xcdcdcdcdu32.to_le_bytes()); }
    let mut unif = vm.alloc_data(0x4000).unwrap();
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&n.to_le_bytes());
    u[24..32].copy_from_slice(&out.va.to_le_bytes());
    let mut usc = vm.alloc_usc(0x1000).unwrap();
    let off = (usc.va - vm.usc_base) as u32;
    let p = Pipeline { code: off + 0x400, gpr_halves: halves, uniforms: vec![(0, 16, unif.va)], shared_bytes: 0 };
    let w = p.usc_words();
    usc.as_mut_slice()[..w.len()].copy_from_slice(&w);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(code);
    let s = cdm_dispatch(off, p.uniform_halves(), dev.g14x(), [n, 1, 1], [wg, 1, 1]);
    let mut cdm = vm.alloc_data(0x4000).unwrap();
    cdm.as_mut_slice()[..s.len()].copy_from_slice(&s);
    K { _usc: usc, _unif: unif, cdm, out, len: s.len() as u64, n }
}

fn control_ok(k: &K) -> bool {
    let o = k.out.as_slice();
    (0..k.n as usize).all(|i| u32::from_le_bytes(o[4 * (8 + i)..4 * (9 + i)].try_into().unwrap()) == 0x12345678)
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let dir = &a[1];
    let layout = a[2].as_str();
    let rd = |n: &str| std::fs::read(format!("{dir}/{n}")).unwrap();
    let (control, op54, deadlock) = (rd("control.bin"), rd("op54.bin"), rd("deadlock.bin"));
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    for case in ["none", "op54", "deadlock", "none"] {
        let mut vma = Vm::new(&dev).unwrap();
        let mut vmb_own = if layout == "vms" { Some(Vm::new(&dev).unwrap()) } else { None };
        let ka = match case {
            "op54" => Some(kernel(&dev, &mut vma, &op54, 256, 32, 16)),
            "deadlock" => Some(kernel(&dev, &mut vma, &deadlock, 1024, 1024, 112)),
            _ => None,
        };
        let mut qa = Queue::new(&mut vma).unwrap();
        qa.timeout = Duration::from_secs(10);
        let vmb: &mut Vm = vmb_own.as_mut().unwrap_or(&mut vma);
        let kb: Vec<K> = (0..20).map(|_| kernel(&dev, vmb, &control, 256, 32, 16)).collect();
        let mut qb = Queue::new(vmb).unwrap();
        qb.timeout = Duration::from_secs(10);
        let t0 = dev.gpu_time().unwrap();
        let fa = ka.as_ref().map(|k| qa.submit_compute(k.cdm.va, k.cdm.va + k.len, &[]).unwrap());
        let fb: Vec<Fence> = kb.iter().map(|k| qb.submit_compute(k.cdm.va, k.cdm.va + k.len, &[]).unwrap()).collect();
        let mut b_ok = 0;
        let mut b_times = Vec::new();
        let mut b_err = 0;
        for (k, f) in kb.iter().zip(&fb) {
            match qb.wait(*f, Duration::from_secs(10)) { Ok(()) => {}, Err(_) => b_err += 1 }
            if control_ok(k) { b_ok += 1 }
            if let Some((s, e)) = qb.timing(*f) { b_times.push(((s as i64 - t0 as i64) / 1000, (e as i64 - t0 as i64) / 1000)); }
        }
        let a_res = fa.map(|f| {
            let w = qa.wait(f, Duration::from_secs(10)).map_err(|e| e.to_string());
            let t = qa.timing(f).unwrap_or((0, 0));
            format!("{{\"wait\":{:?},\"ts_us\":[{},{}]}}", w, if t.0 == 0 { 0 } else { (t.0 as i64 - t0 as i64) / 1000 }, if t.1 == 0 { 0 } else { (t.1 as i64 - t0 as i64) / 1000 })
        }).unwrap_or("null".into());
        let host_after = (dev.gpu_time().unwrap() as i64 - t0 as i64) / 1000;
        println!("{{\"layout\":\"{layout}\",\"case\":\"{case}\",\"a\":{a_res},\"b_correct\":{b_ok},\"b_wait_errors\":{b_err},\"b_first_us\":{:?},\"b_last_us\":{:?},\"done_after_us\":{host_after}}}",
                 b_times.first(), b_times.last());
    }
}
