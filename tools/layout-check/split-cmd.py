#!/usr/bin/env python3
"""Split a kernel .bindings_generated.rs.cmd into header, bindgen and clang args.

  split-cmd.py <.bindings_generated.rs.cmd> <output-directory>

The recorded command is

  bindgen <header> <bindgen args> -o <out> -- <clang args> ; sed ...

The -o pair and everything past the shell separator are dropped.

Recorded paths point into the build sandbox, which may be gone: SRC_ROOT is
substituted for the prefix derived from the header path, or SANDBOX_ROOT if
given. Randstruct flags in the recording are stripped, since leaving them in
would mean the control arm was not a control.
"""
import os
import pathlib
import shlex
import sys

HEADER_SUFFIX = '/rust/bindings/bindings_helper.h'
RANDSTRUCT_FLAGS = ('-DRANDSTRUCT', '-frandomize-layout-seed-file',
                    '-frandomize-layout-seed')


def sandbox_prefix(header):
    """The build-time root the recorded paths are relative to."""
    if header.endswith(HEADER_SUFFIX):
        return header[:-len(HEADER_SUFFIX)]
    return None


def main():
    cmd = pathlib.Path(sys.argv[1]).read_text().splitlines()[0]
    cmd = cmd.split(':=', 1)[1].strip()
    parts = shlex.split(cmd)

    src = os.environ.get('SRC_ROOT')
    sandbox = os.environ.get('SANDBOX_ROOT') or sandbox_prefix(parts[1])
    if src and sandbox and sandbox != src:
        parts = [p.replace(sandbox, src) for p in parts]
        print('rewrote %s -> %s' % (sandbox, src))

    sep = parts.index('--')
    bindgen_args, clang_args = parts[1:sep], parts[sep + 1:]
    if ';' in clang_args:
        clang_args = clang_args[:clang_args.index(';')]

    dropped = [a for a in clang_args if a.startswith(RANDSTRUCT_FLAGS)]
    if dropped:
        clang_args = [a for a in clang_args if not a.startswith(RANDSTRUCT_FLAGS)]
        print('dropped randstruct flags from the recording: %s'
              % ' '.join(dropped))

    header, rest, skip = bindgen_args[0], [], False
    for a in bindgen_args[1:]:
        if skip:
            skip = False
            continue
        if a == '-o':
            skip = True
            continue
        rest.append(a)

    if not pathlib.Path(header).is_file():
        raise SystemExit(
            'the recorded header is not there: %s\n'
            'set SRC_ROOT to the kernel source tree (and SANDBOX_ROOT if the\n'
            'recorded path does not end in %s)' % (header, HEADER_SUFFIX))

    out = pathlib.Path(sys.argv[2])
    (out / 'header').write_text(header)
    (out / 'bindgen_args').write_text('\n'.join(rest))
    (out / 'clang_args').write_text('\n'.join(clang_args))
    print('header       : %s' % header)
    print('bindgen args : %d' % len(rest))
    print('clang args   : %d' % len(clang_args))


if __name__ == '__main__':
    main()
