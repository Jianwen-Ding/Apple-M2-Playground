# Threadgroup memory, barrier and atomic evidence (2026-10-11)

Rows as in `../2026-10-11-memory-hierarchy` (`core_cycles_per_step` = reference cycles per instruction of every
group). `tg.json` / `tgstore.json`: threadgroup load/store, stride S words, 32 KiB declared; `atomic-global.json`:
device atomic add without return, lane index = global thread index (distinct words); `atomic.json`: the same with
lane index = lane (all cores on the same words); `barrier.json`: core cycles per barrier (`barrier`, `filler_iadds`,
`groups`). `make verify-shared-memory-sync`.
