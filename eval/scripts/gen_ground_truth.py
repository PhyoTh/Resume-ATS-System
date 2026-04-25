"""Generate partial ground-truth JSONs for the curated eval positives.

The Kaggle CSV `archive/Resume/Resume.csv` has only raw text + category
(no structured labels) AND the resumes are fully anonymized (no emails,
phones, or URLs). The most reliable signal we can extract mechanically is
the set of recognized technical skills that appear verbatim in the text,
matched against the seed alias canonical-names list plus a small
hand-curated set of common tools.

We assert ONLY on the fields we can verify (`is_resume` + the
mechanically-detected technical-skills set). Anything not in the truth
JSON is ignored by the metric — it isn't a partial-credit penalty.

Usage:
    python -m eval.scripts.gen_ground_truth

Idempotent: overwrites ground_truth/<stem>.json for every resume in
eval/dataset/resumes/ whose stem ends in a numeric ID matching the CSV.
The hand-labelled `engineering_10030015.json` is preserved (skipped).
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSV_PATH = REPO / "archive" / "Resume" / "Resume.csv"
RESUMES_DIR = REPO / "eval" / "dataset" / "resumes"
TRUTH_DIR = REPO / "eval" / "dataset" / "ground_truth"

# Files we explicitly DO NOT overwrite (e.g. hand-labelled positives,
# negatives whose ground truth is hand-written).
SKIP = {"engineering_10030015.json", "invoice.json", "recipe.json"}

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
)
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/[\w./-]+", re.I)
GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/[\w./-]+", re.I)
WEBSITE_RE = re.compile(
    r"https?://(?!(?:www\.)?(?:linkedin|github)\.com)[\w./?=&%-]+",
    re.I,
)

# Skills we'll look for verbatim in the resume body. Using whole-word
# matches; sourced from the seed alias canonical-names plus common tools
# that show up across the Kaggle categories. Multi-word phrases
# ("Microsoft Office") are listed before their components so the longer
# match wins.
SKILL_VOCAB = [
    "Microsoft Office",
    "Microsoft Word",
    "Microsoft Excel",
    "Microsoft PowerPoint",
    "PowerPoint",
    "Excel",
    "Word",
    "Adobe Photoshop",
    "Adobe Illustrator",
    "Adobe InDesign",
    "Photoshop",
    "Illustrator",
    "InDesign",
    "Final Cut Pro",
    "Premiere Pro",
    "After Effects",
    "AutoCAD",
    "QuickBooks",
    "Salesforce",
    "SAP",
    "Tableau",
    "Power BI",
    "JavaScript",
    "TypeScript",
    "Python",
    "Java",
    "C++",
    "C#",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "React",
    "Node.js",
    "Next.js",
    "FastAPI",
    "Django",
    "Flask",
    "PyTorch",
    "TensorFlow",
    "AWS",
    "Google Cloud",
    "Azure",
    "Kubernetes",
    "Docker",
    "Linux",
    "Git",
    "GitHub",
    "Jira",
    "HTML",
    "CSS",
]


def _detect_skills(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for skill in SKILL_VOCAB:
        # Whole-word, case-insensitive. Allow optional period right after
        # the skill (e.g. "PowerPoint.").
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            key = skill.lower()
            if key not in seen:
                seen.add(key)
                found.append(skill)
    return found


def _id_from_filename(name: str) -> str | None:
    """Pull the numeric Kaggle ID out of a filename like 'engineering_10030015.pdf'."""
    m = re.search(r"(\d{5,})", name)
    return m.group(1) if m else None


def _first_or_none(matches: list[str]) -> str | None:
    for m in matches:
        # Phones often false-match on dates / IDs in resume bodies; require
        # at least 10 digits before declaring a hit.
        digits = re.sub(r"\D", "", m)
        if len(digits) >= 10:
            return m.strip()
    return None


def _extract_truth_from_text(text: str) -> dict:
    contact: dict = {}
    emails = EMAIL_RE.findall(text)
    if emails:
        contact["email"] = emails[0]
    phone = _first_or_none(PHONE_RE.findall(text))
    if phone:
        contact["phone"] = phone
    linkedin = LINKEDIN_RE.search(text)
    if linkedin:
        contact["linkedin"] = linkedin.group(0)
    github = GITHUB_RE.search(text)
    if github:
        contact["github"] = github.group(0)
    websites = [m for m in WEBSITE_RE.findall(text) if "linkedin" not in m.lower() and "github" not in m.lower()]
    if websites:
        contact["website"] = websites[0]

    truth: dict = {"is_resume": True}
    if contact:
        truth["contact"] = contact
    skills = _detect_skills(text)
    if skills:
        truth["technical_skills"] = skills
    return truth


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(
            f"CSV not found at {CSV_PATH}. Make sure the Kaggle archive is "
            "extracted under archive/Resume/."
        )

    by_id: dict[str, str] = {}
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_id[row["ID"]] = row.get("Resume_str", "")

    written = 0
    skipped: list[str] = []
    for pdf in sorted(RESUMES_DIR.glob("*.pdf")):
        truth_path = TRUTH_DIR / (pdf.stem + ".json")
        if truth_path.name in SKIP:
            continue
        kaggle_id = _id_from_filename(pdf.name)
        if kaggle_id is None or kaggle_id not in by_id:
            skipped.append(pdf.name)
            continue
        truth = _extract_truth_from_text(by_id[kaggle_id])
        truth_path.write_text(json.dumps(truth, indent=2) + "\n")
        written += 1
        print(f"  wrote {truth_path.relative_to(REPO)}")

    print(f"\nDone. Wrote {written} ground-truth file(s).")
    if skipped:
        print(f"Skipped (no Kaggle ID match): {skipped}")


if __name__ == "__main__":
    main()
