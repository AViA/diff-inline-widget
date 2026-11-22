#!/usr/bin/env python3
"""Check that the renderer URL pinned in make_diff.py serves exactly the src/diff.js of this working tree.

  python3 tests/check_pin.py                 offline: compare the pinned ref's file in the local git history
  python3 tests/check_pin.py --online        also download the URL and compare the bytes
  python3 tests/check_pin.py --allow-unpinned  exit 0 while OWNER/REF are still placeholders

Exit codes: 0 ok, 1 mismatch or unsafe pin, 2 unpinned (placeholders).
A pinned ref must be a commit hash (development) or a version tag such as v1.2.0 (release); branch names are
refused because their content changes.
"""
import argparse
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKE_DIFF = ROOT / "skill" / "diff-inline-widget" / "scripts" / "make_diff.py"
URL = re.compile(r"^https://cdn\.jsdelivr\.net/gh/([^/@]+)/([^/@]+)@([^/]+)/(.+)$")


def read_pin():
    m = re.search(r'^SCRIPT_URL = "([^"]+)"', MAKE_DIFF.read_text(encoding="utf-8"), re.MULTILINE)
    if not m:
        sys.exit("SCRIPT_URL not found in make_diff.py")
    return m.group(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true", help="also download the pinned URL and compare")
    ap.add_argument("--allow-unpinned", action="store_true", help="exit 0 while the URL still has placeholders")
    a = ap.parse_args()

    url = read_pin()
    m = URL.match(url)
    if not m:
        print(f"SCRIPT_URL is not a jsDelivr GitHub URL: {url}")
        return 1
    owner, _repo, ref, path = m.groups()
    if owner == "OWNER" or ref == "REF":
        print(f"unpinned: {url}")
        return 0 if a.allow_unpinned else 2
    is_commit = re.fullmatch(r"[0-9a-f]{7,40}", ref) is not None
    is_tag = re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", ref) is not None
    if not (is_commit or is_tag):
        print(f"unsafe pin: '{ref}' is neither a commit hash nor a vX.Y.Z tag, so its content can change")
        return 1

    local = (ROOT / path).read_bytes()
    show = subprocess.run(["git", "show", f"{ref}:{path}"], check=False, cwd=ROOT, capture_output=True)
    if show.returncode != 0:
        print(f"git does not know {ref}:{path} here ({show.stderr.decode().strip()}); fetch the history first")
        return 1
    if show.stdout != local:
        print(f"MISMATCH: {path} at {ref} differs from the working tree. Commit your change, pin that commit, "
              "or (release) retag before pinning.")
        return 1
    print(f"ok: {path} at {ref} equals the working tree")

    if a.online:
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                body = r.read()
        except OSError as e:  # URLError, HTTPError and timeouts are all OSErrors; they are reported, not hidden
            print(f"online check failed: {e}")
            return 1
        if body != local:
            print("MISMATCH: the CDN serves different bytes than the working tree (cache? wrong ref?)")
            return 1
        print("ok: the CDN serves the same bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
