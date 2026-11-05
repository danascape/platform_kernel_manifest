import re, sys
s = open(sys.argv[1], errors='replace').read()
s = re.sub(r'\$ *\(pound\) *\[cfi_encoding = "[^"]*"\]', '', s)
s = re.sub(r'pub const RUST_CONST_HELPER_([A-Za-z0-9_]*)', r'pub const \1', s)
s = re.sub(r'\s*,\s*MaybeZeroable', '', s)
s = re.sub(r'#\s*\[\s*derive\s*\(\s*MaybeZeroable\s*\)\s*\]', '', s)
s = re.sub(r'#\s*\[\s*derive\s*\(\s*\)\s*\]', '', s)
sys.stdout.write(s)
