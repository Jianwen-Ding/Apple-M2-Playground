//! B1 probe (local, not part of ZLUDA): `b1_stack stack.o N` loads zoc's object for stack.ptx (a dynamically indexed
//! 1 KiB .local array), launches it for N threads (256 per block) and checks out[g] = idx * g + idx,
//! idx = (g * 37) & 255. Prints one JSON line.
use cuda_types::cuda::*;
use nvcuda_agx::*;
use std::ffi::c_void;
use std::ptr::null_mut;

fn ok(what: &str, r: CUresult) {
    if let Err(e) = r { println!("{{\"error\":\"{what}: {}\"}}", e.0); std::process::exit(1) }
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let image = std::fs::read(&a[1]).unwrap();
    let n: u32 = a[2].parse().unwrap();
    unsafe {
        ok("cuInit", cuInit(0));
        let mut dev = 0;
        ok("cuDeviceGet", cuDeviceGet(&mut dev, 0));
        let mut ctx = CUcontext(null_mut());
        ok("cuCtxCreate", cuCtxCreate_v2(&mut ctx, 0, dev));
        let mut m = CUmodule(null_mut());
        ok("cuModuleLoadData", cuModuleLoadData(&mut m, image.as_ptr() as *const c_void));
        let mut f = CUfunction(null_mut());
        ok("cuModuleGetFunction", cuModuleGetFunction(&mut f, m, c"stack_k".as_ptr()));
        let mut out = CUdeviceptr_v2(null_mut());
        ok("cuMemAlloc", cuMemAlloc_v2(&mut out, n as usize * 4));
        ok("cuMemsetD32", cuMemsetD32_v2(out, 0xdeadbeef, n as usize));
        let mut p: [*mut c_void; 2] = [&mut out as *mut _ as *mut c_void, &n as *const u32 as *mut c_void];
        let t = std::time::Instant::now();
        ok("cuLaunchKernel", cuLaunchKernel(f, n.div_ceil(256), 1, 1, 256, 1, 1, 0, CUstream(null_mut()), p.as_mut_ptr(), null_mut()));
        ok("cuCtxSynchronize", cuCtxSynchronize());
        let ms = t.elapsed().as_secs_f64() * 1e3;
        let mut h = vec![0u32; n as usize];
        ok("cuMemcpyDtoH", cuMemcpyDtoH_v2(h.as_mut_ptr() as *mut c_void, out, n as usize * 4));
        let wrong = (0..n).filter(|&g| { let i = (g.wrapping_mul(37)) & 255; h[g as usize] != i.wrapping_mul(g).wrapping_add(i) }).count();
        println!("{{\"threads\":{n},\"wrong\":{wrong},\"host_ms\":{ms:.2}}}");
        ok("cuCtxDestroy", cuCtxDestroy_v2(ctx));
    }
}
