//! B39 probe (local, not part of ZLUDA): `b39_alloc DIR GIB[,GIB..] FLOOR_GIB`. For each size, one data object of that
//! size is created, bound and CPU-zeroed (agx_runtime does that), and count.bin (64 lanes store gid at out[8 + gid])
//! writes into its last page; the CPU checks the words. Then 4 GiB objects are added one at a time while
//! MemAvailable stays above FLOOR_GIB + 4, to find the total that binds without pressure (it stops before any failure).
use agx_runtime::*;
use std::time::{Duration, Instant};

fn mem_available_gib() -> f64 {
    let s = std::fs::read_to_string("/proc/meminfo").unwrap();
    let kb: f64 = s.lines().find(|l| l.starts_with("MemAvailable")).unwrap().split_whitespace().nth(1).unwrap().parse().unwrap();
    kb / (1 << 20) as f64
}

fn touch_last_page(dev: &Device, vm: &mut Vm, q: &mut Queue, code: &[u8], bo: &Bo) -> std::io::Result<usize> {
    let out_va = bo.va + bo.size - PAGE;
    let table = vm.alloc_data(0x1000)?;
    let mut unif = vm.alloc_data(0x1000)?;
    let u = unif.as_mut_slice();
    u[20..24].copy_from_slice(&u32::MAX.to_le_bytes());
    u[24..32].copy_from_slice(&out_va.to_le_bytes());
    u[32..40].copy_from_slice(&table.va.to_le_bytes());
    let mut usc = vm.alloc_usc(0x2000)?;
    let off = (usc.va - vm.usc_base) as u32;
    let p = Pipeline { code: off + 0x400, gpr_halves: 32, uniforms: vec![(0, 20, unif.va)], shared_bytes: 0 };
    let w = p.usc_words();
    usc.as_mut_slice()[..w.len()].copy_from_slice(&w);
    usc.as_mut_slice()[0x400..0x400 + code.len()].copy_from_slice(code);
    let c = cdm_dispatch(off, p.uniform_halves(), dev.g14x(), [64, 1, 1], [32, 1, 1]);
    let mut cdm = vm.alloc_data(0x1000)?;
    cdm.as_mut_slice()[..c.len()].copy_from_slice(&c);
    let f = q.submit_compute(cdm.va, cdm.va + c.len() as u64, &[])?;
    q.wait(f, Duration::from_secs(10))?;
    let s = &bo.as_slice()[(bo.size - PAGE) as usize..];
    Ok((0..64).filter(|&g| u32::from_le_bytes(s[4 * (8 + g)..4 * (9 + g)].try_into().unwrap()) == g as u32).count())
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let code = std::fs::read(format!("{}/count.bin", a[1])).unwrap();
    let sizes: Vec<u64> = a[2].split(',').map(|s| s.parse().unwrap()).collect();
    let floor: f64 = a[3].parse().unwrap();
    let dev = Device::open("/dev/dri/renderD128").unwrap();
    let mut vm = Vm::new(&dev).unwrap();
    let mut q = Queue::new(&mut vm).unwrap();
    let pr = &dev.params;
    println!("{{\"vm_start\":\"{:#x}\",\"vm_end\":\"{:#x}\",\"vm_kernel_min_size\":\"{:#x}\",\"usc_base\":\"{:#x}\",\"mem_avail_gib\":{:.1}}}",
             pr.vm_start, pr.vm_end, pr.vm_kernel_min_size, vm.usc_base, mem_available_gib());
    for gib in sizes {
        let before = mem_available_gib();
        if before - (gib as f64) < floor { println!("{{\"single_gib\":{gib},\"skipped\":\"MemAvailable {before:.1} GiB\"}}"); continue }
        let t = Instant::now();
        match vm.alloc_data(gib << 30) {
            Ok(bo) => {
                let alloc_s = t.elapsed().as_secs_f64();
                let ok = touch_last_page(&dev, &mut vm, &mut q, &code, &bo);
                println!("{{\"single_gib\":{gib},\"va\":\"{:#x}\",\"alloc_and_zero_s\":{alloc_s:.2},\"last_page_ok\":{:?},\"mem_avail_before\":{before:.1},\"mem_avail_with\":{:.1}}}",
                         bo.va, ok.map_err(|e| e.to_string()), mem_available_gib());
            }
            Err(e) => println!("{{\"single_gib\":{gib},\"error\":\"{e}\"}}"),
        }
    }
    let mut held: Vec<Bo> = Vec::new();
    loop {
        let avail = mem_available_gib();
        if avail - 4.0 < floor { println!("{{\"total_gib\":{},\"stopped\":\"MemAvailable {avail:.1} GiB\"}}", 4 * held.len()); break }
        match vm.alloc_data(4 << 30) {
            Ok(bo) => {
                let ok = touch_last_page(&dev, &mut vm, &mut q, &code, &bo).map_err(|e| e.to_string());
                held.push(bo);
                println!("{{\"total_gib\":{},\"last_ok\":{:?},\"mem_avail\":{:.1}}}", 4 * held.len(), ok, mem_available_gib());
            }
            Err(e) => { println!("{{\"total_gib\":{},\"error\":\"{e}\"}}", 4 * held.len()); break }
        }
    }
}
