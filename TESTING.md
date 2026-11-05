# Testing

| | |
|---|---|
| newer bindgen | done — 0.73.2 behaves as 0.72.1, `results/bindgen-versions.txt` |
| multiple seeds | done — ten seeds, `results/ten-seeds.txt` |
| boot | done, both arches: `results/runtime-check.txt`, `results/runtime-check-aarch64.txt` |
| reproducibility | not done |
| KUnit / LTP | not done, see below |

```
TREE=/home/saalim/os/gos/kenrel
REPO=/home/saalim/os/gos/randstruct-gki
SEED=38453fbe5155a2b217dea8c53ad8516174fd7bd8178fa8e2255902c530cda535
```

## The static check

```
find $TREE/out -name '.bindings_generated.rs.cmd'
```

Copy it before use; a later build deletes the sandbox it lives in. `OBJ` is the
directory holding `include/generated/autoconf.h`, inferred from the `.cmd`
path, so pass it explicitly once the file has moved.

```
printf '%s' "$SEED" > /tmp/seed
SRC_ROOT=$TREE/common OBJ=<objdir> \
  $REPO/tools/layout-check/check-kernel-bindings.sh $TREE /tmp/cmd.saved /tmp/seed
```

Non-zero exit if the randstruct arm disagrees anywhere the control did not. A
recording from a randstruct build already carries `-DRANDSTRUCT` and
`-frandomize-layout-seed-file`; `split-cmd.py` strips them so the control is
one.

### Another bindgen

```
cargo install bindgen-cli --version <v> --root /tmp/bg --locked
BINDGEN=/tmp/bg/bin/bindgen CLANG_DIR=$TREE/prebuilts/clang/host/linux-x86/clang-r584948c \
  $REPO/tools/layout-check/check-kernel-bindings.sh ...
```

Confirm which libclang it loaded, since the wrong one gives a clean-looking
result:

```
LIBCLANG_PATH=$(mktemp -d) /tmp/bg/bin/bindgen x.h          # must fail
LIBCLANG_PATH=$CLANG_DIR/lib strace -e trace=openat \
    /tmp/bg/bin/bindgen x.h 2>&1 | grep libclang            # must be the prebuilt
```

### Seeds

```
for i in $(seq 1 10); do
  head -c 32 /dev/urandom | od -A n -t x8 | tr -d ' \n' > /tmp/seed.$i
  SRC_ROOT=$TREE/common OBJ=<objdir> \
    $REPO/tools/layout-check/check-kernel-bindings.sh $TREE /tmp/cmd.saved /tmp/seed.$i \
    | grep -E 'member offsets wrong|records that disagree'
done
```

## The device check

Branch `randstruct-test` adds `rust/helpers/randstruct_check.c` and
`samples/rust/rust_randstruct_check.rs`, which print the C and Rust offsets of
`pid`, `tgid` and `mm` plus `sizeof` from inside the kernel under test. The
fragment at `kernel/configs/randstruct_test.fragment` is attached to both
`kernel_aarch64` and `kernel_x86_64`, states `CONFIG_RANDSTRUCT_FULL` itself,
and raises `LOG_BUF_SHIFT` to 19.

```
cd $TREE
git -C common checkout randstruct-test
printf '%s' "$SEED" > common/randstruct.seed
ARCH=x86_64 common/build_generic.sh
ANDROID_BUILD_TOP=/home/saalim/os/gos/os ARCH=x86_64 common/update_generic_prebuilts.sh
```

`build_generic.sh` takes `aarch64`/`aarch64_16k`/`x86_64`;
`update_generic_prebuilts.sh` takes `arm64`/`arm64_16k`/`x86_64`. It wipes the
prebuilt `.ko` files before copying, so afterwards:

```
cd /home/saalim/os/gos/os
for d in kernel/prebuilts/6.18/x86_64 \
         kernel/prebuilts/common-modules/virtual-device/6.18/x86-64; do
    git -C $d checkout . && git -C $d clean -fd
done
```

Then:

```
adb root && adb wait-for-device
adb shell dmesg > randstruct-on.log
grep -i -A6 'randstruct check' randstruct-on.log
adb shell getprop sys.boot_completed
adb shell getprop init.svc.zygote
adb logcat -d -b crash | head -40
```

`sys.boot_completed` is the one to read first. The x86_64 run reached a shell
with `init.svc.zygote = restarting` and an empty `sys.boot_completed`.

Expected C column on the x86_64 build with this seed: `pid` 1656, `tgid` 3804,
`mm` 376, `sizeof` 3840 — cross-check with
`pahole -F btf -C task_struct common_dist/vmlinux`.

For the control, build from `ac1eaa7cdcbd` with only the test commit
cherry-picked, keeping the fragment. `CONFIG_RANDSTRUCT=false` and four
agreeing rows.

### aarch64 without Android

The Android emulator refuses arm64 on an x86_64 host. The check runs from an
initcall, so a bare kernel boot is enough:

```
Q=/home/saalim/os/gos/os/prebuilts/android-emulator/trusty-x86_64/bin/qemu-system-aarch64
ARCH=aarch64 common/build_generic.sh
$Q -M virt -cpu max -smp 2 -m 2048 -nographic \
   -kernel common_dist/Image \
   -append "console=ttyAMA0 earlycon panic=-1 nokaslr" | grep -i -A6 'randstruct check'
```

That prebuilt is plain QEMU 10.0.0. It panics for want of a root filesystem
and, with `panic=-1`, loops, so take the first iteration and stop it.

## Reproducibility

Last, since the expunge discards the cache behind whatever is being tested.

```
cd $TREE
git -C common checkout randstruct-v2
printf '%s' "$SEED" > common/randstruct.seed
tools/bazel clean --expunge
ARCH=aarch64 common/build_generic.sh
sha256sum common_dist/Image
```

Expect `a512aba4db78ef53ede616ec6e7a4141dadd2a69f4689a99f558bf186dea6e62`.
Same-machine only; a second builder is a separate exercise.

## KUnit

`CONFIG_KUNIT=m` in this defconfig, so `RANDSTRUCT_KUNIT_TEST` can only be
`=m`, and `lib/tests/randstruct_kunit.ko` is not in
`get_kunit_modules_list("arm64")`. It also only checks that C can reach its own
members.

## If bindgen is fixed

`patches/held-back/0003` and `0004` stop being held back, and the remaining
work is the prebuilt bump, wiring `check-kernel-bindings.sh` into the build,
regenerating `gki/aarch64/abi.stg`, carrying 6.1's seed derivation forward, and
then boot and reproducibility as release gating.
