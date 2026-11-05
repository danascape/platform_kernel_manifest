# layout-check

Does the struct layout bindgen described to Rust match the layout the C
compiler actually produced?

Clang's `-Xclang -fdump-record-layouts` is the ground truth: it is the layout
the C side of the kernel uses. rustc's `-Zprint-type-sizes` gives the layout
Rust computes from the `#[repr(C)]` definitions bindgen emitted. Where the
two differ, Rust reads the wrong address, and neither the compiler nor the
module loader will say so.

Each script runs two arms that differ only by `-DRANDSTRUCT` and
`-frandomize-layout-seed-file`. The first is a control: bindgen has layout
limitations unrelated to randstruct, and reporting both arms is what
separates them. It also makes a vacuous pass visible — if the control and
the randstruct arm produce identical Clang output, the seed did nothing and
the run proves nothing, which `check-kernel-bindings.sh` checks for and
refuses.

## Scripts

| | |
|---|---|
| `minimal-repro.sh` | Four-field demonstration. Needs a kernel tree's prebuilt clang and bindgen, builds nothing. |
| `check-kernel-bindings.sh` | The real check, against a kernel's own `bindings_helper.h` and the bindgen command its build recorded. |
| `find-exposed-structs.py` | Source survey: randomized records that contain an anonymous aggregate. An upper bound, not a measurement. |
| `compare-layouts.py` | Compares one Clang dump against one rustc dump. The other scripts call it. |
| `split-cmd.py` | Splits a `.bindings_generated.rs.cmd` into header, bindgen args and clang args. |
| `make-standalone.py` | Makes generated kernel bindings compile outside the kernel crate (drops `MaybeZeroable`, the `cfi_encoding` attribute, the `RUST_CONST_HELPER_` prefix). |
| `force-layout.py` | Appends a `size_of` per type so rustc lays all of them out, not only the ones something uses. |

## Using check-kernel-bindings.sh

It needs the `.bindings_generated.rs.cmd` the kernel build writes next to
`rust/bindings/bindings_generated.rs`, which records the exact bindgen
invocation — every `-I`, `-D` and `-include`. Reusing it is what makes the
check reflect the real build rather than an approximation of it.

```
export SANDBOX_ROOT=<execroot path inside the recorded command>
export SRC_ROOT=/path/to/kernel/tree/common
./check-kernel-bindings.sh /path/to/kernel/tree \
    <objdir>/rust/bindings/.bindings_generated.rs.cmd [seed-file]
```

`SANDBOX_ROOT` and `SRC_ROOT` rewrite the sandbox paths a Kleaf build
records; drop them if the build directory is intact. Exits non-zero if the
randstruct arm disagrees anywhere the control did not.

The check is cheap — no kernel build, a few minutes of bindgen and rustc —
so it can gate the config rather than run after it.

## Reading the output

```
records compared        : 692
member offsets compared : 5356
member offsets wrong    : 235
records that disagree   : 7
  cred  (7)
      ucounts: C @0, Rust @16
```

`C @` is where the member is. `Rust @` is where Rust will look for it.
