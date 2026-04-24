# Plan — Resume ATS (Doc Scanner Assignment 2)

## Context

CSE 190 Assignment 2 ("Document Scanner"). The domain is **resume screening for recruiters**. A recruiter sets a job description once; applicants' resumes (PDF, DOCX, image) are uploaded; an LLM extracts a structured JSON for each (name, email, education, YOE, normalized hard skills, plus a validity flag) and ranks each resume against the current JD. The recruiter reviews/corrects the extraction, and those corrections feed two learning mechanisms: a **skills-alias dictionary** and **custom fields** (recruiter-defined schema extensions), so future extractions get progressively more consistent and more tailored to the recruiter's pipeline.

Deadlines: **Initial submission Fri Apr 24**, review Apr 28–29, **Final Fri May 1**. New requirements will land after Apr 24 — the design must extend gracefully.

---

## Tech stack (decided)

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | **React + TypeScript + Vite** | SPA gives a real dashboard w/ filters, sortable tables, per-candidate edit flow. |
| UI lib | **shadcn/ui + Tailwind** | Fast to build a clean dashboard; composable table/dialog primitives. |
| Charts | **Recharts** | YOE distribution, skill frequency, score histogram. |
| Backend | **FastAPI (Python 3.11)** | Best ecosystem for PDF/DOCX/image pipeline; clean async handlers. |
| ORM | **SQLAlchemy 2.x + Alembic** | Schema migrations matter — custom-fields feature evolves the DB. |
| DB | **SQLite** (file `app.db`) | Zero-ops persistence; sufficient for single-recruiter scope. |
| LLM | **Claude via TritonAI** (OpenAI-compatible) | Class-provided gateway. Use `openai` Python SDK w/ `base_url` + Triton key. Model name per Triton hub (likely `claude-sonnet-4-5` or similar). |
| File storage | **Local `./data/uploads/`** | Deferred deploy; will swap for an S3 adapter later behind a thin `Storage` protocol. |
| PDF parse | **pypdf** (text) + **pdf2image** (rasterize when needed) | Text-first; fall back to image for scanned PDFs. |
| DOCX parse | **python-docx** (text) | Structured extraction straight from XML. |
| Image | pass directly to Claude vision | No OCR needed — model is multi-modal. |
| Testing | **pytest** + **pytest-asyncio** | Standard. |
| Eval harness | **Typer** CLI | Sub-commands for single-doc runs, dataset runs, subset runs. |
| Dev runner | **Makefile** targets | `make dev`, `make test`, `make eval`. |

**No auth.** Single-recruiter app. HITL verification is the recruiter correcting extractions (satisfies the "put the user in the loop" requirement).

---

## Repository layout

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + CORS
│   │   ├── api/                    # route modules: resumes, jd, aliases, custom_fields, dashboard
│   │   ├── db/
│   │   │   ├── models.py           # SQLAlchemy models
│   │   │   └── session.py
│   │   ├── extraction/
│   │   │   ├── pipeline.py         # orchestrates: detect type → parse → prompt → normalize
│   │   │   ├── prompts.py          # prompt templates (with alias + custom-field injection)
│   │   │   ├── schema.py           # Pydantic models for extracted JSON (dynamic w/ custom fields)
│   │   │   ├── llm_client.py       # thin provider adapter (OpenAI-compatible → TritonAI)
│   │   │   └── normalize.py        # post-extraction alias pass
│   │   ├── scoring/
│   │   │   └── rank.py             # JD + extracted JSON → score + subscores + rationale
│   │   └── learning/
│   │       ├── aliases.py          # diff corrections → alias table
│   │       └── custom_fields.py    # CRUD + prompt-schema builder
│   ├── alembic/
│   ├── tests/                      # unit tests for extraction, scoring, normalize
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx       # candidate table + filters + charts
│   │   │   ├── UploadJD.tsx
│   │   │   ├── Upload.tsx          # drag-drop resume upload
│   │   │   ├── Verify.tsx          # HITL edit view for a single candidate
│   │   │   └── Schema.tsx          # custom-fields + aliases admin
│   │   ├── api/                    # typed fetch wrappers
│   │   └── components/
│   └── vite.config.ts
├── eval/
│   ├── dataset/
│   │   ├── resumes/                # pdfs, docx, png/jpg files
│   │   ├── ground_truth/           # *.json hand-labeled
│   │   ├── negatives/              # non-resumes, blanks (for validity gate)
│   │   ├── edge_cases/             # multi-column, scanned, etc.
│   │   └── jd_pairs/               # {jd.md, resumes/, expected_ranking.json}
│   ├── harness.py                  # Typer CLI entry
│   ├── metrics.py                  # field-level EM, skills F1, Spearman rank corr
│   └── report.py                   # summarized output
├── data/
│   ├── uploads/                    # (gitignored) runtime files
│   └── app.db                      # (gitignored)
├── transcripts/                    # 3 agent-interaction transcripts (assignment req)
├── DESIGN.md
├── README.md
└── Makefile
```

---

## Data model (SQLite)

```
job_description (singleton row — one active JD at a time)
  id, title, body_md, required_skills_json, created_at

resume
  id, filename, mime_type, storage_path, uploaded_at,
  is_resume (bool), validity_confidence, validity_reason,
  extraction_raw_json, extraction_edited_json,
  score, subscores_json, rank_rationale,
  scored_against_jd_id  -- FK to jd snapshot

skill_alias
  alias TEXT, canonical TEXT, source (seed|user_correction), frequency INT, created_at
  PK (alias)

custom_field
  id, name, description, type (text|bool|list|number), created_at

custom_field_value
  resume_id, custom_field_id, value_json  -- edited + raw mirrored w/ raw_json

correction_log
  id, resume_id, field_path, before_value, after_value, created_at
  -- feeds both alias learning and future few-shot retrieval
```

Why `extraction_raw_json` and `extraction_edited_json` both: the raw is the ground-truth record of what the LLM produced (useful for retroactive eval and for training the alias dictionary via diff); the edited is what the dashboard displays.

---

## Extraction pipeline (the core LLM loop)

`backend/app/extraction/pipeline.py`:

1. **Ingest** — sniff mime, route: PDF → pypdf text + (if text density is low) rasterize first 2 pages; DOCX → python-docx text; image → pass through.
2. **Prompt build** — compose a single prompt with four sections:
   - System: role + strict JSON-schema instruction.
   - **Canonical skill names** (injected): top-N aliases from `skill_alias` table, as `alias → canonical` lines. Prompt caching key depends on this block hash.
   - **Custom field definitions** (injected): name, type, description for each `custom_field` row.
   - User message: the resume content (text and/or images as multi-modal parts).
3. **LLM call** — OpenAI-compatible chat completion to TritonAI, `temperature=0`, `response_format={"type":"json_object"}`. Single call returns:
   ```json
   {
     "is_resume": true,
     "validity_confidence": 0.95,
     "validity_reason": "Contains standard resume sections...",
     "name": "...", "email": "...",
     "education": [{"degree":"...", "university":"..."}],
     "years_experience": 4.5,
     "hard_skills": ["Python","Django",...],
     "custom": {"aws_certified": true, ...}
   }
   ```
4. **Validity gate** — if `is_resume=false` or `validity_confidence < 0.5`, persist with flag but skip scoring; dashboard filters them out by default.
5. **Post-extraction normalize** (`normalize.py`) — run skills through `skill_alias` map in Python (deterministic second pass).
6. **Score** — call `scoring/rank.py` with extracted JSON + active JD, get `{score, subscores:{skills,experience,education}, rationale}`.
7. **Persist** — write everything to `resume` and `custom_field_value` tables.

**Separately testable:** `pipeline.extract(file_path, provider=...)` is a pure function over inputs + DB reads. The harness imports it directly without starting FastAPI.

---

## Scoring / ranking

`scoring/rank.py` — second LLM call. Input: extracted JSON (after normalization) + JD body + JD required-skills list. Output: `{score: 0-100, subscores: {skills, experience, education}, rationale: str}`. `temperature=0`. The JD text is stable across uploads → prompt-caching candidate.

Ranking on the dashboard is simple `ORDER BY score DESC`. Rationale is surfaced as a tooltip / expandable row.

---

## Feedback loop (the "corrections improve future extractions" requirement)

### Mechanism A — learned skills-alias dictionary

- Every save on the Verify view diffs `extraction_edited_json.hard_skills` against `extraction_raw_json.hard_skills`. Pairs where a raw token was replaced by a canonical form get written to `skill_alias` with `source='user_correction'`, incrementing `frequency` on repeats.
- Prompt injection: top-200 aliases by frequency → included in the system prompt's "Canonical skill names" block.
- Code-side safety net: `normalize.py` runs the same map deterministically after every extraction (catches misses and guarantees consistency for dashboard filters like "has Django").
- University/degree canonicalization uses the same mechanism under the hood with a separate `entity_alias` table keyed by type (`skill | university | degree`) — single table with a `kind` column.

### Mechanism B — custom fields

- `Schema` page lets the recruiter create/edit fields: `name`, `type (text|bool|list|number)`, `description`.
- On every extraction, the prompt's schema is built dynamically from `custom_field` rows. Description is how we coax the model to extract each field without exhaustive examples.
- Custom fields become first-class citizens in the dashboard (auto-added columns and filters) and in the Verify edit form.
- Extends the assignment cleanly: when post-Apr-24 requirements land, custom fields are an obvious surface to plug into.

### Correction log

`correction_log` captures every field-level edit. Later (stretch) we can use it for few-shot retrieval — pull the most-similar prior corrections into the prompt for high-uncertainty cases. Out of scope for initial submission.

---

## UX flows (frontend pages)

1. **UploadJD.tsx** — paste/upload JD text or file; parses required-skills via a quick LLM call; stores as the singleton active JD.
2. **Upload.tsx** — drag-drop multi-file upload (PDF/DOCX/images). Progress + per-file status. On completion, redirect to Verify for review.
3. **Verify.tsx** — side-by-side: rendered document on the left (PDF iframe / docx-preview / image), editable JSON form on the right. Inline diffs where edits differ from raw. Save → commit edited JSON and triggers alias-learning.
4. **Dashboard.tsx** — sortable/filterable candidate table (rank, name, YOE, top skills, score). Filters: min-YOE slider, skill multi-select (operates on canonical), custom-field filters, validity (exclude non-resumes toggle). Charts panel: YOE histogram, top-20 skill frequency, score distribution.
5. **Schema.tsx** — tabs: Custom Fields (CRUD) + Skill Aliases (table, editable).

---

## Evaluation dataset + harness

### Dataset composition (≈30 items)

- `dataset/resumes/` + `ground_truth/` — **15 positive resumes**, mixed PDF / DOCX / PNG, each with a `*.json` ground-truth file (the five base fields, no custom fields). Publicly-sourced (e.g., Kaggle "Resume Dataset") augmented with hand-labeled cases.
- `dataset/negatives/` — **~5 non-resumes** (receipts, random docs, blank PDF, 1-sentence garbage). Ground truth: `is_resume=false`.
- `dataset/edge_cases/` — **~5** multi-column, scanned low-quality, multi-page academic CVs, non-English names, date ranges like "2019–present".
- `dataset/jd_pairs/` — **3–4 JD folders** sourced from Kaggle's "Job Description" dataset, each with 5 resumes + an `expected_ranking.json` partial order.

### Metrics (`eval/metrics.py`)

- **Validity gate:** precision/recall on `is_resume` across positives + negatives.
- **Field extraction:** exact-match on name, email; normalized-equality on university and degree; absolute error on YOE; **skills F1** (after alias normalization on both sides).
- **Ranking:** Spearman rank correlation between predicted and expected order per JD pair; top-K (K=2) precision.

### Harness (`eval/harness.py`) — Typer CLI

```
# single doc, prints diff against ground truth
eval run --file dataset/resumes/jane.pdf

# full dataset, summary table
eval run --dataset dataset/

# subset by tag
eval run --dataset dataset/ --subset edge_cases

# ranking test only
eval rank --jd-pair dataset/jd_pairs/python_ml/

# model comparison
eval run --dataset dataset/ --model claude-sonnet-4-5
eval run --dataset dataset/ --model claude-haiku-4-5

# report: write eval/out/<timestamp>/report.md
eval report --run <id>
```

No code edits needed to switch single/subset/full → satisfies the "run on subsets without editing program" requirement via CLI flags.

---

## Prompt management

Prompts live in `backend/app/extraction/prompts.py` as versioned string constants (`EXTRACT_PROMPT_V1`, etc.). Version id is persisted on each `resume.extraction_raw_json` so we can re-run eval against fresh prompts without losing history. A single `build_extraction_prompt(aliases, custom_fields) -> str` helper composes the final prompt. Same pattern for `scoring/rank.py`.

---

## Verification plan

1. **Backend unit tests** — `pytest backend/tests/` covers: `pipeline.extract` with mocked LLM, alias diff/learning, custom-field schema builder, scoring rank output parsing, validity-gate threshold behavior.
2. **Extraction eval** — `make eval` runs the full harness against `eval/dataset/`, prints summary metrics. Target bars:
   - Email EM ≥ 0.95
   - Skills F1 (post-alias) ≥ 0.75
   - YOE MAE ≤ 1.0 years
   - Validity gate precision ≥ 0.9, recall ≥ 0.9
   - Per-JD Spearman ≥ 0.5
3. **End-to-end manual smoke** — `make dev`, upload a JD, upload 3 resumes, verify edits persist after restart (kill process, reopen), confirm a corrected skill alias ("py" → "Python") appears in the next upload without further correction.
4. **Demo video** — 3–5 min screencast covering upload → verify → dashboard filter → alias persistence → eval harness run.

---

## Milestones

- **Thu Apr 23 (today)** — Scaffold repo: FastAPI skeleton, Vite skeleton, SQLAlchemy models, TritonAI client adapter, env wiring (`.env` with `TRITON_API_KEY`, `TRITON_BASE_URL`, `LLM_MODEL`).
- **Fri Apr 24 (initial submission)** — End-to-end happy path: upload → extract → verify edit → score → dashboard. Alias-learning wired. 8+ dataset items w/ ground truth. Harness runs. README + DESIGN.md + 3 transcripts + demo video.
- **Mon Apr 27** — Fill out dataset to ~30, hit metric bars, prep review log.
- **Tue Apr 28 / Wed Apr 29** — Review session + incorporate feedback.
- **Fri May 1** — Final submission: post-review changes + the post-initial-submission new requirements (custom fields likely becomes the delivery vehicle if the add is schema-shaped; otherwise adapt).

---

## Assignment requirements — coverage matrix

| Requirement | Covered by |
| --- | --- |
| GUI | React SPA |
| Upload documents | Upload.tsx + FastAPI `/api/resumes` |
| Structured info via GenAI | `pipeline.extract` → Claude via Triton |
| Multi-modal (images/PDFs) | Claude vision for images + rasterized PDFs |
| User verifies/edits ambiguity | Verify.tsx side-by-side editor |
| Corrections improve future extractions | Alias dictionary + custom fields + correction_log |
| Persist across sessions | SQLite `app.db` + `./data/uploads/` |
| Useful task | Dashboard aggregation + filters + JD-vs-resume ranking with rationale |
| Evaluation dataset (positive + negative) | `eval/dataset/` — positives, negatives, edge cases, JD pairs |
| Extraction separately testable | `pipeline.extract` is pure; eval harness imports it directly |
| Automatable eval, single + subsets via flags | Typer CLI (`--file`, `--subset`, `--dataset`, `--model`) |
| 3 agent transcripts | `transcripts/` |
| DESIGN.md, README.md, demo video | Top-level |

---

## Open risks

- **TritonAI multi-modal support** — confirm Triton gateway passes image parts through to Claude. If it strips them, fallback: OCR PDFs/images with a local tool (`pypdf` text for text-PDFs works; scanned PDFs + images need a plan B like `pytesseract`). Verify on day 1.
- **PDF variance** — scanned/low-quality PDFs are the biggest extraction failure mode. Rasterize-first-N-pages fallback mitigates.
- **Ranking determinism** — even at temp=0, LLM scores can drift ±2 points. Report subscores + rationale, treat the number as an ordering signal, not a truth.
- **Deploy later** — local-only for now is agreed. Storage adapter (`Storage` protocol in `app/storage.py`) abstracts file I/O so swapping to S3 is a single-class change.
