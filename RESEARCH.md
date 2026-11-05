# CONFIG_RANDSTRUCT_FULL on GKI 6.18

What stands in the way of enabling `CONFIG_RANDSTRUCT_FULL` in the aarch64 GKI
defconfig on GrapheneOS 6.18, with the measurements behind each claim and the
scripts that produced them.

**It cannot be enabled while CONFIG_RUST is set.** bindgen places an anonymous
struct or union member of a randomized record at offset 0 instead of the offset
Clang assigned, so every Rust read of `task_struct`, `cred`, `file`, `inode`,
`mm_struct` and `vm_area_struct` past that member is off. The build does not
notice. The device does not boot.

```
E Zygote: System zygote died with fatal exception
E Zygote: java.lang.RuntimeException: Failed to mmap shared memory: Invalid argument
E Zygote:   at com.android.internal.os.ApplicationSharedMemory.nativeMap(Native Method)
E Zygote:   at com.android.server.SystemServer.run(SystemServer.java:998)
```

ashmem is Rust on 6.18. `ashmem_vmfile_get_unmapped_area()` reads `current->mm`
and hands it to `mm_get_unmapped_area()`; under randstruct that read lands on
`migration_node`, so the mm layer gets a `list_head` pointing into
`task_struct`. `system_server` cannot create its shared memory and zygote
restarts in a loop.

`patches/0001` (seed) and `patches/0002` (accessors) stand on their own.
`patches/held-back/` is what turns randstruct on, kept with the measurement
attached.

## Contents

- [The tree](#the-tree)
- [6.1 already has it](#61-already-has-it)
- [Architecture](#architecture)
- [B1: CONFIG_RUST depends on !RANDSTRUCT](#b1-config_rust-depends-on-randstruct)
- [B2: bindgen misplaces anonymous members](#b2-bindgen-misplaces-anonymous-members)
- [B3: the seed is drawn per make](#b3-the-seed-is-drawn-per-make)
- [B4: the KMI records member offsets](#b4-the-kmi-records-member-offsets)
- [B5: a reproducible build cannot keep the seed secret](#b5-a-reproducible-build-cannot-keep-the-seed-secret)
- [Measurements](#measurements)
- [What enabling it would take](#what-enabling-it-would-take)
- [Recommendation](#recommendation)
- [Not tested](#not-tested)
- [Reproducing](#reproducing)

## The tree

| | |
|---|---|
| source | `GrapheneOS/kernel_common-6.18`, `android17-6.18` |
| base | `ac1eaa7cdcbd` |
| kernel | 6.18.35, `KMI_GENERATION=5` |
| clang | `clang-r584948c`, 22.0.1; also checked against `r596125`, 22.0.2 |
| bindgen | 0.72.1 (prebuilt); also checked against 0.73.2 |
| rustc | 1.91.1.p3 |

`gki_defconfig` has `CONFIG_RUST=y`, `CONFIG_DEBUG_INFO_BTF=y` and
`CONFIG_MODVERSIONS=y`. `microdroid_defconfig` have
none of the three.

## 6.1 already has it

`GrapheneOS/kernel_common-6.1` branch `17` carries `CONFIG_RANDSTRUCT_FULL=y`
at `arch/arm64/configs/gki_defconfig:719`. AOSP's `android14-6.1` does not.
That tree has no `CONFIG_RUST` and `init/Kconfig:1955` still has the plain
`depends on !RANDSTRUCT`.

So the question is not whether randstruct is wanted but what changed by 6.18,
and the answer is Rust.

Two things there are worth carrying forward.

`scripts/gen-randstruct-seed.sh` is already patched to

```sh
SEED=$(echo -n $KBUILD_BUILD_TIMESTAMP | sha256sum | cut -f 1 -d ' ')
```

which solves B3 for a build that already pins that value, with no new variable
or file, and makes every `kernel_build` in an invocation agree. `patches/0001`
is aimed at upstream, where `KBUILD_BUILD_TIMESTAMP` is not reliably set; it is
not an improvement on this. Two notes on it under B5.

The 6.1 defconfig has also already lost its explicit `CONFIG_MODVERSIONS=y` to
`RANDSTRUCT_FULL`'s select, which is the same `savedefconfig` interaction seen
on 6.18.

## Architecture

Not a blocker. `RANDSTRUCT_FULL` has no arch dependency; the gate is
`CC_HAS_RANDSTRUCT`, a `cc-option` test plus clang >= 16. The members entry
code needs — `thread_info`, `__state`, `saved_state` — sit outside the
randomized region, and everything else goes through `asm-offsets.c`. B2 is
bindgen's field ordering, so it is arch-independent; x86 has one extra exposed
record, `cpuinfo_x86`.

What the architecture does decide:

**6.1 enables it for arm64 and not x86_64.** Reasonable for a distribution
shipping arm64, with the consequence that the validation platform is the arch
it is not enabled on. Testing on the emulator means turning it on there for the
test only, which is what `kernel/configs/randstruct_test.fragment` on the
`randstruct-test` branch does.

**`held-back/0004` touches only arm64's defconfig.** The same series built for
x86_64 gives `CONFIG_RUST=y` and no randstruct — fine for a release, and for a
test it reads as a pass while measuring nothing.

**B3 covers more targets than two.** `common/BUILD.bazel` declares
`kernel_aarch64`, `_16k`, `_debug`, `kernel_x86_64`, `_debug`, microdroid for
three arch and page-size combinations, crashdump for two, `fips140`, three
`allmodconfig` targets, plus the `virtual_device_*` module builds. Each is a
separate `kernel_build` drawing its own seed.

## B1: CONFIG_RUST depends on !RANDSTRUCT

`init/Kconfig` at the base commit:

```
	depends on !GCC_PLUGIN_RANDSTRUCT
	depends on !RANDSTRUCT
```

Kconfig resolves this silently: `CONFIG_RANDSTRUCT_FULL=y` in `gki_defconfig`
does not fail, it drops `CONFIG_RUST`, and with it `rust_binder`,
`CONFIG_ASHMEM` (`drivers/staging/android/ashmem.rs`, `shmem.rs`) and
`CONFIG_ANDROID_WRAPFD`.

The dependency dates to `2f7ab1267dc9`, when the GCC plugin was the only
implementation. Clang reorders the `FieldDecl` chain, which libclang reports,
so the original reasoning does not carry over. B2 is why it should stay anyway.

Upstream softened the posture in
[`2625480a1bf7`](https://github.com/torvalds/linux/commit/2625480a1bf79c62ffb09aafdf61778e682da492),
which stops defaulting `RANDSTRUCT_FULL` on when Rust is available. 6.18
predates it.

There is also an open RFC to lift the dependency outright:
[rust: allow Clang-native `RANDSTRUCT` configs](https://lkml.iu.edu/2411.2/03251.html),
which makes the same change as `patches/held-back/0003` and reports

> I printed the offset of a couple of the `task_struct` randomized members
> from both C and Rust independently [...] they seem to match as well from a
> couple tries

asking for "a fair amount of testing" and a "build test to double-check
layouts do actually match". B2 is that test.

## B2: bindgen misplaces anonymous members

```c
struct t {
	long m0;
	union { int u0; long u1; };
	long m2;
	long m3;
} __randomize_layout;
```

```
Clang    m3 @0  m2 @8  union @16  m0 @24
bindgen  union @0  m3 @8  m2 @16  m0 @24
```

With randstruct off the anonymous member is placed correctly. Reproduced with
bindgen 0.72.1 and 0.73.2 against clang 22.0.1 and 22.0.2
(`results/minimal-repro.txt`, `results/bindgen-versions.txt`).

### On the kernel

`tools/layout-check/check-kernel-bindings.sh` compares Clang's
`-fdump-record-layouts` against rustc's layout of the bindings bindgen emitted,
using the invocation the build records in `.bindings_generated.rs.cmd`. Both
arms differ only by `-DRANDSTRUCT` and `-frandomize-layout-seed-file`.

| | records | member offsets | wrong |
|---|---|---|---|
| randstruct off | 690 | 5350 | 0 |
| randstruct on | 691 | 5351 | **235** |

Seven records: `cred`, `file`, `inode`, `mm_struct`, `shmem_inode_info`,
`task_struct`, `vm_area_struct`. Over ten seeds the off arm is 0 every time and
the on arm ranges from 134 to 413 (`results/ten-seeds.txt`); `cred` escapes on
one seed, its single anonymous member landing where it was declared.

### On the device

x86_64 emulator, `CONFIG_RANDSTRUCT_FULL=y`, seed `38453fbe…da535`. The check
module reports both columns from inside the running kernel:

```
randstruct check: CONFIG_RANDSTRUCT=true
randstruct check:         member        C     Rust
randstruct check:            pid     1656     1656
randstruct check:           tgid     3804     3804
randstruct check:             mm      376      384  MISMATCH
randstruct check:         sizeof     3840     3840
```

The C column matches `pahole -F btf` on that build's own `vmlinux`.

The kernel boots and adb works. Android does not come up:

```
$ adb shell getprop sys.boot_completed      (empty)
$ adb shell getprop init.svc.zygote         restarting
$ adb shell getprop init.svc.servicemanager running
$ adb shell getprop init.svc.surfaceflinger running
```

`shmem.rs:234`:

```rust
#[cfg(CONFIG_RANDSTRUCT)]
let mm = unsafe { (*bindings::get_current()).__bindgen_anon_1.mm };
unsafe { bindings::mm_get_unmapped_area(mm, file, addr, len, pgoff, flags) }
```

```
struct mm_struct *     mm;                    /*   376     8 */
struct list_head       migration_node;        /*   384    16 */
```

`mm_get_unmapped_area()` therefore receives `migration_node.next`, mmap returns
EINVAL, `ApplicationSharedMemory.create()` throws, and `system_server` dies.

`pid` and `tgid` agreed on that kernel. They are the two members anyone checks
first, and checking only those passes on a kernel that cannot boot. The same
seed on aarch64 falls the other way, with `pid`, `tgid`, `mm` and `files` all
wrong. Which members move depends on the permutation.

The quieter consumer is `binder/page_range.rs:277`:

```rust
ARef::from(&**kernel::current!().mm().ok_or(ESRCH)?)
```

which takes a counted reference on the same pointer, against a documented
precondition that `current->mm` being non-null means it references a valid mm
with non-zero `mm_users`. Boot never gets that far. A permutation that left
`mm` alone but moved something binder reads would corrupt rather than fail.

### Not caught by the build

The series compiles, links, produces one consistent vermagic across both dists
and loads `rust_binder.ko`. The randstruct hash in vermagic covers the seed, and
both sides used the same seed; they disagree about what it means.
`scripts/rust_is_available.sh` warns on a libclang/`$CC` version mismatch,
which is a different failure.

### Reach

`tools/layout-check/find-exposed-structs.py` lists randomized records that
directly contain an anonymous aggregate: 15 in this tree
(`results/exposed-structs.txt`), including `cred`, `file`, `inode`,
`mm_struct`, `task_struct`, `tty_struct`, `vm_area_struct`, `proto` and
`task_security_struct`. The seven that the bindings check flags are the ones
the current bindings reach.

## B3: the seed is drawn per make

```sh
SEED=$(od -A n -t x8 -N 32 /dev/urandom | tr -d ' \n')
```

Unconditionally, so builds are not reproducible, and a build system that
invokes make more than once gets a different seed each time. Kleaf does; see
[Architecture](#architecture) for the target count.

`patches/0001` takes the seed from `$KRANDSTRUCT_SEED`, else
`$KRANDSTRUCT_SEED_FILE`, else a `randstruct.seed` at the top of the tree, else
`/dev/urandom`. The seed is not added to the tree.

On Kleaf a `randstruct.seed` at `common/` reaches every `kernel_build` in the
invocation despite being gitignored, because `//common:common_kernel_sources`
is `glob(["**"])` and `kernel_aarch64_sources` aliases it
(`common/BUILD.bazel:150`, `common_kernels.bzl:171`). Confirmed by building
both dists and checking they share one vermagic.

## B4: the KMI records member offsets

`gki/aarch64/abi.stg` records member offsets and ordered member id lists, and
`kernel_aarch64` is `kmi_enforced = True` (`common/BUILD.bazel:255`,
`abi_definition_stg` at `:240`). `abi_stgdiff.bzl:53` turns that into an error
rather than a warning.

Two `//common:kernel_aarch64_abi_dist` builds, one at the base commit and one
with the series:

| | control | randstruct |
|---|---|---|
| exported symbols | 10050 | 10050 |
| added or removed | 0 | 0 |
| modversion CRCs changed | — | 6612 |
| of the 9718 KMI symbols | — | 6364 |
| stg types changed | 16 | 384 |
| stg member offsets moved | 28 | 3774 |

The symbol add/remove list is identical between the runs, so it is this tree's
config delta against stock AOSP, not randstruct. This tree therefore already
fails `kernel_aarch64_abi_dist`; `kernel_aarch64_dist` does not run that check.

Randstruct contributes layout churn and no API surface change, fixed by
`//common:kernel_abis_update`. It does invalidate every vendor module, which is
why the seed should rotate on `KMI_GENERATION` bumps.

## B5: a reproducible build cannot keep the seed secret

Reproducibility requires the seed, and publishing it publishes the layouts.
`.BTF` is allocated — `ffff800081c0b000`, flag `A` — so it ships in `Image` and
`boot.img`:

```
$ pahole -F btf -C cred vmlinux
struct cred {
	struct ucounts *           ucounts;              /*     0     8 */
	struct key *               thread_keyring;       /*     8     8 */
	kernel_cap_t               cap_permitted;        /*    16     8 */
```

The same struct starts `usage@0, uid@8, gid@12` in the control build.

So on a public-build distribution randstruct is not layout secrecy. It makes an
exploit written against stock GKI offsets need re-targeting once — per
distribution, not per device, and only until the attacker reads the BTF out of
a published image. Against per-boot randomization that keeps its secret, it is
a weaker kind of defence.

Dropping `CONFIG_DEBUG_INFO_BTF` would close that route at the cost of BPF
CO-RE and the GKI module checks.

On 6.1 the seed is weaker still: `sha256($KBUILD_BUILD_TIMESTAMP)`, and
`init/Makefile:32` feeds that timestamp into `UTS_VERSION`, so it is one sha256
of a string in the kernel banner. The variable is also unquoted, and with it
unset the script yields `sha256("")` =
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` on every
build, while the banner still looks right because `init/Makefile` falls back
separately.

## Measurements

`//common:kernel_aarch64_dist` and `//common-modules/virtual-device:virtual_device_aarch64_dist`
with a supplied seed (`results/build-and-abi.txt`):

- one vermagic across both dists, its hash the sha256 of the supplied seed
- `Image` 40643072 → 40647168, +4096 bytes
- 273 of 11645 named BTF types change layout: 60 marked `__randomize_layout`,
  213 function-pointer-only (`results/reordered-structs.txt`)
- `rust_binder.ko` builds; `CONFIG_RUST`, `CONFIG_ASHMEM` and
  `CONFIG_ANDROID_WRAPFD` survive

None of that is evidence the kernel works, as the boot shows.

## What enabling it would take

1. bindgen places anonymous members at their randomized offsets. Not fixed in
   0.73.2.
2. The build checks that it did. `check-kernel-bindings.sh` needs no kernel
   build, only the recorded bindgen command, so it can gate the config.
3. `patches/0002`, so Rust can name the members at all. It covers every
   accessor, so 0001+0002 build with randstruct forced on by hand.
4. A seed under the build's control — 6.1's `$KBUILD_BUILD_TIMESTAMP`
   derivation carried forward, with the empty case guarded.
5. The Kconfig relaxation, gated on `CC_IS_CLANG`.
6. `abi.stg` regenerated, seed rotated on `KMI_GENERATION` bumps.
7. Which arches, stated explicitly.

Step 1 is not work this tree can do.

## Recommendation

**`gki_defconfig`: do not enable.** It does not boot.

**6.1 needs no change.** `RANDSTRUCT_FULL` and no Rust.

**`microdroid_defconfig` is cheap.** No
`CONFIG_RUST`, so B1 and B2 do not apply; no `CONFIG_DEBUG_INFO_BTF`, so B5's
disclosure route is closed. They still need B3.

**Report B2 to rust-bindgen and to the RFC thread.** `minimal-repro.sh` is the
bindgen report; the thread asked for this measurement and is still open.

On the security value, separately from the mechanics: official builds must be
reproducible, so the seed is public, and `.BTF` ships the layouts anyway. What
randstruct offers here is one-off re-targeting work for an attacker — real,
fixed, public, and weaker than the per-boot randomization already in the tree.

## Not tested

- aarch64 never booted. Built only.
- Reproducibility unproven. `Image` is
  `a512aba4db78ef53ede616ec6e7a4141dadd2a69f4689a99f558bf186dea6e62` for the
  series without the test commit; confirming it needs `bazel clean --expunge`
  and a second build.
- `CONFIG_RANDSTRUCT_KUNIT_TEST` not run: `CONFIG_KUNIT=m` here so it can only
  be `=m`, and `lib/tests/randstruct_kunit.ko` is not in
  `get_kunit_modules_list("arm64")`.
- No LTP run.
- One seed on the device; ten through the static check.

## Reproducing

```
tools/layout-check/minimal-repro.sh <kernel-tree>
```

```
SRC_ROOT=<kernel-tree>/common OBJ=<objdir> \
  tools/layout-check/check-kernel-bindings.sh <kernel-tree> \
      <objdir>/rust/bindings/.bindings_generated.rs.cmd [seed]
```

Exits non-zero if the randstruct arm disagrees anywhere the control did not. A
later build deletes the `.cmd` file, so copy it first; `OBJ` is the directory
holding `include/generated/autoconf.h`.

```
tools/layout-check/find-exposed-structs.py <kernel-tree>/common
```

For the device check, build `randstruct-test` and read
`dmesg | grep -i 'randstruct check'`. See `TESTING.md`.
