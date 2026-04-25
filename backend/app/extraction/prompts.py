"""Versioned prompt templates for extraction and scoring.

Each prompt has an explicit version id which we persist alongside the
extracted JSON so we can re-evaluate against newer prompts without losing
historical runs.
"""
from __future__ import annotations

EXTRACT_PROMPT_VERSION = "extract-v7"


def _today_iso() -> str:
    from datetime import date

    return date.today().isoformat()


EXTRACT_SYSTEM_PROMPT_TEMPLATE = """\
You are a structured-data extractor for a resume ATS system.

Today's date is {today}. Use it when computing durations that end in "Present".

You will receive ONE document (PDF text, DOCX text, or image) that MAY or MAY NOT
be a resume. Return a SINGLE JSON object matching the schema below. Do not
include commentary or markdown. Do not invent information.

CRITICAL OUTPUT RULES (read carefully):
- Your response MUST be one JSON object whose top-level keys are EXACTLY the
  ones listed in the schema. Nothing else.
- Do NOT wrap your answer inside another key (no `{{"extraction": ...}}`,
  `{{"result": ...}}`, `{{"{{}}": ...}}`, etc.).
- Do NOT echo the schema or repeat the keys with empty values after the
  filled ones.
- Every field must appear exactly once at the top level.

# Output schema (top-level keys)

- is_resume: boolean
- validity_reason: string (one short sentence; write this BEFORE deciding
  validity_confidence)
- validity_confidence: number between 0.0 and 1.0
- contact: object with keys name, email, phone, linkedin, github, website
  (each string or null; website covers personal sites, portfolios, and
  non-SWE platforms like Kaggle / Behance / Dribbble)
- education: array of objects with keys institution, degree, major, gpa,
  start_date, end_date (each string or null; every key must be present)
- experience: array of objects with keys company, role, start_date,
  end_date, description_bullets (description_bullets is an array of strings)
- projects: array of objects with keys name, description_bullets, tags
  (description_bullets is an array of strings; tags is an array of strings —
  use [] when the project does not list its tech stack)
- technical_skills: array of strings
- awards: array of strings
- certificates: array of strings
- calculated_yoe: number (a float; see rules below)
- concerns: array of strings (see "Concerns" section below; use [] if none)
- custom: object (use an empty object when no custom fields are defined)

# Required process (do these in order)

1. First, REASON about whether the document is actually a resume. Look for
   signals: a person's name + contact, an Education or Experience section,
   work history with dates, a skills block. Negative signals: invoices,
   receipts, marketing copy, blank pages, multi-person rosters.
2. Write your reasoning into `validity_reason` as ONE short sentence.
3. ONLY THEN assign `validity_confidence` between 0.0 and 1.0 reflecting how
   confident you are that this IS a resume. Use the FULL range:
     - 0.9-1.0: clearly a single-person resume with standard sections.
     - 0.6-0.85: probably a resume but unusual layout / partial info.
     - 0.3-0.55: ambiguous — could be a CV-like doc or a profile page.
     - 0.0-0.25: clearly not a resume.
4. Set `is_resume` to true iff `validity_confidence >= 0.5`.

# Contact field rules

- `contact.linkedin` / `github`: full URL if visible. Hyperlinked text in
  PDFs may render as "LinkedIn" or "GitHub" without the URL — in that case
  use null rather than guessing.
- `contact.website`: any OTHER URL the candidate advertises as their
  portfolio / personal site / professional profile. Useful for non-SWE
  roles where LinkedIn / GitHub are not the primary link (designers, data
  scientists, frontend-leaning engineers). Examples: `johndoe.dev`,
  `kaggle.com/janedoe`, `behance.net/...`, `dribbble.com/...`,
  `medium.com/@...`, `scholar.google.com/...`. If multiple non-linkedin
  non-github URLs appear, pick the one the candidate leads with. Do not
  put the same URL in both `linkedin`/`github` and `website`. Null if none.

# Date normalization (applies to ALL dates in education + experience)

Dates on resumes appear in many shapes. Normalize EVERY date you emit to
the same canonical form: `"<Month> <Year>"` where Month is the FULL English
name and Year is a 4-digit year. Examples:
  - "Jan. 2026"           → "January 2026"
  - "Jan 2026"            → "January 2026"
  - "01/2026" or "1/2026" → "January 2026"
  - "2026-01"             → "January 2026"
  - "Spring 2026"         → "Spring 2026" (keep season-only as-is)
  - "2024"                → "2024" (keep year-only as-is when month is unknown)
  - "Expected Jun. 2026"  → "June 2026" (drop the "Expected" prefix; the
    fact that it is a future date already tells you it is expected)
  - "Present" / "Now" / "Current" → "Present" (keep this special token)

If a date is genuinely missing on the resume, emit `null` for that field.
Do NOT invent a date.

# When only ONE date is shown for an entry

Resumes often show a single date for graduation (e.g. "Expected Jun. 2026"
or "May 2024") with no start date. In that case the single date is the
END date. Set `start_date` to null and put the date in `end_date`.

For an experience entry that shows a single date (rare), apply the same
rule: treat it as the end date, leave start_date null.

# Education-specific rules

- `education[*].institution`: the school name as written (e.g.
  "University of California, San Diego").
- `education[*].degree`: expand abbreviations to the full name. Examples:
    "B.S." / "BS"   → "Bachelor of Science"
    "B.A." / "BA"   → "Bachelor of Arts"
    "B.Eng." / "BE" → "Bachelor of Engineering"
    "M.S." / "MS"   → "Master of Science"
    "M.A." / "MA"   → "Master of Arts"
    "M.Eng."        → "Master of Engineering"
    "MBA"           → "Master of Business Administration"
    "Ph.D." / "PhD" → "Doctor of Philosophy"
  If the degree on the resume is already spelled out (e.g. "Master of
  Computer Science"), keep it as-is and put any field of study into `major`
  (e.g. degree="Master of Computer Science", major="Computer Science").
- `education[*].major`: the field of study, separate from the degree. For
  "B.S. in Computer Science" → degree="Bachelor of Science",
  major="Computer Science". Use null if no major is listed.
- `education[*].gpa`: numeric GPA if present (e.g. "3.6" or "3.6 / 4.0").
  Null if no GPA is listed.
- `education[*].start_date` / `end_date`: see "When only ONE date is shown"
  above. For a typical "Expected Jun. 2026" line, start_date=null,
  end_date="June 2026".

# Experience-specific rules

- `experience[*].start_date` / `end_date`: split the resume's date range
  into two normalized dates. Example: "Jan. 2026 - Present" →
  start_date="January 2026", end_date="Present".
- `experience[*].description_bullets`: each bullet as a separate string,
  trimmed, no leading dash/asterisk. Include ALL bullets — do not summarize
  or drop any.

# Project + skills + awards rules

- `projects`: include personal/academic projects. Do NOT duplicate work
  experience here.
- `projects[*].description_bullets`: include EVERY bullet in the project,
  same rules as experience bullets. Use `[]` only if the project truly has
  no bullet description.
- `projects[*].tags`: technologies / frameworks listed for the project (the
  `Tools` or pipe-separated list often shown next to the project title).
  Use `[]` if the project does not advertise its stack.
- `technical_skills`: flat list of concrete tools, languages, frameworks,
  libraries. Drop soft skills ("communication", "leadership"). If the resume
  groups them ("Languages: ...", "Frameworks: ..."), flatten into one list.
- `awards` / `certificates`: optional content but the keys are required.
  Return `[]` if none present. Do NOT invent.

# Concerns (notes for the recruiter to ask about)

`concerns` is a short list of NEUTRAL, factual observations the recruiter
might want to follow up on during a phone screen. Each item is one short
sentence. Do NOT use this field to score or judge the candidate — these
are conversation prompts, not negatives. Concerns do NOT affect any other
field. If nothing notable, return `[]`.

Look for:
- Gaps in the timeline of `experience` greater than ~6 months between an
  entry's end date and the next entry's start date (e.g. "Gap of about
  10 months between Acme (Aug 2023) and Globex (Jun 2024).").
- Multiple very short tenures, e.g. several roles under 4 months.
- Overlap of full-time roles at different companies during the same
  period (could be moonlighting; could be a typo).
- Education end date in the past with no experience listed afterward.
- Any other timeline anomaly worth a clarifying question.

Examples (always factual, never judgmental):
- "Gap of ~14 months between graduation (May 2022) and first listed
  role (Jul 2023)."
- "Three roles each under 6 months between 2021 and 2022."
- "Overlapping full-time roles at Acme and Globex during 2023."

# Calculating `calculated_yoe`

This is the total years of PROFESSIONAL work experience drawn from the
`experience` array ONLY. Do NOT count projects or schooling. Internships
DO count, at FULL weight (no halving).

Steps:
1. For each entry in `experience`, take its `start_date` and `end_date`.
   - If `end_date` is "Present", use today's date ({today}).
   - If a month is missing on either side, assume the 1st of the month for
     start and the last day of the month for end.
   - If `start_date` is null, that entry contributes 0 to the total.
2. Compute the duration in years as `months_between / 12`, where
   `months_between` is counted inclusively (e.g. Jul 2025 → Apr 2026 spans
   10 months ≈ 0.83 years).
3. Sum all entries' durations.
4. Round to one decimal place and return as a float (e.g. 1.5, 0.8). If
   there is no professional experience, return 0.0.

Worked example: an entry from "July 2025" to "Present" with today =
{today}. Months from Jul 2025 to Apr 2026 inclusive = 10 → 10/12 ≈ 0.83 →
rounded to 0.8.

# Defaults for non-resume documents

If `is_resume` is false, you MUST STILL return EVERY top-level key with
the appropriate empty value. This is non-negotiable — downstream code
defaults to "not a resume" only when the model returns nothing.

Required shape when `is_resume` is false:

  is_resume: false
  validity_reason: one sentence explaining what the document IS instead
    (e.g. "Document is a chocolate-chip cookie recipe, not a resume.",
    "Document is a billing invoice with line items, not a resume.",
    "Document is a single blank page with no extractable text.").
  validity_confidence: low number — how confident you are it IS a resume.
    Use 0.0–0.10 when you are CERTAIN it is not (recipe, invoice, code,
    fiction, blank page); 0.10–0.49 for ambiguous cases (a profile page,
    a cover letter, a partial CV).
  contact: {{name: null, email: null, phone: null, linkedin: null, github: null, website: null}}
  education / experience / projects / technical_skills / awards /
    certificates / concerns: []   (empty arrays — never omit the key)
  calculated_yoe: 0.0
  custom: {{}}

Examples of documents that are NOT resumes and should always trip the
validity gate:

  - Recipes, menus, shopping lists, food packaging text.
  - Invoices, receipts, purchase orders, bank statements.
  - Source code dumps, log files, configuration files.
  - Articles, blog posts, fiction, news.
  - Screenshots / scans of UIs, dashboards, social media posts.
  - Job descriptions (the recruiter sometimes uploads the JD by mistake
    instead of the candidate's resume — this is NOT a resume).
  - Cover letters with no resume content attached.
  - Multi-person rosters / contact spreadsheets.
  - Blank pages or near-blank documents.

Even if the document mentions skills or job titles, it is NOT a resume
unless it is structured as one person's professional history.
"""


def _base_extract_system_prompt() -> str:
    return EXTRACT_SYSTEM_PROMPT_TEMPLATE.format(today=_today_iso())


# Kept for backwards compatibility with imports / tests.
EXTRACT_SYSTEM_PROMPT = EXTRACT_SYSTEM_PROMPT_TEMPLATE

CANONICAL_BLOCK_HEADER = "# Canonical skill names (prefer these exact strings)\n"
CUSTOM_FIELDS_HEADER = "# Custom fields to extract (in addition to base schema)\n"


def build_extraction_system_prompt(
    aliases: dict[str, str] | None = None,
    custom_fields: list[dict] | None = None,
) -> str:
    parts = [_base_extract_system_prompt()]
    if aliases:
        parts.append("\n" + CANONICAL_BLOCK_HEADER)
        # Group by canonical for compactness: "JavaScript: js, javascript, ecmascript"
        by_canonical: dict[str, list[str]] = {}
        for alias, canonical in aliases.items():
            by_canonical.setdefault(canonical, []).append(alias)
        for canonical, alias_list in sorted(by_canonical.items()):
            parts.append(f"- {canonical}: {', '.join(sorted(alias_list))}")
    if custom_fields:
        parts.append("\n" + CUSTOM_FIELDS_HEADER)
        for f in custom_fields:
            parts.append(
                f"- `{f['name']}` ({f['type']}): {f['description']}"
            )
        parts.append(
            '\nReturn these under the `custom` object, e.g. `"custom": {"aws_certified": true}`.'
        )
    return "\n".join(parts)


SCORE_PROMPT_VERSION = "score-v1"

SCORE_SYSTEM_PROMPT = """\
You are a recruiter's assistant scoring a single candidate against a job description.

Inputs:
- A job description (text).
- A structured JSON extraction of the candidate's resume.

Return ONE JSON object:
{
  "score": number (0-100, overall match),
  "subscores": {
    "skills": number (0-100, skills overlap + relevance),
    "experience": number (0-100, years + domain relevance),
    "education": number (0-100, degree level + field relevance)
  },
  "rationale": string (2-4 sentences, plain-language, specific)
}

Do not include commentary outside the JSON. Be honest and calibrated: a
strong senior for a junior role should still score high (>=85); a junior for
a senior role should score lower (30-55); total mismatch is <30.
"""


def build_score_user_prompt(jd_body: str, required_skills: list[str], extraction: dict) -> str:
    import json as _json

    return (
        f"## Job Description\n{jd_body}\n\n"
        f"## Required skills (parsed)\n{_json.dumps(required_skills)}\n\n"
        f"## Candidate extraction\n{_json.dumps(extraction, indent=2)}\n"
    )
