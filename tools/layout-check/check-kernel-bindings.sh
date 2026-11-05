#!/bin/bash
# Compare clang -fdump-record-layouts against rustc's layout of the bindings
# bindgen emits, with and without randstruct.
#
#   check-kernel-bindings.sh <kernel-tree> <.bindings_generated.rs.cmd> [seed]
#
# The two arms differ only by -DRANDSTRUCT and -frandomize-layout-seed-file;
# the first is the control. Exits non-zero if the randstruct arm disagrees
# anywhere the control did not.
#
# Env: SRC_ROOT, OBJ, CLANG_DIR, BINDGEN, RUSTC, WORK.
set -eu

TREE=${1:?usage: check-kernel-bindings.sh <kernel-tree> <.bindings_generated.rs.cmd> [seed]}
CMDFILE=${2:?missing .bindings_generated.rs.cmd}
: "${SRC_ROOT:=$TREE/common}"
export SRC_ROOT
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$(mktemp -d)}
mkdir -p "$WORK/inc/generated" "$WORK/o"

if [ $# -ge 3 ]; then
	cp "$3" "$WORK/seed"
else
	head -c 32 /dev/urandom | od -A n -t x8 | tr -d ' \n' > "$WORK/seed"
fi

CLANG_DIR=${CLANG_DIR:-$(ls -d "$TREE"/prebuilts/clang/host/linux-x86/clang-r* | sort | tail -1)}
BINDGEN=${BINDGEN:-$TREE/prebuilts/clang-tools/linux-x86/bin/bindgen}
RUSTC=${RUSTC:-$(ls -d "$TREE"/prebuilts/rust-toolchain/linux-x86/*/bin/rustc | sort | tail -1)}
export LIBCLANG_PATH=$CLANG_DIR/lib

echo "clang   : $("$CLANG_DIR/bin/clang" --version | head -1)"
echo "bindgen : $("$BINDGEN" --version)"
echo "rustc   : $("$RUSTC" --version)"
echo "seed    : $(cat "$WORK/seed")"
echo

python3 -I "$HERE/split-cmd.py" "$CMDFILE" "$WORK"
HDR=$(cat "$WORK/header")
mapfile -t CA < "$WORK/clang_args"
mapfile -t BA < "$WORK/bindgen_args"

# Only reaches vermagic, never a layout.
printf '#define RANDSTRUCT_HASHED_SEED "%s"\n' \
	"$(tr -d ' \n' < "$WORK/seed" | sha256sum | cut -d' ' -f1)" \
	> "$WORK/inc/generated/randstruct_hash.h"

# Include paths are relative to the object directory; set OBJ when the .cmd
# file has been copied out of the build tree.
OBJ=${OBJ:-$(dirname "$(dirname "$(dirname "$CMDFILE")")")}
if [ ! -f "$OBJ/include/generated/autoconf.h" ]; then
	echo "no include/generated/autoconf.h under $OBJ; set OBJ" >&2
	exit 1
fi
cd "$OBJ"

run_arm() {
	local tag=$1; shift
	local extra=("$@")

	"$CLANG_DIR/bin/clang" -w -fsyntax-only -Xclang -fdump-record-layouts \
		"${CA[@]}" ${extra[@]+"${extra[@]}"} "$HDR" > "$WORK/clang_$tag.txt"

	"$BINDGEN" "$HDR" "${BA[@]}" -o "$WORK/raw_$tag.rs" \
		-- "${CA[@]}" ${extra[@]+"${extra[@]}"} 2>/dev/null

	{
		echo '#![no_std]'
		echo '#![allow(non_camel_case_types,non_snake_case,dead_code,non_upper_case_globals,improper_ctypes)]'
		echo 'pub mod ffi { pub use core::ffi::*; pub type c_size_t = usize; pub type c_ssize_t = isize; pub type c_ptrdiff_t = isize; }'
		echo 'pub type __kernel_size_t = usize; pub type __kernel_ssize_t = isize; pub type __kernel_ptrdiff_t = isize;'
		python3 -I "$HERE/make-standalone.py" "$WORK/raw_$tag.rs"
	} > "$WORK/bind_$tag.rs"
	python3 -I "$HERE/force-layout.py" "$WORK/bind_$tag.rs" >> "$WORK/bind_$tag.rs"

	"$RUSTC" -Zprint-type-sizes --target aarch64-unknown-none --crate-type=lib \
		--edition 2021 -A warnings --emit=metadata -o "$WORK/o/$tag.rmeta" \
		"$WORK/bind_$tag.rs" > "$WORK/rust_$tag.txt"
}

run_arm off
run_arm on -DRANDSTRUCT -I"$WORK/inc" -frandomize-layout-seed-file="$WORK/seed"

if cmp -s "$WORK/clang_off.txt" "$WORK/clang_on.txt"; then
	echo "randstruct changed no layout; check CC_HAS_RANDSTRUCT" >&2
	exit 2
fi

echo "=== control: randstruct off ==="
python3 -I "$HERE/compare-layouts.py" "$WORK/clang_off.txt" "$WORK/rust_off.txt" \
	"$WORK/bind_off.rs" | tee "$WORK/report_off.txt" || true
echo
echo "=== randstruct on ==="
python3 -I "$HERE/compare-layouts.py" "$WORK/clang_on.txt" "$WORK/rust_on.txt" \
	"$WORK/bind_on.rs" | tee "$WORK/report_on.txt" || true
echo
echo "work dir: $WORK"

off=$(sed -n 's/^member offsets wrong *: //p' "$WORK/report_off.txt")
on=$(sed -n 's/^member offsets wrong *: //p' "$WORK/report_on.txt")
[ "$on" = "$off" ]
