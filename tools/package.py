#!/usr/bin/env python3
"""Build dist/diff-inline-widget.skill from skill/diff-inline-widget.

  python3 tools/package.py [--allow-unpinned] [--out DIR]

A .skill file is a zip archive with the skill folder at its top level, plus a copy of the repository's LICENSE inside
that folder. The build is reproducible (fixed timestamps).

It refuses to package while the renderer URL in make_diff.py still has placeholders, because such a skill could not
draw anything; --allow-unpinned is for trying the packager only.
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "diff-inline-widget"
LICENSE = ROOT / "LICENSE"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def frontmatter(text):
    """The `key: value` fields between the two --- lines at the top of SKILL.md."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        sys.exit("SKILL.md has no frontmatter")

    fields = {}
    for line in match.group(1).split("\n"):
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields


def check_skill(allow_unpinned):
    """Exit with a message unless SKILL.md is valid and the renderer URL is pinned."""
    fields = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    if fields.get("name") != SKILL.name:
        sys.exit(f"frontmatter name '{fields.get('name')}' must equal the folder name '{SKILL.name}'")

    description = fields.get("description", "")
    if not description or len(description) > 1024:
        sys.exit(f"description must be 1-1024 characters (is {len(description)})")

    script = (SKILL / "scripts" / "make_diff.py").read_text(encoding="utf-8")
    if not allow_unpinned and re.search(r'^SCRIPT_URL = ".*(OWNER|@REF/)', script, re.MULTILINE):
        sys.exit("SCRIPT_URL still has placeholders: pin the renderer first (docs/releasing.md)")


def package_entries():
    """(path in the archive, file on disk): the skill's own files first, then the license."""
    entries = [
        (Path(SKILL.name) / path.relative_to(SKILL), path)
        for path in sorted(SKILL.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    ]
    entries.append((Path(SKILL.name) / LICENSE.name, LICENSE))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-unpinned", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "dist"))
    args = parser.parse_args()

    check_skill(args.allow_unpinned)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{SKILL.name}.skill"
    entries = package_entries()

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for archive_path, source in entries:
            info = zipfile.ZipInfo(archive_path.as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())

    print(f"{target} ({target.stat().st_size} bytes, {len(entries)} files)")


if __name__ == "__main__":
    main()
