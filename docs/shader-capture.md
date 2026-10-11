# Shader capture: AGX binaries from any Mesa program, with a cycle estimate per instruction

`scripts/agx_capture.py` works like a Metal shader capture for Asahi Mesa. It runs a GLES or Vulkan
program through Mesa's own driver, collects every AGX binary that Mesa compiled, splits each one
into rodata, main shader and preamble, and disassembles them with applegpu. Each instruction is then
annotated with the `scripts/agx_cost.py` cycle model, which predicts issue counts and stall cycles
for 1 and 4 SIMD groups per core.

## Usage

```sh
python3 scripts/agx_capture.py [--ir] [--out DIR] [--json FILE] -- <command ...>   # run + capture
python3 scripts/agx_capture.py --cache DIR                                         # existing cache dir
python3 scripts/agx_capture.py --blob FILE ...                                     # Vulkan shader-object export / raw blob
make capture-demo                                                                  # tests/gles_compute.c mode private
```

| option | meaning |
| --- | --- |
| `--out DIR` | output dir (default `/scratch/apple-m2-playground/capture/<utc>`). It receives `cache/`, `listing.txt`, `capture.json`, one `shader<k>-<region>.bin` per code region (input for `agx_cost.py`), and `run/`, the command's working directory |
| `--ir` | second run with `AGX_MESA_DEBUG=shaders` and the cache disabled. Its dump is matched to the captured shaders by stage and workgroup size. Matched shaders are labelled *application shader*, and their NIR plus AGX IR goes into the JSON. Unmatched shaders are labelled *driver-internal?* |
| `--groups 1,4` | SIMD-group counts to simulate |
| `--path auto\|static\|emulate` | dynamic path for the cost model: `static` runs every instruction once; `emulate` uses applegpu's emulator (`agx_cost.trace`); `auto` picks emulate only if the region has a backward branch |
| `--loop-trips N` | assume every loop runs N times. This is a static path with each backward-branch body repeated, innermost loop first |
| `--timeout 60` | timeout for the command |
| `--mesa auto\|25.1\|25.3` | struct layout. `auto` reads the installed versions: `libgallium-25.1.9.so` for GL, the `Mesa 25.3.6` string in `libvulkan_asahi.so` for Vulkan |

During the capture run, the command gets `MESA_SHADER_CACHE_DIR=<out>/cache` and
`MESA_SHADER_CACHE_DISABLE=false`. Every `*_MESA_DEBUG`, `MESA_SHADER_CACHE*` and `MESA_DISK_CACHE*`
variable is removed, because `agx_disk_cache_init` leaves the cache off whenever compiler debug
flags are set.

## Output (excerpt, `tests/gles_compute.c private`, see `results/2026-10-11-shader-capture/`)

```text
shader 0: compute main  [gl (Mesa 25.1 layout)]  application shader
  source part0/mesa_cache.db@20  binary 420 B  main @128+214  preamble @384  rodata @0 12 B -> u10
  gprs(16-bit) main 10 preamble 2  push uniforms 16  stack 1036/0 words  local 0 B  wg [32, 1, 1]
  Mesa stats: instrs 32  alu 17  fscib 17  ic 16  threads 1024  loops 1  spills 1  fills 2
  --- main @128  198 B  32 instructions (+8 padding)
      predicted cycles: 1 group/core = 94  4 groups/core = 98   (path emulate, 32 dynamic instrs, ...)
         pc  hex                      class            n@1  stall@1   n@4  stall@4  disassembly
          0  b500c10520800004         store              1        0     4        0  stack_adjust #1036 (words; applegpu: stack_store i8, ...)
         64  b51a800400c01200         store              1        1     4        4  stack_store i32, 1, 0, x, 4, r3, r4, 0
        152  351a604400c01200         load               1        1     4        4  stack_load r3, i32, 1, 0, x, 4, r3, 1
        160  3800                     wait               1       41     4      164  wait 0
```

`n@G` is how many times the instruction issued, summed over G groups. `stall@G` is the summed gap,
in cycles, between the previous issue and this one in the same group. "Mesa stats" is Mesa's own
`agx2_stats` from the blob, which includes its ALU, FSCIB and IC cycle estimates, so the two models
can be compared. The captured main shader is byte-identical to the one carved by hand in
`results/2026-10-11-stack-via-mesa/record.json`.

## How the binaries are located (no pattern search)

Each layer below is parsed exactly as Mesa writes it. The tool accepts a parse only if it consumes
the whole payload, so a payload that is not an AGX shader is skipped rather than misread. Source
references are to the `mesa-25.1.9` and `mesa-25.3.6` tags in `/save/workspace/AGX_Probe/mesa`.

1. **Cache container.** There are two formats:
   - Database (the default for 25.1.9 GL): `mesa_shader_cache_db/part*/mesa_cache.db`, laid out
     as a 20-byte `mesa_db_file_header`, then entries of `{cache_key[20], crc u32, size u32}` and
     `size` bytes each (`src/util/mesa_cache_db.c`).
   - Multi-file (`MESA_DISK_CACHE_MULTI_FILE=1`): one file per item, `mesa_shader_cache/<2 hex>/<38 hex>`.
2. **Cache item** (`src/util/disk_cache_os.c` `create_cache_item_header_and_blob`). The driver-keys
   blob comes first: `cache_version u8`, the build-id string, the GPU name, `ptr_size u8`, and
   `driver_flags u64` (`src/util/disk_cache.c`). Then come the item type (`u32`; 1 = GLSL program
   metadata, which is skipped), `cache_entry_file_data {crc32, uncompressed_size}`, and the zstd
   frame, which is decompressed with `/usr/bin/zstd` and checked against `uncompressed_size`.
   `blob_write_uint32` aligns to 4 bytes (`src/util/blob.c`). That is why the type field starts 2
   bytes after the 74-byte driver keys.
3. **Asahi Gallium payload** (`src/gallium/drivers/asahi/agx_disk_cache.c` `write_shader`). The
   payload holds `struct agx_shader_info` (1176 bytes), then `binary_size` bytes of code, then
   `uvs` (88), `attrib_components_read` (8), `epilog_key` (4), alignment to 4, `push_range_count`,
   and that many 6-byte push ranges. For a geometry shader this is followed by `agx_gs_info` and
   the child shaders `pre_gs`, `gs_copy` and `gs_count`, each recursively the same layout.
4. **Honeykrisp (Vulkan) payload** (`src/asahi/vulkan/hk_shader.c` `hk_api_shader_serialize`). The
   payload starts with a stage byte. Each variant then has `hk_shader_info` (664 bytes in 25.1, 976
   in 25.3), `agx_shader_info`, alignment, `code_size`, `data_size`, code and data. There is 1
   variant per shader, except vertex and tess-eval shaders, which have 2 (hw, sw), and geometry
   shaders, which have 7 in 25.1 and 4 in 25.3. A `VK_EXT_shader_object` export
   (`vkGetShaderBinaryDataEXT`) has a 72-byte `vk_shader_bin_header` first, starting with
   `"MesaVkShaderBin"` (`src/vulkan/runtime/vk_shader.c`).
5. **Regions inside the binary** (`src/asahi/compiler/agx_compile.c`, `agx_compile_function_nir`
   and `agx_compile_shader_nir`). Rodata (`rodata.offset`, `2*size_16` bytes, mapped to uniform
   `base_uniform`) is placed before the main function's code. Every function starts 128-byte
   aligned (`AGX_CODE_ALIGN`). The main shader is at `main_offset` with `main_size` bytes. The
   preamble starts at `preamble_offset` and ends at the next region or at `binary_size`. Each region
   is disassembled up to its last `stop`. The nops after that are Mesa's prefetch padding, which
   is counted but not listed.

The struct sizes and field offsets come from `tests/agx_cache_layout.c`. It contains the
25.1.9/25.3.6 struct definitions copied from the tags (`-DMESA_25_3` selects 25.3) and prints them as
JSON. Between the two versions, `agx_shader_info` stays 1176 bytes, but 25.3 inserts
`uses_sampler_heap` and the texture/sampler state counts. That moves `nr_gprs` from offset 1094
to 1096, and `agx2_stats` gains `preamble_instrs`. `agx_gs_info` grows from 16 to 84 bytes, which
makes `hk_shader_info` grow from 664 to 976. The 976 was confirmed on a real 25.3.6 export: the
`code_size` header appears exactly where predicted. Note that `agx_shader_info.scratch_size` holds
the `stack_adjust` size in 32-bit words, despite the header comment that says bytes.

Mesa's `stack_adjust` (`agx_pack.c` `AGX_OPCODE_STACK_ADJUST`) shares opcode `0xb5` with
`stack_store`. The tool recognises it by Mesa's fixed bits and prints the decoded word count.

## Results on this machine (M2 Max G14C, GLES Mesa 25.1.9, Vulkan Mesa 25.3.6)

* **GLES** `tests/gles_compute.c index` and `private`: 3 shaders each. One is the application
  compute shader. In `index` mode its rodata holds exactly the GLSL constants `0x9e3779b9` and
  `0x12345678`, mapped to `u10`. The other two are a fragment shader part and a 1×1×1 compute
  shader (a 4×4 matrix-vector product). Neither appears in the `AGX_MESA_DEBUG=shaders` dump, so
  both are driver-internal. The fragment shader is a non-monolithic part: 4 `mov`s and no `stop`,
  because it gets an epilog linked at draw time.
* **Vulkan**: shaders created through `VK_EXT_shader_object` (`tests/vulkan_compute.c`) are **not**
  written to the disk cache. The cache dir only ever contained an empty multi-file `index`. The
  binary the program exports with `vkGetShaderBinaryDataEXT` parses fully with `--blob`
  (`listing-vulkan-index.txt`). The pipeline path (`vkCreate*Pipelines` → `vk_pipeline_cache` →
  disk cache) stores the same `hk_api_shader_serialize` bytes without the 72-byte header, and the
  parser handles them, but no pipeline-based program was run.

## Limitations

* Only shaders that go through the disk cache are captured. Not captured:
  - libagx precompiled kernels and the scratch helper program, which are built into the driver;
  - VS prologs and FS epilogs and the fast-linked programs built from them at draw time;
  - Vulkan shader objects (use `--blob` on their export).

  Shaders already present in a cache are not recompiled, which is why each run gets a fresh dir.
  Cache writes are asynchronous and are flushed in `disk_cache_destroy`, so a program that exits
  without tearing down its context can lose entries.
* The cost-model path does not see real uniforms. `emulate` runs with zero uniforms and registers,
  so a loop bound by a uniform runs once. In `private` mode the loop really runs 1024 times; use
  `--loop-trips`. A `static` path counts both sides of every if/else once. The preamble is costed
  like the main shader, although the hardware runs it once per dispatch or draw, not per group.
* Layouts are hardcoded for Mesa 25.1.x and 25.3.x on aarch64. For another version, regenerate them
  with `tests/agx_cache_layout.c` after diffing the structs above. The exact-length check rejects a
  wrong layout rather than misreading it, except for fields that only move inside
  `agx_shader_info`.
* Stage labels come from `agx_shader_info.stage`, the hardware stage. A vertex shader that runs as
  compute (Vulkan `variant:sw`, geometry `pre_gs`) shows as compute.
* The GLSL cache item (type 1) is skipped. The single-file Fossilize cache (`MESA_DISK_CACHE_SINGLE_FILE`)
  is not parsed.
