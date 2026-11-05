# randstruct on GKI 6.18

`CONFIG_RANDSTRUCT_FULL` cannot go into the aarch64 `gki_defconfig` on
GrapheneOS 6.18 while `CONFIG_RUST` is set. bindgen places an anonymous struct
or union member of a randomized record at offset 0 instead of where Clang put
it, so Rust reads `task_struct`, `cred`, `file`, `inode`, `mm_struct` and
`vm_area_struct` members from the wrong addresses. The build does not notice;
the device does not boot.

`GrapheneOS/kernel_common-6.1` already has `CONFIG_RANDSTRUCT_FULL=y`, where
there is no `CONFIG_RUST`.

[RESEARCH.md](RESEARCH.md) · [TESTING.md](TESTING.md)

```
patches/                 the two that stand on their own
patches/held-back/       the two that turn it on
tools/layout-check/      measurement scripts
results/                 their output
```

## Fastest reproduction

```
tools/layout-check/minimal-repro.sh <kernel-tree>
```

Needs only the tree's prebuilt clang and bindgen. Output as recorded:
[results/minimal-repro.txt](results/minimal-repro.txt).

The device result is [results/runtime-check.txt](results/runtime-check.txt).

## Patches

Applying in order on `GrapheneOS/kernel_common-6.18` at `ac1eaa7cdcbd`:

- `0001-randstruct-allow-the-seed-to-be-supplied.patch` — seed from
  `$KRANDSTRUCT_SEED`, `$KRANDSTRUCT_SEED_FILE` or a `randstruct.seed` at the
  top of the tree, falling back to `/dev/urandom`. Aimed at upstream; 6.1
  already derives it from `$KBUILD_BUILD_TIMESTAMP`, which suits a build that
  pins that value better.
- `0002-rust-handle-the-randomized-task_struct-layout.patch` — lets the Rust
  accessors name `task_struct` members through the anonymous struct. Necessary,
  not sufficient.

`held-back/0003` and `held-back/0004` enable it. Applying them produces a
kernel that builds and does not boot; each commit message says so in its first
line.
