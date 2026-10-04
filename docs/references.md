# Sources and provenance

| Source | Intended use | Caveat |
| --- | --- | --- |
| [Linux DRM UAPI documentation](https://docs.kernel.org/gpu/drm-uapi.html) | Generic DRM and render-node interfaces | Driver-specific interfaces need their own header |
| [Linux DRM header](https://github.com/torvalds/linux/blob/master/include/uapi/drm/drm.h) | `DRM_IOCTL_VERSION` and core structures | Compile against the local header and record its hash |
| [dougallj/applegpu](https://github.com/dougallj/applegpu) | Existing assembler, decoder, model, and tests | Describes G13/M1; hardware harness uses Metal |
| [Generated applegpu ISA documentation](https://dougallj.github.io/applegpu/docs.html) | Candidate encodings and semantics | Reverse-engineered knowledge, not a new local observation |
| `/usr/include/drm/asahi_drm.h` | Installed Asahi parameter, memory, submission, and timing interfaces | Installed header presence does not prove kernel support |

Session inputs are currently at `../AGX_Probe/`: `AGENTS.md`, `REQUESTS.md`,
`apple-agx-resources-guide.md`, and `applegpu/`. Those instruction/reference
folders may not accompany later sessions. Keep new evidence and decisions in
this repository. Do not rely on that resource guide as proof of ISA behavior.

Consulted on 2026-10-04: Linux DRM UAPI documentation and upstream applegpu
README; also inspected the local applegpu Makefile and installed DRM headers.
