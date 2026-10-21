# B24 item 6: six-byte low-0b11 opcodes with other operand bytes (2026-10-21)

**Result: they are not no-ops for every operand pattern.** `b24n.py` (every form gated in agx_run, which treats them as
no-ops) ran opcode 0x03 with operand bytes `00 00 00 00` (no-op, as recorded before) and then `ff ff ff ff`:
**`0309ffffffff` hung** (syncobj wait timed out after 3 s; fence never signalled in time). Recovery: a control dispatch
right after passed 3 / 3 with valid timestamps. The sweep was stopped at that point (2 of 248 forms run), as the
remaining variants are no longer "safe" by evidence. The coverage suite's recorded forms (bytes 2-5 = `38 00 62 40`)
remain the only established no-ops; the backend must never emit these opcodes, and the simulator should not treat
arbitrary operand bytes as a no-op (it currently does).
