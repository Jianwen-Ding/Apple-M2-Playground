//! B36 / B45 probe (local, not part of ZLUDA). `b36_ipc DIR` with DIR holding writer.bin, reader.bin and count.bin.
//! B36: process P writes a shared buffer S on the GPU (writer: every lane stores WANT at S[8 + gid]), exports S as a
//! dma-buf and forks; the child opens its own render-node fd and VM, imports S, reads it on the GPU (reader:
//! out[8 + g] = S[g]) and then overwrites it on the GPU (count: S[8 + g] = g); P checks the child's writes on the CPU.
//! B45: S bound in two VMs of one fd. VM B reads it after VM A's writer (a) after a host wait, (b) through a fence
//! wait on B's queue, (c) with no ordering.
use agx_runtime::*;
use std::time::Duration;

const N: u32 = 4096;
const WANT: u32 = 0x10186a00;

struct Run { fence: Fence, _keep: Vec<Bo> }

fn launch(dev: &Device, vm: &mut Vm, q: &mut Queue, code: &[u8], out_va: u64, table_va: u64, wait_for: &[Fence]) -> std::io::Result<Run> {
    let mut unif = vm.alloc_data(0x1000)?;
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&u32::MAX.to_le_bytes());
    u[24..32].copy_from_slice(&out_va.to_le_bytes());
    u[32..40].copy_from_slice(&table_va.to_le_bytes());
    let mut usc = vm.alloc_usc(0x2000)?;
    let usc_off = (usc.va - vm.usc_base) as u32;
    let p = Pipeline { code: usc_off + 0x400, gpr_halves: 32, uniforms: vec![(0, 20, unif.va)], shared_bytes: 0 };
    let w = p.usc_words();
    usc.as_mut_slice()[..w.len()].copy_from_slice(&w);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(code);
    let c = cdm_dispatch(usc_off, p.uniform_halves(), dev.g14x(), [N, 1, 1], [256, 1, 1]);
    let mut cdm = vm.alloc_data(0x1000)?;
    cdm.as_mut_slice()[..c.len()].copy_from_slice(&c);
    let fence = q.submit_compute(cdm.va, cdm.va + c.len() as u64, wait_for)?;
    Ok(Run { fence, _keep: vec![unif, usc, cdm] })
}

fn word(b: &Bo, i: usize) -> u32 { u32::from_le_bytes(b.as_slice()[4 * i..4 * i + 4].try_into().unwrap()) }

fn main() {
    let dir = std::env::args().nth(1).unwrap();
    let rd = |n: &str| std::fs::read(format!("{dir}/{n}")).unwrap();
    let (writer, reader, count) = (rd("writer.bin"), rd("reader.bin"), rd("count.bin"));
    let t = Duration::from_secs(10);

    // ---- B36: across processes
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    let mut q = Queue::new(&mut vm).unwrap();
    let s = vm.alloc_data(0x10000).unwrap();
    let scratch = vm.alloc_data(0x4000).unwrap();
    let r = launch(&dev, &mut vm, &mut q, &writer, s.va, scratch.va, &[]).unwrap();
    q.wait(r.fence, t).unwrap();
    let wrote = (8..8 + N as usize).filter(|&i| word(&s, i) == WANT).count();
    let fd = s.export_dmabuf().unwrap();
    use std::os::fd::AsRawFd;
    let raw = fd.as_raw_fd();
    let pid = unsafe { libc::fork() };
    if pid == 0 {
        let res = std::panic::catch_unwind(|| {
            let dev2 = Device::open("/dev/dri/renderD128").unwrap();
            let mut vm2 = Vm::new(&dev2).unwrap();
            let mut q2 = Queue::new(&mut vm2).unwrap();
            let imp = vm2.import_dmabuf(raw, 0x10000).unwrap();
            let cpu_view = (8..8 + N as usize).filter(|&i| word(&imp, i) == WANT).count();
            let out = vm2.alloc_data(0x10000).unwrap();
            let tab = vm2.alloc_data(0x4000).unwrap();
            let r = launch(&dev2, &mut vm2, &mut q2, &reader, out.va, imp.va, &[]).unwrap();
            q2.wait(r.fence, t).unwrap();
            let gpu_read = (8..N as usize).filter(|&g| word(&out, 8 + g) == WANT).count();
            let r = launch(&dev2, &mut vm2, &mut q2, &count, imp.va, tab.va, &[]).unwrap();
            q2.wait(r.fence, t).unwrap();
            println!("{{\"b36_child\":true,\"import_va\":\"{:#x}\",\"cpu_view_ok\":{cpu_view},\"gpu_read_ok\":{gpu_read},\"of\":{}}}", imp.va, N - 8);
        });
        unsafe { libc::_exit(if res.is_ok() { 0 } else { 1 }) };
    }
    let mut st = 0;
    unsafe { libc::waitpid(pid, &mut st, 0) };
    let child_writes = (0..N as usize).filter(|&g| word(&s, 8 + g) == g as u32).count();
    println!("{{\"b36_parent\":true,\"writer_ok\":{wrote},\"child_status\":{st},\"child_gpu_writes_seen_by_parent_cpu\":{child_writes},\"of\":{N}}}");

    // ---- B45: one buffer in two VMs of one fd
    let mut vmb = Vm::new(&dev).unwrap();
    let mut qb = Queue::new(&mut vmb).unwrap();
    let sb = vmb.import_dmabuf(raw, 0x10000).unwrap();      // same fd: the same GEM object, bound in VM B
    for case in ["host_wait", "fence_wait", "unordered"] {
        let mut sa = s.as_slice().to_vec(); sa.fill(0);
        unsafe { std::ptr::write_bytes(s.as_slice().as_ptr() as *mut u8, 0, s.size as usize) };
        let outb = vmb.alloc_data(0x10000).unwrap();
        let ra = launch(&dev, &mut vm, &mut q, &writer, s.va, scratch.va, &[]).unwrap();
        let rb = match case {
            "host_wait" => { q.wait(ra.fence, t).unwrap(); launch(&dev, &mut vmb, &mut qb, &reader, outb.va, sb.va, &[]).unwrap() }
            "fence_wait" => launch(&dev, &mut vmb, &mut qb, &reader, outb.va, sb.va, &[ra.fence]).unwrap(),
            _ => launch(&dev, &mut vmb, &mut qb, &reader, outb.va, sb.va, &[]).unwrap(),
        };
        qb.wait(rb.fence, t).unwrap();
        q.wait(ra.fence, t).unwrap();
        let seen = (8..N as usize).filter(|&g| word(&outb, 8 + g) == WANT).count();
        let (a0, a1) = q.timing(ra.fence).unwrap_or((0, 0));
        let (b0, b1) = qb.timing(rb.fence).unwrap_or((0, 0));
        println!("{{\"b45\":\"{case}\",\"vm_a\":{},\"vm_b\":{},\"b_saw_writes\":{seen},\"of\":{},\"a_us\":[0,{:.1}],\"b_us\":[{:.1},{:.1}]}}",
                 vm.id, vmb.id, N - 8, (a1 - a0) as f64 / 1e3, (b0 as i64 - a0 as i64) as f64 / 1e3, (b1 as i64 - a0 as i64) as f64 / 1e3);
    }
    std::mem::forget(sb);   // same GEM handle as `s`: let `s` close it
}
