"""Append a size_of per concrete type so rustc lays them all out."""
import re, sys
src = open(sys.argv[1], errors='replace').read()
names = set(re.findall(r'pub (?:struct|union) (\w+)\s*(?:\{|\()', src))
generic = set(re.findall(r'pub (?:struct|union) (\w+)\s*<', src))
out = []
for i, n in enumerate(sorted(names - generic)):
    out.append("const _FORCE_%d: usize = core::mem::size_of::<%s>();" % (i, n))
print("\n".join(out))
