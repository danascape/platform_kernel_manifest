#!/bin/bash
# bindgen misplaces anonymous struct and union members of a randomized struct.
#
#   minimal-repro.sh <kernel-tree>
set -eu
TREE=${1:?usage: minimal-repro.sh <kernel-tree>}
CLANG_DIR=${CLANG_DIR:-$(ls -d "$TREE"/prebuilts/clang/host/linux-x86/clang-r* | sort | tail -1)}
BINDGEN=${BINDGEN:-$TREE/prebuilts/clang-tools/linux-x86/bin/bindgen}
export LIBCLANG_PATH=$CLANG_DIR/lib
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT

printf 'deadbeefcafebabe0123456789abcdef' > "$D/seed"
cat > "$D/a.h" <<'EOF'
#define __randomize_layout __attribute__((randomize_layout))
struct t {
	long m0;
	union { int u0; long u1; };
	long m2;
	long m3;
} __randomize_layout;
EOF
printf '#include "a.h"\nstruct t v;\nint u = sizeof(v);\n' > "$D/u.c"

echo "clang   : $("$CLANG_DIR/bin/clang" --version | head -1)"
echo "bindgen : $("$BINDGEN" --version)"
echo

for arm in off on; do
	if [ "$arm" = on ]; then
		flags=(-frandomize-layout-seed-file="$D/seed")
	else
		flags=()
	fi
	echo "######## randstruct $arm ########"
	echo "--- the layout Clang produced ---"
	"$CLANG_DIR/bin/clang" -w -fsyntax-only -Xclang -fdump-record-layouts \
		-I"$D" ${flags[@]+"${flags[@]}"} "$D/u.c" 2>/dev/null |
		awk '/\| struct t$/,/sizeof=/' | sed 's|(anonymous at [^)]*)|(anonymous)|'
	echo "--- the struct bindgen gave Rust ---"
	"$BINDGEN" --use-core --no-layout-tests --no-derive-debug -o "$D/b.rs" \
		"$D/a.h" -- -I"$D" ${flags[@]+"${flags[@]}"} 2>/dev/null
	awk '/^pub struct t \{/,/^}/' "$D/b.rs"
	echo
done

cat <<'EOF'
With randstruct on, Clang puts the anonymous union at 16 and bindgen puts it
first, shifting m3, m2 and the union's members. vermagic does not catch it:
both sides used the same seed.
EOF
