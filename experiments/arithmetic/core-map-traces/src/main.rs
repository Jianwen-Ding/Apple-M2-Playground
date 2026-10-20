//! Host-only address oracle for supplied core-map tracing. No DRM/device access.
use agx_sim::{cost::Trace, func::{self, Dispatch, Memory, PreparedDispatch}, kernels::{e, get_sr, mov, store}};
use serde_json::{json, Value};
use std::{collections::BTreeSet, io::{self, Read}, sync::Arc};

fn check(traces: &[Vec<Trace>], wgs: &[[u32; 3]], cores: &[u32], wg: u32,
         stride: u32, pcs: &[usize], supplied: bool) -> usize {
    assert_eq!(traces.len(), wgs.len());
    let mut groups = 0;
    for (id, ts) in wgs.iter().zip(traces) {
        assert_eq!(ts.len(), (wg / 32) as usize);
        for (g, tr) in ts.iter().enumerate() {
            let core = if supplied { cores[id[0] as usize] } else { 0 };
            // Independent per-lane integer address calculation; no simulator
            // address/segment helpers or captured traces supply this oracle.
            let segments: BTreeSet<u64> = (0..32).map(|lane| {
                let global = id[0] as u64 * wg as u64 + g as u64 * 32 + lane;
                (0x1000 + 4 * (core as u64 * stride as u64 + global)) / 64
            }).collect();
            assert_eq!(tr.pcs, pcs);
            assert_eq!(tr.mem, vec![(3, vec![(1u64 << 36) / 64]),
                (6, segments.into_iter().collect())]);
            assert!(tr.warnings.is_empty() && tr.skipped.is_empty());
            groups += 1;
        }
    }
    groups
}

fn main() {
    let mut input = String::new(); io::stdin().read_to_string(&mut input).unwrap();
    let jobs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let parts = [get_sr(80, 1), get_sr(20, 2), mov(5, 0),
        e("device_load 0, i32, x, r4, u10_u11, r5, unsigned"), e("wait 0"),
        e("imadd r3, r2, r4, r1"), store(2, 8, 3), e("wait 0"), e("stop")];
    let mut pcs = vec![]; let mut code = vec![];
    for part in &parts { pcs.push(code.len()); code.extend(part); }
    agx_sim::par::set_local_threads(4);
    let mut results = vec![];
    for job in jobs {
        let n = job["n"].as_u64().unwrap() as u32;
        let wg = job["wg"].as_u64().unwrap() as u32;
        let cores: Vec<u32> = serde_json::from_value(job["cores"].clone()).unwrap();
        assert!(n % wg == 0 && wg % 32 == 0);
        let d = Dispatch { code: code.clone(), grid: [n, 1, 1], wg: [wg, 1, 1],
            shared_bytes: 0, uniforms: vec![(8, 0x1000), (9, 0), (10, 0), (11, 16)],
            num_registers: 8, max_steps: 100, placement: 0, launch: Default::default() };
        let mapped = PreparedDispatch::with_m2_core_map(&d, &cores).unwrap();
        let legacy = PreparedDispatch::new(&d).unwrap();
        let mut selected = BTreeSet::new(); let mut seen = BTreeSet::new();
        for (i, core) in cores.iter().enumerate() {
            if seen.insert(*core) { selected.insert(i as u32); }
        }
        let count = cores.len() as u32;
        for i in [0, 7, 8, 15, 16, count - 1, count.saturating_sub(2), (count - 1) / 8 * 8] {
            if i < count { selected.insert(i); }
        }
        let mut wgs: Vec<_> = selected.into_iter().rev().map(|i| [i, 0, 0]).collect();
        wgs.push(wgs[0]); // Preserve duplicate and caller order through parallel collection.
        let mut groups = 0;
        for stride in [n, n * 2] {
            let mut mem = Memory::default();
            let plane = Arc::new(vec![0x5a; n as usize * 4]);
            for core in 0..64 { mem.regions.push((0x1000 + core * stride as u64 * 4, plane.clone())); }
            mem.map(1u64 << 36, stride.to_le_bytes().to_vec());
            let batch = mapped.trace_workgroups(&mem, &wgs).unwrap();
            groups += check(&batch, &wgs, &cores, wg, stride, &pcs, true);
            let old = legacy.trace_workgroups(&mem, &wgs).unwrap();
            groups += check(&old, &wgs, &cores, wg, stride, &pcs, false);
            let fresh = func::trace_workgroups_with_m2_core_map(&d, &mem, &wgs, &cores).unwrap();
            groups += check(&fresh, &wgs, &cores, wg, stride, &pcs, true);
            // Arc identity proves no caller plane was replaced; every byte remains the sentinel.
            assert!(plane.iter().all(|&v| v == 0x5a));
            assert!(mem.regions[..64].iter().all(|(_, p)| Arc::ptr_eq(p, &plane)));
            assert_eq!(mem.read(1u64 << 36, 4).unwrap(), stride as u64);
        }
        results.push(json!({"name":job["name"],"core_ids":seen.len(),"workgroups":cores.len(),
            "requested_workgroups":wgs.iter().map(|w| w[0]).collect::<Vec<_>>(),
            "simd_traces_checked":groups,"memory_snapshots":2,"modes_per_snapshot":3,
            "addresses_exact":true,"caller_memory_unchanged":true}));
    }
    println!("{}",json!({"records":results,"shader_hex":code.iter().map(|b| format!("{b:02x}")).collect::<String>(),
        "instruction_offsets":pcs,"host_threads":4,"hardware_submissions":0}));
}
