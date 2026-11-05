# results

| file | from |
|---|---|
| `runtime-check.txt` | the booted x86_64 emulator kernel |
| `minimal-repro.txt` | `minimal-repro.sh`, clang r584948c and r596125 |
| `bindgen-versions.txt` | `check-kernel-bindings.sh` with bindgen 0.72.1 and 0.73.2 |
| `kernel-bindings-check.txt` | `check-kernel-bindings.sh`, seed `38453fbe…da535` |
| `ten-seeds.txt` | the same over ten random seeds |
| `task-struct-fields.txt` | the members the kernel crate and Rust drivers read, aarch64 |
| `exposed-structs.txt` | `find-exposed-structs.py` over `common/` |
| `reordered-structs.txt` | the 273 types whose BTF layout differs between two aarch64 builds |
| `build-and-abi.txt` | two `//common:kernel_aarch64_abi_dist` builds |

`reordered-structs.txt` comes from comparing each type's ordered member list in
`pahole -F btf` output across the two builds.

`build-and-abi.txt` includes the control build, which is what separates
randstruct's contribution from this tree's existing config delta against stock
AOSP — the latter already fails `kernel_aarch64_abi_dist` on its own.
