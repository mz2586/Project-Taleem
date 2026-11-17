"""Render the live disclosure phrase list as a Markdown table for the safeguarding review pack.

Reads ``services/core-api/src/taleem_core/contexts/safeguarding/disclosure_phrases.json`` and
normalises each phrase with the SAME ``normalise()`` the screen uses (imported from the service
code, not re-implemented), so the "compared as" column is exactly what the matcher looks for.

Usage (from services/core-api, stdlib only):

    python -m taleem_core.tools.safeguarding_phrase_table           # print the table and counts
    python -m taleem_core.tools.safeguarding_phrase_table --write   # refresh the review pack table
    python -m taleem_core.tools.safeguarding_phrase_table --check   # exit 1 if the table is stale

The table in docs/safeguarding/SAFEGUARDING_REVIEW_PACK.md sits between the markers
``<!-- phrase-table:start -->`` and ``<!-- phrase-table:end -->``. Read-only with respect to the
phrase list: this script never edits the JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ..contexts.safeguarding.domain.disclosure import normalise
from ..contexts.safeguarding.domain.model import CATEGORY_PRIORITY, Category

PKG = Path(__file__).resolve().parents[1]  # src/taleem_core
ROOT = PKG.parents[3]  # repository root
PHRASES = PKG / "contexts" / "safeguarding" / "disclosure_phrases.json"
PACK = ROOT / "docs" / "safeguarding" / "SAFEGUARDING_REVIEW_PACK.md"
START, END = "<!-- phrase-table:start -->", "<!-- phrase-table:end -->"

LANG = {"en": "English", "ur": "Urdu (script)", "ur-Latn": "Roman Urdu"}


def render() -> str:
    data = json.loads(PHRASES.read_text(encoding="utf-8"))
    rows = [
        "| ID | Category | Tier | Language | Phrase (exact, from the JSON) "
        "| Compared as (normalised; must appear as whole words, in order) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    by_cat: Counter[tuple[str, str]] = Counter()
    for p in data["phrases"]:
        cat = p["category"]
        tier = CATEGORY_PRIORITY[Category(cat)].value
        lang = LANG.get(p["lang"], p["lang"])
        by_cat[(cat, lang)] += 1
        rows.append(
            f"| `{p['id']}` | `{cat}` | {tier} | {lang} | {p['phrase']} "
            f"| `{normalise(p['phrase'])}` |"
        )
    langs = sorted({lang for _, lang in by_cat})
    cats = sorted({c for c, _ in by_cat}, key=lambda c: list(Category).index(Category(c)))
    counts = ["", "| Category | " + " | ".join(langs) + " | Total |"]
    counts.append("| --- | " + " | ".join("---" for _ in langs) + " | --- |")
    for c in cats:
        n = [by_cat[(c, lang)] for lang in langs]
        counts.append(f"| `{c}` | " + " | ".join(str(x) for x in n) + f" | {sum(n)} |")
    totals = [sum(by_cat[(c, lang)] for c in cats) for lang in langs]
    counts.append("| **All** | " + " | ".join(str(x) for x in totals) + f" | {sum(totals)} |")
    header = (
        f"Source: `disclosure_phrases.json`, version {data.get('version')}, "
        f"status `{data.get('status')}`."
    )
    return "\n".join([header, "", *rows, *counts])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="refresh the table in the review pack")
    mode.add_argument("--check", action="store_true", help="exit 1 if the pack's table is stale")
    args = ap.parse_args()
    table = render()
    if not (args.write or args.check):
        print(table)
        return 0
    text = PACK.read_text(encoding="utf-8")
    head, sep, rest = text.partition(START)
    _, sep2, tail = rest.partition(END)
    if not sep or not sep2:
        print(f"markers not found in {PACK}", file=sys.stderr)
        return 2
    updated = f"{head}{START}\n\n{table}\n\n{END}{tail}"
    if args.check:
        if updated != text:
            print("review pack phrase table is stale: run with --write", file=sys.stderr)
            return 1
        return 0
    PACK.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
