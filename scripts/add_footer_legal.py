#!/usr/bin/env python3
"""
Add a legal-links row (About · Contact · Privacy Policy · Disclaimer) to the
footer of every page on BalticDryIndex.com, so the required pages — and the
contact email on the contact page — are reachable from anywhere. This is what
Google AdSense expects, and it surfaces your contact method site-wide.

Safe & idempotent: inserts the row just before <div class="footer-bottom">,
skips any page that already has it, writes a file only when it changes.
Absolute links (/about/ etc.) point at the English legal pages from every page,
including the language subsites (which have no localized legal pages).

Run from the repo root:
    python scripts/add_footer_legal.py          # apply
    python scripts/add_footer_legal.py --dry     # preview only
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRY  = "--dry" in sys.argv

ANCHOR = '<div class="footer-bottom">'
MARKER = 'class="footer-legal"'   # presence => already done

LEGAL_ROW = (
    '<div class="footer-legal" style="text-align:center;padding:14px 16px;'
    'border-top:1px solid var(--border);font-family:var(--mono);font-size:12px;'
    'letter-spacing:.03em;">'
    '<a href="/about/" style="color:var(--text-dim);text-decoration:none;margin:0 10px;">About</a>'
    '<a href="/contact/" style="color:var(--text-dim);text-decoration:none;margin:0 10px;">Contact</a>'
    '<a href="/privacy-policy/" style="color:var(--text-dim);text-decoration:none;margin:0 10px;">Privacy Policy</a>'
    '<a href="/disclaimer/" style="color:var(--text-dim);text-decoration:none;margin:0 10px;">Disclaimer</a>'
    '</div>\n'
)

def process(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if MARKER in text:        # already has the legal row
        return False
    if ANCHOR not in text:    # no footer-bottom to anchor to
        return False
    new = text.replace(ANCHOR, LEGAL_ROW + ANCHOR, 1)  # before the first footer-bottom
    if new != text:
        if not DRY:
            path.write_text(new, encoding="utf-8")
        return True
    return False

def main():
    changed, scanned = [], 0
    for p in ROOT.rglob("*.html"):
        if ".git" in p.parts or "node_modules" in p.parts:
            continue
        scanned += 1
        if process(p):
            changed.append(p.relative_to(ROOT))
    mode = "DRY RUN — nothing written" if DRY else "Applied"
    print(f"{mode}. Scanned {scanned} HTML files, updated {len(changed)}.")
    for c in sorted(changed):
        print("  +", c)
    if not changed:
        print("  (nothing to change — every page already has the legal row)")

if __name__ == "__main__":
    main()
