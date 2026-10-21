//! B42 probe (local, not part of ZLUDA): `b42_teardown vectoradd.o CYCLES`. Phase 1: CYCLES x (cuCtxCreate,
//! cuModuleLoadData, 3 x cuMemAlloc, launch vectorAdd, cuCtxSynchronize, check, cuCtxDestroy), sampling MemAvailable,
//! the process's open fds and the cgroup's shmem. Phase 2: 100 x (create, queue 200 launches without waiting,
//! cuCtxDestroy at once), timing the destroy. Phase 3: 100 x (primary context, queue 200 launches, cuDevicePrimaryCtxReset).
//! Prints JSON lines.
use cuda_types::cuda::*;
use nvcuda_agx::*;
use std::ffi::c_void;
use std::ptr::null_mut;
use std::time::Instant;

fn ok(what: &str, r: CUresult) -> bool {
    if let Err(e) = r { println!("{{\"error\":\"{what}: {}\"}}", e.0); false } else { true }
}
fn meminfo(key: &str, file: &str) -> u64 {
    std::fs::read_to_string(file).ok().and_then(|s| s.lines().find(|l| l.starts_with(key))
        .and_then(|l| l.split_whitespace().nth(1)).and_then(|v| v.parse().ok())).unwrap_or(0)
}
fn sample(tag: &str, i: usize) {
    let fds = std::fs::read_dir("/proc/self/fd").map(|d| d.count()).unwrap_or(0);
    println!("{{\"{tag}\":{i},\"mem_avail_mib\":{},\"rss_mib\":{},\"fds\":{fds},\"cgroup_shmem_mib\":{}}}",
             meminfo("MemAvailable:", "/proc/meminfo") / 1024, meminfo("VmRSS:", "/proc/self/status") / 1024,
             meminfo("shmem ", "/sys/fs/cgroup/memory.stat") >> 20);
}

const N: i32 = 50_000;

unsafe fn load(image: &[u8]) -> Option<(CUmodule, CUfunction)> {
    let mut m = CUmodule(null_mut());
    if !ok("cuModuleLoadData", cuModuleLoadData(&mut m, image.as_ptr() as *const c_void)) { return None }
    let mut f = CUfunction(null_mut());
    if !ok("cuModuleGetFunction", cuModuleGetFunction(&mut f, m, c"_Z9vectorAddPKfS0_Pfi".as_ptr())) { return None }
    Some((m, f))
}

/// Allocates A, B, C, queues `launches` vectorAdds; with `check`, synchronizes and returns the wrong count.
unsafe fn work(f: CUfunction, launches: usize, check: bool) -> Option<usize> {
    let bytes = N as usize * 4;
    let a: Vec<f32> = (0..N).map(|i| i as f32).collect();
    let b: Vec<f32> = (0..N).map(|i| 2.0 * i as f32).collect();
    let (mut da, mut db, mut dc) = (CUdeviceptr_v2(null_mut()), CUdeviceptr_v2(null_mut()), CUdeviceptr_v2(null_mut()));
    for d in [&mut da, &mut db, &mut dc] { if !ok("cuMemAlloc", cuMemAlloc_v2(d, bytes)) { return None } }
    ok("cuMemcpyHtoD", cuMemcpyHtoD_v2(da, a.as_ptr() as *const c_void, bytes));
    ok("cuMemcpyHtoD", cuMemcpyHtoD_v2(db, b.as_ptr() as *const c_void, bytes));
    let mut p: [*mut c_void; 4] = [&mut da as *mut _ as *mut c_void, &mut db as *mut _ as *mut c_void, &mut dc as *mut _ as *mut c_void, &N as *const i32 as *mut c_void];
    for _ in 0..launches {
        if !ok("cuLaunchKernel", cuLaunchKernel(f, (N as u32).div_ceil(256), 1, 1, 256, 1, 1, 0, CUstream(null_mut()), p.as_mut_ptr(), null_mut())) { return None }
    }
    if !check { return Some(0) }
    if !ok("cuCtxSynchronize", cuCtxSynchronize()) { return None }
    let mut c = vec![0f32; N as usize];
    ok("cuMemcpyDtoH", cuMemcpyDtoH_v2(c.as_mut_ptr() as *mut c_void, dc, bytes));
    Some((0..N as usize).filter(|&i| c[i] != 3.0 * i as f32).count())
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let image = std::fs::read(&a[1]).unwrap();
    let cycles: usize = a[2].parse().unwrap();
    unsafe {
        ok("cuInit", cuInit(0));
        let mut dev = 0;
        ok("cuDeviceGet", cuDeviceGet(&mut dev, 0));
        let phases = std::env::var("B42_PHASES").unwrap_or("0123".into());
        // phase 0: 200 queued launches, then an ordinary synchronize and check (no teardown involved)
        if phases.contains('0') {
            let mut ctx = CUcontext(null_mut());
            ok("cuCtxCreate", cuCtxCreate_v2(&mut ctx, 0, dev));
            let q: usize = std::env::var("B42_Q").ok().and_then(|v| v.parse().ok()).unwrap_or(200);
            let r = load(&image).and_then(|(_, f)| work(f, q, true));
            println!("{{\"phase0_200_queued_then_sync\":{:?}}}", r);
            ok("cuCtxDestroy", cuCtxDestroy_v2(ctx));
        }
        // phase 1
        let (mut wrong, mut failed) = (0usize, 0usize);
        let t = Instant::now();
        for i in 0..if phases.contains('1') { cycles } else { 0 } {
            if i == 0 || i == 10 || i == cycles / 2 || i == cycles - 1 { sample("p1_cycle", i) }
            let mut ctx = CUcontext(null_mut());
            if !ok("cuCtxCreate", cuCtxCreate_v2(&mut ctx, 0, dev)) { failed += 1; continue }
            match load(&image).and_then(|(_, f)| work(f, 1, true)) { Some(w) => wrong += w, None => failed += 1 }
            if !ok("cuCtxDestroy", cuCtxDestroy_v2(ctx)) { failed += 1 }
        }
        let n1 = if phases.contains('1') { cycles } else { 0 };
        println!("{{\"phase1_cycles\":{n1},\"wrong\":{wrong},\"failed\":{failed},\"ms_per_cycle\":{:.2}}}", t.elapsed().as_secs_f64() * 1e3 / n1.max(1) as f64);
        sample("p1_end", cycles);
        // phase 2: destroy with work queued
        let (mut failed2, mut dmax, mut dsum) = (0usize, 0f64, 0f64);
        for _ in 0..if phases.contains('2') { 100 } else { 0 } {
            let mut ctx = CUcontext(null_mut());
            if !ok("cuCtxCreate", cuCtxCreate_v2(&mut ctx, 0, dev)) { failed2 += 1; continue }
            if load(&image).and_then(|(_, f)| work(f, 200, false)).is_none() { failed2 += 1 }
            let t = Instant::now();
            if !ok("cuCtxDestroy", cuCtxDestroy_v2(ctx)) { failed2 += 1 }
            let d = t.elapsed().as_secs_f64() * 1e3; dsum += d; dmax = dmax.max(d);
        }
        println!("{{\"phase2_destroy_with_200_queued\":100,\"failed\":{failed2},\"destroy_ms_mean\":{:.2},\"destroy_ms_max\":{dmax:.2}}}", dsum / 100.0);
        sample("p2_end", 100);
        // phase 3: primary context reset with work queued, then a checked launch in the fresh primary context
        let (mut failed3, mut wrong3) = (0usize, 0usize);
        for _ in 0..if phases.contains('3') { 100 } else { 0 } {
            let mut ctx = CUcontext(null_mut());
            if !ok("cuDevicePrimaryCtxRetain", cuDevicePrimaryCtxRetain(&mut ctx, dev)) { failed3 += 1; continue }
            ok("cuCtxSetCurrent", cuCtxSetCurrent(ctx));
            if load(&image).and_then(|(_, f)| work(f, 200, false)).is_none() { failed3 += 1 }
            if !ok("cuDevicePrimaryCtxReset", cuDevicePrimaryCtxReset_v2(dev)) { failed3 += 1 }
            ok("cuCtxSetCurrent", cuCtxSetCurrent(ctx));
            match load(&image).and_then(|(_, f)| work(f, 1, true)) { Some(w) => wrong3 += w, None => failed3 += 1 }
            ok("cuDevicePrimaryCtxRelease", cuDevicePrimaryCtxRelease_v2(dev));
        }
        println!("{{\"phase3_primary_reset_with_200_queued\":100,\"failed\":{failed3},\"wrong_after_reset\":{wrong3}}}");
        sample("p3_end", 100);
    }
}
