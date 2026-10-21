//! B38 probe (local, not part of ZLUDA): `b38_limits CODE V Q` creates V VMs with Q queues each (all alive together),
//! submits one 64-lane launch of CODE (every lane adds 1 to its own table word 0, stores SR21 at out[8 + gid]) on every
//! queue without waiting, then waits for all. Prints how many VMs / queues were created (and the first error), how many
//! launches gave the right count, the distinct SR21 values and the wall time.
use agx_runtime::*;
use std::collections::BTreeSet;
use std::time::{Duration, Instant};

struct Launch { out: Bo, table: Bo, _unif: Bo, _cdm: Bo, _usc: Bo, fence: Fence, q: usize }

fn launch(dev: &Device, vm: &mut Vm, code: &[u8], q: &mut Queue, qi: usize) -> std::io::Result<Launch> {
    let out = vm.alloc_data(0x1000)?;
    let table = vm.alloc_data(0x1000)?;
    let mut unif = vm.alloc_data(0x1000)?;
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&u32::MAX.to_le_bytes());
    u[24..32].copy_from_slice(&out.va.to_le_bytes());
    u[32..40].copy_from_slice(&table.va.to_le_bytes());
    // the pipeline words carry the uniform buffer's address, so each launch has its own
    let mut usc = vm.alloc_usc(0x1000)?;
    let usc_off = (usc.va - vm.usc_base) as u32;
    let p = Pipeline { code: usc_off + 0x400, gpr_halves: 32, uniforms: vec![(0, 20, unif.va)], shared_bytes: 0 };
    let words = p.usc_words();
    usc.as_mut_slice()[..words.len()].copy_from_slice(&words);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(code);
    let c = cdm_dispatch(usc_off, p.uniform_halves(), dev.g14x(), [64, 1, 1], [32, 1, 1]);
    let mut cdm = vm.alloc_data(0x1000)?;
    cdm.as_mut_slice()[..c.len()].copy_from_slice(&c);
    let fence = q.submit_compute(cdm.va, cdm.va + c.len() as u64, &[])?;
    Ok(Launch { out, table, _unif: unif, _cdm: cdm, _usc: usc, fence, q: qi })
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let code = std::fs::read(&a[1]).unwrap();
    let (nv, nq): (usize, usize) = (a[2].parse().unwrap(), a[3].parse().unwrap());
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let t0 = Instant::now();
    let mut vms: Vec<Vm> = Vec::new();
    let mut queues: Vec<(usize, Queue)> = Vec::new();
    let mut first_err: Option<String> = None;
    'outer: for v in 0..nv {
        let mut vm = match Vm::new(&dev) { Ok(vm) => vm, Err(e) => { first_err = Some(format!("vm {v}: {e}")); break } };
        for qi in 0..nq {
            match Queue::new(&mut vm) {
                Ok(mut q) => { q.timeout = Duration::from_secs(10); queues.push((v, q)) }
                Err(e) => { first_err = Some(format!("vm {v} queue {qi}: {e}")); vms.push(vm); break 'outer }
            }
        }
        vms.push(vm);
    }
    let created = (vms.len(), queues.len());
    let mut launches = Vec::new();
    let mut launch_err: Option<String> = None;
    for (qi, (v, q)) in queues.iter_mut().enumerate() {
        match launch(&dev, &mut vms[*v], &code, q, qi) { Ok(l) => launches.push(l), Err(e) => { launch_err = Some(format!("launch {qi}: {e}")); break } }
    }
    let (mut ok, mut bad, mut failed) = (0, 0, 0);
    let mut slots = BTreeSet::new();
    let mut per_vm_slot: Vec<BTreeSet<u32>> = vec![BTreeSet::new(); vms.len()];
    for l in &launches {
        let (v, q) = &queues[l.q];
        if q.wait(Fence { syncobj: l.fence.syncobj, point: l.fence.point }, Duration::from_secs(10)).is_err() { failed += 1; continue }
        let n = u32::from_le_bytes(l.table.as_slice()[0..4].try_into().unwrap());
        let s = u32::from_le_bytes(l.out.as_slice()[32..36].try_into().unwrap());
        slots.insert(s); per_vm_slot[*v].insert(s);
        if n == 64 { ok += 1 } else { bad += 1 }
    }
    let multi = per_vm_slot.iter().filter(|s| s.len() > 1).count();
    println!("{{\"want_vms\":{nv},\"want_queues_per_vm\":{nq},\"vms\":{},\"queues\":{},\"create_error\":{:?},\"launch_error\":{:?},\"ok\":{ok},\"wrong\":{bad},\"wait_failed\":{failed},\"distinct_sr21\":{},\"sr21\":{:?},\"vms_with_several_slots\":{multi},\"wall_ms\":{:.1}}}",
             created.0, created.1, first_err, launch_err, slots.len(), slots.iter().take(80).collect::<Vec<_>>(), t0.elapsed().as_secs_f64() * 1e3);
}
