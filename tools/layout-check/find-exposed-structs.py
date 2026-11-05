#!/usr/bin/env python3
"""List randomized records that directly contain an anonymous aggregate.

  find-exposed-structs.py <kernel source tree>

Three spellings produce one:

    struct foo { ... struct { ... }; ... } __randomize_layout;
    struct foo { struct { ... struct { ... }; ... } __randomize_layout; ... };
    struct foo { randomized_struct_fields_start ... randomized_struct_fields_end };

The record reported is the one whose members move, so for the last two that is
the inner anonymous struct, named after its enclosing struct.

A source survey and an upper bound; check-kernel-bindings.sh measures what the
bindings actually reach.
"""
import os
import re
import sys

OPEN_NAMED = re.compile(r'^\s*(?:typedef\s+)?(struct|union)\s+(\w+)\s*\{')
OPEN_ANON = re.compile(r'^\s*(struct|union)\s*\{')
START = 'randomized_struct_fields_start'
END = 'randomized_struct_fields_end'


def scan(path, rel):
    try:
        lines = open(path, errors='replace').read().splitlines()
    except OSError:
        return
    # stack entries: [name, has_anon_member, start_line]
    stack = []
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith(START):
            if stack:
                stack[-1][1] = True
            stack.append(['%s (randomized fields)' % stack[-1][0]
                          if stack else 'anonymous', False, n])
            continue
        if s.startswith(END) or (s.startswith('}') and stack):
            if s.startswith(END) or '__randomize_layout' in s or s.startswith('}'):
                if not stack:
                    continue
                name, has_anon, start = stack.pop()
                randomized = s.startswith(END) or '__randomize_layout' in s
                if randomized and has_anon:
                    yield name, '%s:%d' % (rel, start)
                continue
        m = OPEN_NAMED.match(line)
        if m:
            stack.append([m.group(2), False, n])
            continue
        if OPEN_ANON.match(line) and stack:
            stack[-1][1] = True
            stack.append(['%s (anonymous member)' % stack[-1][0], False, n])


def main():
    root = sys.argv[1]
    hits = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('.git', 'out')]
        for f in files:
            if f.endswith(('.h', '.c')):
                p = os.path.join(base, f)
                hits += list(scan(p, os.path.relpath(p, root)))
    seen, uniq = set(), []
    for name, loc in sorted(hits):
        if (name, loc) not in seen:
            seen.add((name, loc))
            uniq.append((name, loc))
    print("randomized records containing an anonymous aggregate member: %d"
          % len(uniq))
    for name, loc in uniq:
        print("  %-42s %s" % (name, loc))


if __name__ == '__main__':
    main()
