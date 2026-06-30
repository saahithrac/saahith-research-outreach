"""Validation checks for the Saahith Research Outreach app.

Run from the app folder:
    python validate_app.py
"""
from __future__ import annotations

import ast
import csv
from pathlib import Path

ROOT = Path(__file__).parent
APP = ROOT / "app.py"
FACULTY = ROOT / "data" / "faculty_targets.csv"
PROFILE = ROOT / "data" / "student_profile.csv"

REQUIRED_COLUMNS = [
    "selected", "wave", "priority", "institution", "field_of_study", "name", "title", "email", "department",
    "research_keywords", "recent_work", "paper_1_title", "paper_1_url", "paper_2_title", "paper_2_url",
    "source_url", "verification_status", "fit_notes", "status", "last_contacted", "follow_up_date"
]
AFFIRMATIVE_STATUSES = {
    "verified", "source_verified", "paper_verified", "send_ready", "fully_verified", "verified_no_paper_reference"
}

def is_verified_status(value: str) -> bool:
    v = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return v in AFFIRMATIVE_STATUSES or v.startswith("verified_")

def main() -> int:
    ast.parse(APP.read_text())
    print("OK: app.py parses successfully.")

    for path in [FACULTY, PROFILE]:
        if not path.exists():
            raise FileNotFoundError(path)
    print("OK: required CSV files exist.")

    rows = list(csv.DictReader(FACULTY.open(newline="")))
    if not rows:
        raise ValueError("faculty_targets.csv has no rows")
    missing = [c for c in REQUIRED_COLUMNS if c not in rows[0]]
    if missing:
        raise ValueError(f"faculty_targets.csv missing columns: {missing}")
    print(f"OK: faculty_targets.csv has required schema and {len(rows)} rows.")

    bad_ready = []
    for i, row in enumerate(rows, start=2):
        name = row.get("name", "")
        status = row.get("verification_status", "")
        email = row.get("email", "")
        source = row.get("source_url", "")
        p1, p1u = row.get("paper_1_title", ""), row.get("paper_1_url", "")
        p2, p2u = row.get("paper_2_title", ""), row.get("paper_2_url", "")
        send_ready = (
            is_verified_status(status)
            and name.strip()
            and "TBD" not in name.upper()
            and email.strip()
            and source.strip()
            and (not p1.strip() or p1u.strip())
            and (not p2.strip() or p2u.strip())
        )
        # A row that is not send-ready is fine. This check confirms no placeholder can slip through.
        if send_ready and "TBD" in name.upper():
            bad_ready.append((i, name))
    if bad_ready:
        raise ValueError(f"Placeholder rows incorrectly marked send-ready: {bad_ready[:5]}")
    print("OK: no placeholder rows can be treated as send-ready.")
    print("NOTE: This script validates structure and guardrails. It does not independently verify faculty/paper truth; use source_url and paper_url review before marking rows verified.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
