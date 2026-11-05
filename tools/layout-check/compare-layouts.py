#!/usr/bin/env python3
"""Compare the layout bindgen gave Rust with the layout Clang produced.

  compare-layouts.py <clang-record-layouts> <rustc-print-type-sizes> <bindings.rs>

Members of anonymous aggregates are followed on both sides, so a member C
names directly is compared against the same member reached through
__bindgen_anon_N.
"""
import re
import sys

C_TOP = re.compile(r'^\s*(\d+) \| (?:struct|union) ([A-Za-z_]\w*)\s*$')
C_MEM = re.compile(r'^\s*(\d+)(?::\d+-\d+)? \|(\s+)(\S.*?)\s*$')
C_SIZE = re.compile(r'^\s*\| \[sizeof=(\d+), align=(\d+)')


def parse_clang(path):
    """{struct: {"size", "align", "fields": {name: absolute offset}}}"""
    out, cur, skip = {}, None, None
    for line in open(path, errors='replace'):
        m = C_TOP.match(line)
        if m:
            cur, skip = {"fields": {}}, None
            out[m.group(2)] = cur
            continue
        if cur is None:
            continue
        m = C_SIZE.match(line)
        if m:
            cur["size"], cur["align"] = int(m.group(1)), int(m.group(2))
            cur = None
            continue
        m = C_MEM.match(line)
        if not m:
            continue
        indent = len(m.group(2))
        if skip is not None:
            if indent > skip:
                continue
            skip = None
        if "(anonymous" in m.group(3):
            continue
        name = m.group(3).split()[-1].split('[')[0].lstrip('*')
        cur["fields"].setdefault(name, int(m.group(1)))
        skip = indent  # a named aggregate's members are not ours
    return out


R_TYPE = re.compile(r'^print-type-size type: `(\w+)`: (\d+) bytes, alignment: (\d+) bytes')
R_FIELD = re.compile(r'^print-type-size\s+field `\.(\w+)`: (\d+) bytes')
R_PAD = re.compile(r'^print-type-size\s+(?:end )?padding: (\d+) bytes')
B_DEF = re.compile(r'pub (struct|union) (\w+)\s*\{')


def parse_bindings(path):
    """{type: (kind, [(field, type), ...])}"""
    src = open(path, errors='replace').read()
    out = {}
    for m in B_DEF.finditer(src):
        i, depth = m.end() - 1, 0
        while i < len(src):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = src[m.end():i]
        fields = re.findall(r'pub (\w+)\s*:\s*([A-Za-z_]\w*)\s*,', body)
        out[m.group(2)] = (m.group(1), fields)
    return out


def parse_rust(path, binds):
    """{type: {"size", "align", "own": [(field, offset, size)]}}"""
    out, cur, off = {}, None, 0
    for line in open(path, errors='replace'):
        m = R_TYPE.match(line)
        if m:
            name = m.group(1)
            cur = {"size": int(m.group(2)), "align": int(m.group(3)), "own": []}
            out.setdefault(name, cur)
            cur = out[name]
            off = 0
            cur["_union"] = binds.get(name, ("struct", []))[0] == "union"
            continue
        if cur is None:
            continue
        m = R_PAD.match(line)
        if m:
            off += int(m.group(1))
            continue
        m = R_FIELD.match(line)
        if m:
            sz = int(m.group(2))
            cur["own"].append((m.group(1), 0 if cur["_union"] else off, sz))
            off += sz
    return out


def flatten(rust, binds, name, base=0, seen=None):
    """{member: absolute offset}, following __bindgen_anon_N."""
    seen = seen or set()
    if name in seen or name not in rust:
        return {}
    seen = seen | {name}
    ftypes = dict(binds.get(name, ("struct", []))[1])
    out = {}
    for fname, foff, _ in rust[name]["own"]:
        if fname.startswith("__bindgen_anon_"):
            inner = ftypes.get(fname)
            if inner:
                out.update(flatten(rust, binds, inner, base + foff, seen))
        elif not fname.startswith(("_bitfield", "__bindgen_padding")):
            out.setdefault(fname, base + foff)
    return out


def main():
    c = parse_clang(sys.argv[1])
    binds = parse_bindings(sys.argv[3])
    r = parse_rust(sys.argv[2], binds)

    n_rec = n_mem = n_bad = 0
    bad = {}
    for name in sorted(set(c) & set(r)):
        if "size" not in c[name]:
            continue
        n_rec += 1
        notes = []
        if c[name]["size"] != r[name]["size"]:
            notes.append("sizeof: C %d, Rust %d"
                         % (c[name]["size"], r[name]["size"]))
        rf = flatten(r, binds, name)
        for mname, coff in c[name]["fields"].items():
            if mname not in rf:
                continue
            n_mem += 1
            if rf[mname] != coff:
                n_bad += 1
                notes.append("%s: C @%d, Rust @%d" % (mname, coff, rf[mname]))
        if notes:
            bad[name] = notes

    print("records compared        : %d" % n_rec)
    print("member offsets compared : %d" % n_mem)
    print("member offsets wrong    : %d" % n_bad)
    print("records that disagree   : %d" % len(bad))
    for name in sorted(bad):
        print("  %s  (%d)" % (name, len(bad[name])))
        for d in bad[name][:5]:
            print("      %s" % d)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
