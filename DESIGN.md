# DESIGN.md


## 1. Tech stack

**Decision.** FastAPI + SQLAlchemy + SQLite on the backend; Vite + React +
TypeScript + Tailwind on the frontend; OpenAI-compatible client pointed at
TritonAI (Claude). PDF text via `pypdf`, DOCX via `python-docx`, images
passed straight to Claude vision; `pdf2image` only as a fallback for
text-empty PDFs.

**Why.** I knew this stack and could move fast. SQLite + WAL is enough for
a single recruiter; Postgres would be overkill for the deadline. React +
Tailwind makes the dashboard / Verify / Schema pages feasible as a real
SPA rather than a server-rendered form.

**Provenance.** Mine. The tool occasionally suggested adding heavier deps
(Alembic, shadcn) but I kept it minimal.

---

## 2. Validity gate before scoring

**Decision.** The model returns both `is_resume` (boolean) and
`validity_confidence` (0–1). Any document with `is_resume=false` OR
`validity_confidence < 0.5` is marked **Rejected document** and skipped for
scoring. The recruiter can still open and edit it.

**Why.** Recruiters get random files dropped at them — invoices, blank
pages, marketing PDFs. Wasting an LLM scoring call on those is silly. The
threshold is a config knob (`validity_confidence_threshold`).

**Provenance.** Mine. Copilot originally proposed only the boolean flag; I
added the confidence score and the threshold gate so recruiters could tune
the rejection rate.

---

## 3. Two-call extraction-then-score, not one combined call

**Decision.** Extraction (resume → JSON) and scoring (JSON + JD → score) are
two separate LLM calls with two separate versioned prompts (`extract-v4`,
`score-v1`). The extraction result is persisted before scoring runs.

**Why.** Extraction is reusable across many JDs; re-running scoring against
a different JD shouldn't require re-extracting. Splitting also makes each
prompt easier to test independently in `eval/`.

**Provenance.** Mine. The tool initially produced a combined prompt; I
split it.

---

## 4. Opt-in alias learning (not automatic)

**Decision.** Saving corrections on the Verify page does NOT teach the alias
table by default. The recruiter has to tick a checkbox labelled "Apply skill
corrections to alias learning for future resumes."

**Why.** Resume edits are often one-offs ("their resume says NodeJS but the
person is calling themselves a 'Node person' in their cover letter"). Auto-
learning poisons the alias table from edits that aren't actually canonical.

**Provenance.** Mine, post-mortem. The first version learned automatically
and I noticed the alias table was filling with garbage after a few test
runs. I told the tool to add the opt-in checkbox and the corresponding
backend flag.

---

## 5. Custom fields as schema extensions

**Decision.** Recruiters can define typed custom fields
(`name`, `description`, `type ∈ {text, bool, list, number}`). Definitions
are injected into the extraction prompt as a `# Custom fields to extract`
block. Extracted values land under a top-level `custom: {}` object in the
JSON.

**Why.** "Recruiter wants to extract X" was the obvious extension axis. A
typed field with a description is enough to drive an LLM extraction without
schema migrations.

**Provenance.** Mine for the design (typed fields, prompt injection,
`custom` namespace). Copilot wrote the CRUD endpoints + the Schema page
admin UI from that spec.

---

## 6. Async upload with task polling (not synchronous)

**Decision.** `POST /api/resumes/upload` returns **HTTP 202 Accepted** with
`{task_id, resume_id}` immediately. The frontend polls
`GET /api/resumes/tasks/{task_id}` every 1.2s. A `resume_processing_task`
row tracks status + per-stage step (`Reading document`, `AI extracting
data`, `AI scoring`, `Done`/`Rejected document`/`Failed`).

**Why.** Extraction can take 5-15s; multi-file uploads compound. Blocking
the HTTP response leaves the user staring at a spinner with no feedback.
Polling + per-stage labels makes the wait visible and survives a page
refresh (the task row is persisted).

**Provenance.** Tool-assisted. I described the desired UX (live per-row
status); Copilot proposed the persistent task model + polling protocol +
the granular step labels. I kept it as-is.

---

## 7. Resume schema overhauls (v1 → v4)

**Decision.** The extracted JSON has been rewritten three times. The current
shape (`extract-v4`):

- `contact: {name, email, phone, linkedin, github}` — grouped instead of
  flat.
- `education[]` with `institution / degree / major / gpa / start_date /
  end_date` (degree expanded from `B.S.` → `Bachelor of Science`; major
  separated from degree; dates split with the "single date = end date"
  convention).
- `experience[]` with `start_date / end_date / description_bullets` (split
  from a single free-text `dates` string).
- `projects[]` with `name / description_bullets / tags` (renamed from
  `technologies`, multiple bullets instead of one string).
- `technical_skills`, `awards`, `certificates` as flat lists.
- `calculated_yoe` summed unweighted from experience entries (internships
  count fully).

**Why.** The original schema (`hard_skills`, `years_experience`,
`{degree, university, graduation_year}`) was too coarse to be useful for
the recruiter's review and lost too much resume detail. Each iteration
was driven by a specific failure I observed:
- v1 → v2: needed full sections (experience, projects, awards,
  certificates), not just skills + yoe.
- v2 → v3: model was treating my `{}` example as a literal key and wrapping
  the answer; needed a stricter prompt + an unwrap step in the pipeline.
- v3 → v4: dates were ambiguous (one-date entries were going into a
  free-text `dates` field), degrees weren't expanded, YOE was halving
  internships when I just wanted the raw months. Rewrote the prompt
  around explicit normalization + a date-split convention.

**Provenance.** Mine for every schema change — they were prompted by
specific test cases in my own resume. The tool wrote the
prompt/test/normalize edits I asked for.

---

## 8. `concerns` field — neutral observations, NOT a score input

**Decision.** The extraction prompt now produces a top-level
`concerns: [string]` array. The model fills it with neutral, factual
observations the recruiter may want to ask about during a phone screen
(timeline gaps > ~6 months, multiple very short tenures, overlapping
full-time roles, education end date long before first listed role).
Concerns are surfaced in their own card on the Verify page; they do
**not** feed into the score.

**Why.** Recruiters shouldn't auto-deduct points for a 14-month gap —
that gap might be parental leave, a startup that failed, or a deliberate
sabbatical. The right move is to give the recruiter conversation prompts,
not silently penalize the candidate. Keeping `concerns` out of the scoring
loop also avoids tying recruiter judgement to a single LLM hallucination
about a missing date.

**Provenance.** Mine for the framing ("recruiter ask later, don't score
on it"). I asked the tool to add the field + the prompt rules + the form
section.

---

## 9. Match tiers (Excellent / Good / Average / Bad)

**Decision.** Each scored candidate is bucketed into a tier derived from
the score:

| Tier      | Score range |
| --------- | ----------- |
| Excellent | 90 – 100    |
| Good      | 80 – 89     |
| Average   | 40 – 79     |
| Bad       | 0 – 39      |

`match_tier` is computed in `match_tier_for_score()` (`backend/app/scoring/
rank.py`), surfaced on `ResumeOut`, and rendered as a coloured badge on
the dashboard. The list endpoint accepts `?tier=Excellent` for filtering.

**Why.** Numbers like "78" and "82" don't actually mean anything different
to a recruiter triaging hundreds of candidates — they need a coarse
"is this worth a phone call?" verdict. Cut-offs are deliberately wide
(40-79 = Average) because the LLM scorer is noisy at fine-grained
distinctions but reliable at the gross "great / fine / no" level. The Bad
floor is 40 instead of e.g. 70 so that "rejected on signal" is loud and
unambiguous.

**Provenance.** Mine for the cut-offs (decided in chat with the recruiter:
≥90, ≥80, ≥40, <40 = Bad). The tool implemented the helper, the
ResumeOut field, the `?tier=` query parameter, and the dashboard badge.

---

## 11. Eval dataset (small + diverse, not exhaustive)

**Decision.** `eval/dataset/` is a curated subset of the Kaggle resume
corpus — one PDF from each of 8 different categories (engineering,
healthcare, finance, etc.) plus two negatives (`invoice.txt`,
`recipe.txt`). Only one of the eight Kaggle PDFs has a hand-labelled
ground-truth JSON; the others run as smoke tests (extraction completes,
no per-field metric).

**Why.** The harness is meant to be a useful daily driver during prompt
iteration. Running the entire 927-PDF Kaggle corpus on every change is
slow and expensive. Eight diverse positives is enough to surface format
breakage (column-heavy designer resumes vs. dense finance resumes) and
the two negatives directly assert the validity gate. Hand-labelling all
ground truth would crowd out the deadline for negligible signal — the
metric arithmetic is already validated by the one labelled example.

**Provenance.** Mine for the curation strategy. Tool wrote the harness
filter that accepts `.txt` / `.md` so negatives can sit alongside PDFs.

---

## Known Limitations

Things I chose to scope *out* for the initial submission. Each one is a
real limitation, not an oversight — documented so a reviewer can see I
know where the boundaries are.

### 1. One resume row = one JD (no Candidate / Application split)

A `Resume` row today is tied to a single `scored_against_jd_id`. Deleting
a JD therefore also deletes every resume submitted under it (including
the file on disk) — see section "JD delete cascades to its resumes".

**Why it's a limitation.** In reality the same person applies to multiple
roles: one candidate, several applications. If a recruiter deletes a
"Backend" JD, a candidate who also applied to "Frontend" should keep
their profile intact under "Frontend". Today they don't — the row is gone.

**What the fix looks like.** Separate two concepts that are currently
conflated:

- `Candidate` — the extracted person (contact + extraction JSON + the
  uploaded file, one per physical resume upload).
- `Application` — the link row between a Candidate and a JD, carrying
  the `score`, `subscores`, `rationale`, `status`, and
  `scored_against_jd_id`. Deleting a JD would cascade-delete its
  Applications but leave Candidates alone.

The retroactive `POST /api/resumes/{id}/score` endpoint already treats
"extract once, score against many JDs" as a first-class flow on the
extraction side; it's just not modeled that way in the DB yet.

### 2. Alias learning is positional

`learn_from_skill_diff` pairs `raw_skills[i]` with `edited_skills[i]` —
edits that *reorder*, *add*, or *remove* skills don't teach anything.
Fine for the common "fix a typo / canonical name" case; silently drops
the signal in others. Fixing it well needs a real sequence-alignment
step (LCS or similar) which I skipped for the deadline.

### 3. `is_active` column is dead weight in the JD table

The "active JD" concept is gone from the API and UI, but the column is
still on `JobDescription` (always false) because dropping a SQLite column
means rewriting the table. Harmless; just noise for anyone inspecting
the schema. A future migration sweep can remove it.

### 4. Retroactive scoring is synchronous

`POST /api/resumes/{id}/score` blocks on one LLM call. For a single
re-score that's fine (~5-15s), but "re-score all resumes against this
new JD" would need the same 202+polling+task-row plumbing the upload path
uses. Not built yet because nothing in the UI triggers it.

### 5. No sequence-alignment on the `concerns` diff

`concerns` survives the Verify round-trip (it's in `diffed_keys`) but the
correction log stores it as an opaque blob swap. If the user edits one
entry in a 5-item concerns list, the log shows the whole list changing.
Same limitation as aliases; same deferred fix.

### 6. ID-based URLs are guessable

`/resumes/5`, `/api/resumes/5/file` — auto-incrementing integer IDs are
public. Single-recruiter app with no auth, so this is fine in practice,
but anyone with network access to the dev server can iterate IDs.
Multi-tenant deployment would need to swap to opaque IDs (UUIDs) or add
auth before exposing the API.

### 7. Tier filtering happens in Python

`GET /api/resumes?tier=Excellent` fetches every matching row from the DB
and bucketizes in Python (because `match_tier` is derived from `score`,
not stored). Acceptable for the demo dataset; would need a stored
`match_tier` column or a DB-side CASE expression past ~10K rows.
