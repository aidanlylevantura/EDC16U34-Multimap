import hashlib
import os

files = [
    "03G906021KH_382083_MULTIMAP_v1.2.bin",
    "build_multimap.py",
    "generate_thunk.py",
    "sanity_check_build.py"
]

print("=== FILE HASHES (SHA-256) ===")
for f in files:
    if os.path.exists(f):
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        print(f"{f}: {h}")
    else:
        print(f"[-] Missing: {f}")

# Rename the binary to v1.2.1
old_bin = "03G906021KH_382083_MULTIMAP_v1.2.bin"
new_bin = "03G906021KH_382083_MULTIMAP_v1.2.1.bin"
if os.path.exists(old_bin):
    os.rename(old_bin, new_bin)
    print(f"\n[+] Renamed binary to {new_bin}")