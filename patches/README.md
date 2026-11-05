# Patches

All four apply on `GrapheneOS/kernel_common-6.18` at `ac1eaa7cdcbd`, in order:

```
git am patches/0001-*.patch patches/0002-*.patch
```

`0001` and `0002` are independent of each other and of the held-back pair.
`0002` carries every accessor site, so the two together build with
CONFIG_RANDSTRUCT forced on.

## Held back

`held-back/0003` and `held-back/0004` enable randstruct. Applying them gives a
kernel that builds, links, produces one consistent vermagic and does not finish
booting: ashmem's Rust `get_unmapped_area` reads `current->mm` 8 bytes high,
`mm_get_unmapped_area()` gets a `list_head`, mmap returns EINVAL and
`system_server` dies in a loop. `../RESEARCH.md` has the measurement.

```
git am patches/0001-*.patch patches/0002-*.patch \
       patches/held-back/0003-*.patch patches/held-back/0004-*.patch
```

`0004` needs a seed at `common/randstruct.seed` or `$KRANDSTRUCT_SEED`.
