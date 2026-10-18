#!/usr/bin/env python3
"""
One-off ownership/operator update for BalticDryIndex.com.

Replaces the old company (Sea Blast LTD, St. Vincent) with the current
owner/operator across every .html and .md file in the repo:

    Virtual Random LLC
    Reg. No. 400481260
    Erosi Manjgaladze St. 75a, Nadzaladevi District, Tbilisi, Georgia

Safe to run on the live repo: it only does exact-string replacements, writes a
file only when it actually changes, and prints a report. Idempotent — running it
twice does nothing the second time.

Usage, from the repo root:
    python scripts/update_owner.py          # apply changes
    python scripts/update_owner.py --dry    # show what would change, write nothing
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRY  = "--dry" in sys.argv

NEW_COMPANY = "Virtual Random LLC"
NEW_ADDRESS = "Erosi Manjgaladze St. 75a, Nadzaladevi District, Tbilisi, Georgia"
NEW_REGNO   = "400481260"

# Ordered list of exact (old -> new) replacements. Longest/most-specific first
# so a broad name swap never corrupts a longer phrase.
REPLACEMENTS = [
    # Full address block (contact page + footers + schema)
    ("Cane Garden, Kingstown, St. Vincent and the Grenadines, VC0100", NEW_ADDRESS),
    # About-page sentence about being based in St. Vincent
    ("St. Vincent and the Grenadines. Our team has backgrounds in maritime commerce, commodity markets and financial data.",
     "Tbilisi, Georgia. Our team has backgrounds in maritime commerce, commodity markets and financial data."),
    # Any remaining standalone address fragment
    ("Cane Garden, Kingstown, St. Vincent and the Grenadines", NEW_ADDRESS),
    # Company name everywhere (footers, schema, disclaimer, copyright)
    ("Sea Blast LTD", NEW_COMPANY),
]

# Targeted insert: add a "Reg. No." row to the contact page's Company Details
# panel, right after the Company row. Runs only on files that contain the anchor.
CONTACT_ANCHOR = (
    '<div class="stats-row"><span class="stats-label">Company</span>'
    '<span class="stats-value">Virtual Random LLC</span></div>'
)
CONTACT_INSERT = CONTACT_ANCHOR + (
    '\n          <div class="stats-row"><span class="stats-label">Reg. No.</span>'
    f'<span class="stats-value">{NEW_REGNO}</span></div>'
)

def process(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    # Reg. No. row — only where the Company row now exists and the Reg row doesn't
    if CONTACT_ANCHOR in text and "Reg. No." not in text:
        text = text.replace(CONTACT_ANCHOR, CONTACT_INSERT, 1)
    if text != original:
        if not DRY:
            path.write_text(text, encoding="utf-8")
        return sum(1 for old, _ in REPLACEMENTS if old in original)
    return 0

def main():
    changed, scanned = [], 0
    # .html/.md across the site, plus update_bdi.py (its article generator has the
    # old company baked into the footer template that every new article inherits).
    for ext in ("*.html", "*.md", "*.py"):
        for p in ROOT.rglob(ext):
            if ".git" in p.parts or "node_modules" in p.parts:
                continue
            if p.name == "update_owner.py":   # never rewrite this script's own search strings
                continue
            scanned += 1
            n = process(p)
            if n:
                changed.append(p.relative_to(ROOT))
    mode = "DRY RUN — nothing written" if DRY else "Applied"
    print(f"{mode}. Scanned {scanned} files, updated {len(changed)}.")
    for c in sorted(changed):
        print("  ✓", c)
    if not changed:
        print("  (no occurrences found — already up to date)")

if __name__ == "__main__":
    main()
