# SR12/SR13 imageblock dimensions and SR15 imageblock sample stride

Status: confirmed on one device (driver-reported M2 Max G14C B1), direct DRM, compute.

## Claim and scope

* **SR12 / SR13** read the USC Shared word's imageblock width / height: 32×32,
  32×16 and 16×16 read back exactly; 0 for the vertex/compute layout.
* **SR15** reads the Shared word's 4-bit sample-stride field (8-byte units),
  with 0 read as 16. The value 16 seen in every earlier scan is that default,
  not a hardware constant.
* **SR18** equals the Shared bytes field × 256.

The sample-count field changes no compute-visible register (SR14 stays 0).
Imageblock layouts on a compute dispatch completed normally in all 13 probes.

Update 2026-10-18: none of these imageblock layouts changes threadgroup-memory occupancy ([follow-up](../2026-10-18-imageblock-occupancy/README.md)).

## Reproducer and evidence

`make sr-direct` (includes the `shared-*` configurations), `make verify-sr-direct`
(checks 13–15). [Report](../../experiments/registers/sr-direct-drm.md) ·
[evidence](../../results/2026-10-11-sr-direct-drm/README.md).

## Relationship to existing knowledge

The Shared word fields come from Mesa genxml (`USC Shared`). Mesa names neither
SR12, SR13 nor SR15. applegpu's register list was not found to name them either.
Their link to the Shared word is measured here.

## Compiler implications and limitations

Tile-shader / imageblock code could read its tile geometry and sample stride from
SR12/13/15 instead of uniforms. For CUDA compute, which uses the plain layout,
they read 0/0/16. Fragment-stage behaviour is untested.
