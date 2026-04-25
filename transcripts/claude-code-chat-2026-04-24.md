# Claude Code Chat Transcript — Resume Parsing Overhaul

Date: 2026-04-24
Model: Claude Opus 4.7 (Claude Code CLI)

This transcript captures the full session that rewrote the extraction
schema, fixed the LLM-wrapper bug, redesigned the JD page, added resume +
JD delete, rebuilt the Verify editor, and produced README.md / DESIGN.md.

---

## Turn 1 — Read the project, fix three things

**User:**

> Read the readme.md to understand how my project is working right now.
>
> I want you to help me fix these. Right now my goal is to get the resume
> parsing part working correctly. Don't worry about ranking the resume
> based on the JD or rejecting resumes for now.
>
> - it looks like it remember[s] the uploaded job descriptions ... is there
>   a way we can read, update, and delete those previous histories? There
>   is a ton of space on the right for you to make a list of previous jd
>   descriptions with metadata on title and last date modified in the /jd
>   page.
> - make uploaded resumes deletable as well
> - as you can see in the screenshots, when the recruiter uploaded the
>   resume, and click verify. It didn't extract all the information in the
>   resume correctly ... I want you to focus on making a good resume parser
>   first ... Here is a rough structure that i am thinking: { contact,
>   education[], experience[], projects, technical_skills, awards[],
>   certificates[], calculated_yoe }
> - Right now the raw json looks like this on the website: { is_resume,
>   validity_confidence (don't show on edit page), validity_reason
>   (prompt the llm to do reasoning first), hard_skills (won't be using),
>   education, custom (need this) }

**Assistant (summary):**

Read README, plan, all backend modules (`schema.py`, `prompts.py`,
`pipeline.py`, `normalize.py`, `llm_client.py`, `parse_doc.py`,
`api/jd.py`, `api/resumes.py`, `db/models.py`, `learning/aliases.py`),
all frontend pages, the eval harness, and the existing tests.

Then implemented in one pass:

- New Pydantic `ExtractedResume` schema covering contact, education,
  experience, projects, technical_skills, awards, certificates,
  calculated_yoe, custom.
- New extraction prompt (`extract-v2`) with "reason about validity first"
  instructions and an explicit confidence-scale rubric.
- Pipeline `_apply_extraction_defaults` so every key is always present.
- `normalize.py` updated: alias-normalize `technical_skills` and
  `projects[*].technologies`; institution + degree normalization now uses
  `institution` instead of `university`.
- `JobDescription` got `updated_at` plus a one-shot SQLite `ALTER TABLE`
  on startup so existing DBs migrate without Alembic.
- New JD endpoints: `GET /api/jd/{id}`, `POST /api/jd`, `PUT /api/jd/{id}`,
  `PUT /api/jd/{id}/activate`, `DELETE /api/jd/{id}`. List endpoint sorts
  by `updated_at` and exposes `is_active` + timestamps. Delete clears FK
  references on resumes / tasks.
- New `DELETE /api/resumes/{id}` removes the row + the file on disk.
- `ResumeOut.from_model` updated and `verify` now diffs the new sectioned
  keys instead of `name`/`email`/`hard_skills`.
- Frontend `api.ts` rewritten: new types (Contact, EducationEntry,
  ExperienceEntry, ProjectEntry, Extraction, JD with timestamps,
  JDSummary), CRUD methods for JDs (`createJD`, `updateJD`, `activateJD`,
  `deleteJD`, `getJD`), `deleteResume`.
- `UploadJD.tsx` rebuilt as a two-pane layout (form + JD history list with
  per-row activate/delete).
- `Verify.tsx` rebuilt with grouped Field/Group editors for every new
  section.
- `Upload.tsx` and `Dashboard.tsx` updated to read
  `extraction.contact.name` instead of `extraction.name`, and
  `calculated_yoe` / `technical_skills`.
- Backend dashboard stats query updated to `technical_skills` /
  `calculated_yoe`.
- Eval harness `_score_one` and `metrics.education_match` updated for the
  new field names. `learn_from_education_diff` now accepts both
  `institution` (new) and `university` (legacy).
- Tests rewritten/extended:
  `test_pipeline_runs_normalization_over_llm_output`,
  `test_pipeline_fills_missing_keys`, `test_normalize_skills_uses_seed_aliases`,
  `test_normalize_dedupes_after_canonicalization`,
  `test_normalize_project_technologies`,
  `test_learn_education_creates_university_alias` (`institution` shape).

Verified `make test` (18 passed) and `make check` (typecheck clean).

---

## Turn 2 — Three follow-up issues (name not showing, raw JSON has redundant fields, project bullets, GPA, YoE, projects.technologies → tags)

**User:**

> - after done parsing the candidate name didn't show up in the upload page
> - It looks like the resume got parsed correctly, it's just that they
>   don't show up on the extraction (edit to correct) on the right side.
>   Change it so that it shows all of the fields that got extracted in
>   the JSON
> - Add the GPA field in the education field, make it optional
> - Projects json structure needs a bit more work. Right now it looks like
>   this: ... // why only parse 1 bullet? parse all the bullets like the
>   experience section, make it [] ... // sometimes this technologies
>   section doesn't appear in the resume. So make this optional, and also
>   change the name from technologies to tags
> - calculated yoe is wrong as well, it got calculated as 0.5. if you
>   were to look at my resume pdf and only look at the experience section
>   it starts at July 2025 till present which is Apr 2026 (should be 0.8)
> - i am also seeing this redundant fields at the end of raw json: ...

**Assistant (summary):**

Started investigating the "redundant fields" mystery. Read pipeline,
ResumeOut, the verify flow, the LLM client. Theorized about duplicate keys
in JSON, schema echoes, `_parse_json_loose` capturing two objects, etc.

Decided to add a generic `_unwrap_if_nested` step plus a tighter prompt
example, but flagged the diagnosis was incomplete.

---

## Turn 3 — User stops the assistant and pastes the actual raw JSON

**User:**

> let me stop you there, it looks like you are having hard time trying to
> pinpoint the issue about redundant fields, for reference here is the
> full raw LLM extraction JSON. Also don't forget the fix the other
> things i mentioned in the previous prompt
>
> {
>   "{}": {  // idk why it starts with "{}" and nested inside, just move
>           // everything outside and remove the redundant field
>     ...all the real extraction...
>   },
>   "is_resume": true,
>   "validity_confidence": 0.5,
>   ...empty defaults...
> }

**Assistant (summary):**

Diagnosed: the LLM literally returned a top-level key named `"{}"` because
the previous prompt's `"custom": { ... or {} if none }` example used `{}`
verbatim, and the model echoed empty defaults at the top level. The defensive
defaults pass kept the empty echo as the "real" extraction.

Implemented:

- `_unwrap_if_nested` + `_has_filled_extraction_signal` /
  `_looks_like_extraction` helpers that recover the inner extraction by
  looking for the first nested dict with a non-empty contact/education/
  experience/projects/technical_skills field. Handles `{"{}": ...}`,
  `{"extraction": ...}`, `{"resume": ...}`, etc.
- Extraction prompt rewritten as `extract-v3`:
  - Drops the `{}` example so the model can't confuse it for a key.
  - "CRITICAL OUTPUT RULES" section explicitly forbidding wrappers and
    schema echoes.
  - Today's ISO date injected into the system prompt at request time.
  - Worked YoE example.
- Pydantic `EducationEntry` got `gpa` (optional, key always present).
- Pydantic `ProjectEntry`: `technologies` → `tags`, `description` → `description_bullets` (array).
- `normalize.py` migrates legacy projects (`technologies` → `tags`,
  `description` (str) → `description_bullets` ([str])).
- Frontend `api.ts` types updated.
- Verify page `EducationEditor` got a GPA input.
- Verify page `ProjectEditor` got a multi-line bullets textarea + a
  comma-separated tags input.
- Verify page `normalizeExtraction` migrates legacy DB rows
  (`description` → `description_bullets`, `technologies` → `tags`,
  `university` → `institution`).
- New tests: `test_pipeline_unwraps_curly_brace_wrapper`,
  `test_normalize_project_tags_new_shape`,
  `test_normalize_project_migrates_legacy_shape`.

Verified: `make test` (20 passed), `make check` clean.

---

## Turn 4 — More fixes (still wrong YoE, dates, degree expansion, UI cleanup, write README + DESIGN + transcript)

**User:**

> - Calculated years of experience is still wrong, it still shows 0.5 . I
>   looked at it and the reason was because of halfing the weight of date
>   calculation for internships. Don't half it. Get rid of weighted
>   calculation.
> - make LLM interpret dates precisely. In my resume, i put the months in
>   truncated form ... So basically i put in the first 3 characters of the
>   month. ... so just prompt the LLM model to re-correct the months
>   (truncated text, MM/YYYY, etc).
> - Education field fixes: make LLM interpret the degree precisely. For
>   example, B.S -> Bachelor of Science, B.A -> Bachelor of Arts, etc, and
>   then the field that they are pursuing Computer Science. And also
>   separate the start_date and end_date. ... For those cases, make sure
>   to tell LLM that those are end dates and not start dates. Both start
>   and end dates could be optional, don't make up any data. So the JSON
>   structure would have { institution, degree, major, gpa, start_date,
>   end_date }
> - Change the education field UI to look cleaner in the editor, right
>   now everything is clustered. Just have 1 field part row, for example
>   just University of California, San Diego in one row. Also specify
>   which row is what field. So add something like "Institution" next to
>   it.
> - Similarly for the experience field UI in the editor, everything is
>   clustered and doesn't tell which field is what. Separate start date
>   and end date. Also make sure to add like a "• " in front of each
>   bullet point of the experiences, projects, awards, and certificates.
>   so its easier to look at
> - After you have done everything, update the readme.md with current
>   implementation. ... follow [my // comments].
> - Then write a design.md document that includes most of the important
>   design decisions from the start, you can read the transcripts folder
>   to get more information about previous things i have done. ... DESIGN.md
>   a file that includes descriptions of cases where a design decision was
>   made. Describe the decision and how much you feel YOU made it, vs an
>   agentic coding tool.
> - Then, create a transcript markdown file of this entire chat, and
>   exported into transcript folder

**Assistant (summary):**

Read existing transcripts under `transcripts/` to understand what had
already happened, then implemented the lot:

Schema + prompt:
- `EducationEntry`: split `degree` from new `major`, replaced
  `graduation_date` with `start_date` + `end_date`.
- `ExperienceEntry`: replaced single free-text `dates` with `start_date`
  + `end_date`.
- Extraction prompt bumped to `extract-v4`. New sections:
  - Date normalization rules (full month + 4-digit year, or `Present`,
    or year-only when month unknown). Examples for `Jan.`, `Jan`,
    `01/2026`, `2026-01`, `Spring 2026`, `Expected Jun. 2026`.
  - "When only ONE date is shown" — treat as end date, leave start null.
  - Education-specific rules: degree expansion table
    (B.S./BS → Bachelor of Science, M.S. → Master of Science, MBA →
    Master of Business Administration, Ph.D. → Doctor of Philosophy, etc.),
    major split, GPA optional, end-date-only convention.
  - Experience-specific rules: split start/end, all bullets included.
  - YoE rules: removed the half-weight-for-internships clause; explicit
    inclusive-month duration formula; worked example using today's date.

Pipeline + normalize:
- `normalize.py`: legacy `education[*].graduation_date` → `end_date`;
  legacy `experience[*].dates` (str) → split into `start_date` + `end_date`
  via `_split_legacy_dates` (handles `-`, `–`, `—`, ` to `).
- All new keys default to `None` so older rows render.

Frontend:
- `api.ts` types updated for `major` + split dates.
- `Verify.tsx`:
  - New `RowField` component for "label on the left, single input on the
    right" rows.
  - New `BulletsEditor` component: each bullet is its own auto-sized
    textarea prefixed with `•`, with per-bullet add/remove buttons.
  - `EducationEditor` rebuilt: each entry is a card with one labeled row
    per field (Institution, Degree, Major, GPA, Start date, End date).
  - `ExperienceEditor` rebuilt: same labeled-row pattern, separate
    Start/End date inputs, bullets via `BulletsEditor`.
  - `ProjectEditor` rebuilt: Name + Tags + bullets via `BulletsEditor`.
  - Awards + Certificates groups switched to `BulletsEditor` instead of a
    single multi-line textarea.
  - `normalizeExperience` added to `normalizeExtraction` to migrate legacy
    rows that still carry a `dates` string.
- Removed obsolete `awardsText` / `certsText` derived strings.

Tests:
- `test_pipeline_runs_normalization_over_llm_output` updated to use the
  new `start_date` / `end_date` / `major` shape and asserts `extract-v4`.
- `test_pipeline_unwraps_curly_brace_wrapper` updated for the new shape.
- New: `test_normalize_migrates_legacy_education_date`,
  `test_normalize_splits_legacy_experience_dates`.

Verified: `make test` → 22 passed; `make check` → clean typecheck.

Docs:
- README rewritten end-to-end. Inline comments from the user's previous
  schema sketch are folded into a `jsonc` schema block.
- DESIGN.md created. 18 sections covering domain framing, tech stack, the
  pure-function extraction boundary, validity gate, reasoning-first
  prompting, two-call extract-then-score, two-stage skill normalization,
  opt-in alias learning, custom fields, async upload + polling, SQLite
  WAL + thread offload, tiny inline migrations vs. Alembic, JD CRUD UX,
  schema iterations v1→v4, backwards-compat normalize, eval CLI,
  versioned prompts, Verify editor UX. Each section calls out
  Decision / Why / Provenance (mine vs. tool).
- This transcript file written under `transcripts/`.

---

## Validation summary

- `make test` — 22/22 passed across all turns.
- `make check` — backend imports clean, frontend `tsc --noEmit` clean.
- No backend or frontend lint errors at session end.

---

## Turn 5 — Concerns, match tiers, pipeline status, dashboard rebuild, JD cascade, bigger bullets

**User (paraphrase):**

1. Add a `concerns` field to the extraction so the recruiter can see
   things like timeline gaps (without it feeding scoring).
2. Explain how alias-learning currently works.
3. Add `match_tiers` (Excellent ≥90, Good ≥80, Average ≥70, Bad <40)
   alongside the numeric score.
4. Dashboard cleanup: remove Verify/Edit, add "View Resume"; drop the
   skills + YOE charts; add a JD switcher; remove Min YOE / Skill
   Contains (those are custom-field territory); default to 50 per page
   with pagination; add match-tier + pipeline-status filters. Status
   dropdown: Ready, Recruiter-Call, Round 1, Round 2, Final Round,
   Rejected, Awaiting Acceptance, Accepted.
5. JD page: deleting a JD cascades to its resumes; remove "set as
   active" entirely; Upload with no JD = parse-only.
6. Bigger bullet boxes for Experience / Projects / Awards.

**Assistant (summary):**

Answered the alias-learning question inline (positional diff, teaches
`(raw_lower, edited)` pairs into `entity_alias` on opt-in, feeds top-N
into the next prompt + a deterministic post-pass).

Implemented the rest:

- `concerns: list[str]` added to `ExtractedResume`, pipeline defaults,
  prompt rules (neutral / don't score on it / look for gaps > ~6 months,
  overlapping full-time roles, several sub-4-month tenures, etc.).
  Verify page surfaces it as its own card with the bullet editor.
- `match_tier_for_score()` in `backend/app/scoring/rank.py`. I extended
  Average down to 40 to fill the 40-79 gap that wasn't spelled out in the
  requirements, with a legend in the dashboard. `ResumeOut.match_tier`
  is derived, not stored. `GET /api/resumes?tier=Excellent` filters.
- `status` column on `Resume` with an inline `ALTER TABLE` migration
  (existing rows default to `Ready`). Enum-checked `PUT /api/resumes/{id}/status`.
  `GET /api/resumes/_meta/statuses` for client enum.
- `DELETE /api/jd/{id}` now cascades: deletes every `Resume` whose
  `scored_against_jd_id` matches (files on disk removed too); confirm
  dialog + response payload reports `deleted_resumes`.
- Removed `GET /api/jd/active`, `PUT /api/jd/active`,
  `PUT /api/jd/{id}/activate`. Dropped `is_active` from JDOut/JDListOut.
  Column kept on the table.
- Upload page no longer pre-selects a JD. "No JD selected" reads
  "parse only (no scoring)".
- Dashboard rewritten from scratch: three filters (JD / tier / status),
  tier badges, per-row inline status dropdown, server-side pagination
  (50 per page, hard cap 200), "View Resume" link, no per-row edit
  button. Removed charts; removed Min YOE / Skill Contains client-side
  filters.
- `GET /api/resumes` now returns `{items, total, limit, offset}` and
  accepts `jd_id`, `status_filter`, `tier`, `limit`, `offset`.
- `BulletsEditor` bumped to `min-h-[80px]` and ≥3 rows.
- Tests: new `test_match_tier.py` covers all four bands + `None`.
  Existing pipeline test updated for `concerns` + `extract-v5`.
- Docs: README + DESIGN.md updated with the new sections, pages, and
  API surface. This transcript written.

Final verification: `make test` → 27/27 passed; `make check` clean.

---

## Turn 6 — Parse-only rescue, retry on failure, website field

**User (paraphrase):**

1. Parse-only resumes have no way to be scored later. Add a
   "Score against [select JD]" control on the Verify page (or dashboard)
   so parse-only candidates aren't trapped.
2. Failed extractions (LLM 529 / rate-limit / timeout) require re-upload.
   Add a Retry button that re-queues the already-stored file.
3. Add a `website` / portfolio field to `contact` — LinkedIn and GitHub
   don't cover designers, data scientists, frontend-leaning roles.
4. Note the "deleting a JD nukes the resumes" limitation in DESIGN.md
   under a Known Limitations header — no code fix now, but flag the
   Candidate vs. Application split as the right long-term shape.
5. Update README and DESIGN.md but keep them trim (user had hand-trimmed
   both).
6. Append this turn to `claude-code-chat-2026-04-24.md`.

**Assistant (summary):**

Backend:

- `POST /api/resumes/{id}/score` — synchronous retroactive (re)score.
  422s on rejected documents or missing extraction; 404s on unknown JD.
  Updates `score`, `subscores`, `rationale`, `scored_against_jd_id` and
  returns the refreshed `ResumeOut`.
- `POST /api/resumes/{id}/retry` — re-queues the existing
  `storage_path` through the extraction pipeline by creating a fresh
  `ResumeProcessingTask` row and returning `202 Accepted`. 410s if the
  stored file is gone. Resets the extraction state so the UI doesn't
  display stale partial data during the re-run.
- Added `website: str | None` to `Contact` and the pipeline contact
  defaults. Prompt bumped to `extract-v6` with a new "Contact field
  rules" block spelling out the non-SWE examples (Kaggle, Behance,
  Dribbble, Medium, Scholar) and the "don't put the same URL in both
  linkedin/github and website" rule.

Frontend:

- `api.scoreResume(id, jdId)` and `api.retryExtraction(id)` added, plus
  `website` in the `Contact` type.
- Verify page: new "Score against a JD" card right under the validity
  reason. Shows current JD + tier + score, offers a JD dropdown and a
  "Score now" button. Works for both parse-only and already-scored
  resumes (switches the scored JD in place).
- Verify page: new `Website / Portfolio` field in the Contact card with
  a hint about the non-SWE use case.
- Upload page: **Retry** button appears on rows whose task status (or
  persisted processing_status) is `error`. Retrying creates a synthetic
  queue row that polls the new task to completion, and removes the
  stale persisted entry from the history list.

Docs:

- README: bumped schema block to `extract-v6`; added `website` line;
  new one-sentence blurb on Retry; new bullet on Score-against-JD under
  Verify; added `POST /api/resumes/{id}/retry` and
  `POST /api/resumes/{id}/score` to the API reference. No new H2
  sections — everything folded into the existing ones, per the user's
  "keep it trim" request.
- DESIGN.md: new **Known Limitations** section listing the big one
  (Candidate vs. Application split) plus four smaller ones (positional
  alias diff, dead `is_active` column, synchronous retroactive scoring,
  no sequence alignment on `concerns`).
- This appendix written.

Tests:

- Updated fixture dict + expected-shape assertion to include the
  `website` key.
- Bumped `extract-v5` → `extract-v6` in the version assertion.

Final verification: `make test` → 27/27 passed; `make check` clean.

---

## Turn 7 — Bug-fix bundle, per-JD custom fields, eval dataset, requirements audit

**User (paraphrase):**

1. Drag-and-drop into the Upload box doesn't work (only click).
2. Big bug: after applying a skill correction with the alias-learning
   checkbox, deleting the resume returns 500. Same when deleting the
   parent JD. Also `FastAPI → fastapi` in the skills field never appears
   in the alias list — the save itself isn't working.
3. Custom-field schema should be per-JD, not global. Move the editor onto
   the Job Description page; add a button there to re-run AI extraction
   on every resume under that JD.
4. Verify the assignment requirements for the April 24 initial submission
   are met. Kaggle resume PDFs are in `archive/` — use a few for the eval
   dataset.

**Assistant (summary):**

Bug fixes:

- **Drag-and-drop** rebuilt as a real `DropZone` component on the Upload
  page with `onDragEnter` / `onDragOver` / `onDragLeave` / `onDrop`
  handlers (the previous version was just a `<label>` wrapping a hidden
  file input, which only handles click). Drop target highlights blue
  while a file is hovering and reads the dropped `FileList`.
- **Alias case-only correction**: the bug was a case-insensitive equality
  check at TWO sites — `learn_from_skill_diff` had
  `if raw.lower() == edited.lower(): continue` (and same for education).
  `_upsert_alias` had a similar guard. All three now compare
  case-sensitively, so `FastAPI → fastapi` actually records an alias.
  Added two regression tests:
  `test_learn_skill_records_case_only_correction` and
  `test_learn_skill_skips_no_op`.
- **Delete 500 after edits**: `CorrectionLog` rows have a FK to `Resume`
  with no relationship cascade, and we run SQLite with FK enforcement on,
  so deleting a Resume that had any saved correction blew up the FK
  constraint — and JD delete (which cascades to its resumes) failed for
  the same reason. Both delete handlers now explicitly clear
  `correction_log` rows for the affected resume IDs before deleting.

Per-JD custom fields:

- New `custom_field.job_description_id` column (nullable; NULL = global,
  non-null = JD-scoped). Inline SQLite migration on startup so existing
  databases pick up the column.
- `_load_custom_fields(db, jd_id=...)` returns global + JD-matched fields
  only. The pipeline (`extract` and `extract_async`) takes a `jd_id`
  parameter, threaded from the resume's `task.job_description_id`.
- New endpoints: `GET /api/jd/{id}/custom_fields`,
  `POST /api/jd/{id}/custom_fields`,
  `POST /api/jd/{id}/reextract` (202 + `{queued, task_ids}`).
  The reextract endpoint resets each resume's extraction state and
  enqueues a fresh `ResumeProcessingTask` per resume scoped to the JD.
- The legacy global `POST /api/custom_fields` still works (creates a
  field with `job_description_id=NULL`), and the `CustomFieldOut` model
  surfaces the scope so the Schema page can display where each field
  lives.
- Frontend: `api.listJDCustomFields`, `api.createJDCustomField`,
  `api.reextractJD`. JD page got a new `CustomFieldsCard` under the edit
  form (only shows when editing an existing JD): list of fields, an
  add-field row, and the "Re-run extraction on all resumes" button with
  a confirm dialog warning that recruiter edits will be overwritten.
- Three new tests in `test_custom_field_scope.py` cover:
  global field visible everywhere; JD-scoped field invisible to other
  JDs and to parse-only; loader combines global + scoped.

Eval dataset:

- Copied 8 PDFs out of `archive/data/data/` into `eval/dataset/resumes/`
  (one per category: engineering, digital-media, healthcare, teacher,
  finance, sales, designer, arts) with category-prefixed filenames.
- Added two negatives in `eval/dataset/negatives/`: `invoice.txt` and
  `recipe.txt`, with matching `is_resume: false` ground-truth JSONs.
- Hand-labelled `engineering_10030015.json` for the first PDF (companies
  are anonymized in the source, so the label only asserts experience
  count + role titles + the one explicit skill, "LabView").
- Extended `eval/harness.py`'s file filter to accept `.txt` / `.md` so
  text negatives can sit next to PDFs.
- Wrote `eval/dataset/README.md` explaining layout, how to run, and the
  deliberate trade-off of "one labelled example, the rest are smoke
  tests" (vs. labelling 200+ Kaggle PDFs by hand).

Docs:

- README: added the per-JD custom-fields + reextract endpoints to the
  API reference; updated the Schema page section to clarify the
  global-vs-JD split.
- DESIGN.md: two new sections — `Per-JD custom fields (not global)` and
  `Eval dataset (small + diverse, not exhaustive)`.
- This appendix written.

Final verification: `make test` → 32/32 passed; `make check` clean.

---

## Turn 8 — Recipe-as-resume bug, Upload-page rejection UX, ground-truth generator, QA pass

**User (paraphrase):**

1. Uploaded `recipe.txt` and the app classified it as `is_resume=true`.
   The eval JSON for a non-resume should have the same shape as a
   resume (all-null fields), with `is_resume=false` + a clear
   `validity_reason`. Also surface other edge cases.
2. Upload page should clearly say "not a resume" for rejected rows, and
   have a one-button bulk delete for all rejected uploads.
3. Eval ground truth has nothing real in it — generate labels from
   `archive/Resume/Resume.csv`.
4. Do a QA pass on the whole project (perf / code / security / edge
   cases). Skip ranking.

**Assistant (summary):**

Diagnosis of the recipe bug:

- `_apply_extraction_defaults` defaulted `is_resume` to **True** when the
  LLM returned `{}`. For inputs where the model produced no useful JSON
  (recipes, invoices, garbled text), the row was silently classified as a
  borderline-valid resume (confidence 0.5) and slipped past the validity
  gate.
- The user-message framing for known mime types ("Resume (PDF, ...)")
  asserted the file IS a resume and contradicted the system prompt's
  "MAY or MAY NOT" line, biasing the model toward `is_resume=true`.
- The unknown-mime fallback dumped the raw text with no framing at all,
  giving the model nothing to anchor on.

Fixes:

- **Pipeline defaults** now lean SAFE: when the LLM omits `is_resume`,
  `validity_confidence`, AND `validity_reason`, we set them to
  `false / 0.0 / "Model returned no usable extraction; document treated
  as not a resume."`. The plain `setdefault("is_resume", False)` is the
  new fallback for partial responses.
- **`parse_doc.py`** rewritten to use neutral framing across every mime
  type (`_neutral_framing`) — "Document uploaded by a recruiter ...
  verify against the schema and set is_resume=false if it is not." Plus
  a 50K-char cap (`MAX_TEXT_CHARS`) so pathological text inputs don't
  blow the prompt out.
- **Prompt v7** spells out the required shape for non-resumes
  explicitly (every key must be present with the empty value), gives
  examples of common non-resume inputs (recipes, invoices, source dumps,
  cover letters, JDs uploaded by mistake, blank pages, multi-person
  rosters), and tells the model to set `validity_confidence` to 0.0–0.10
  when it's certain.
- New regression test: `test_empty_llm_response_defaults_to_not_a_resume`
  confirms `complete_json` returning `{}` results in `is_resume=False`.

Upload-page rejection UX:

- "rejected document" replaced with a styled `Not a resume` badge
  (`bg-red-100 text-red-800` pill with uppercase tracking).
- New `useMemo` `rejectedCount` walks the queue + history rows and
  surfaces a button "Delete N non-resume(s)" next to the persistence
  caption when `rejectedCount > 0`.
- New backend endpoint `DELETE /api/resumes` (no body) bulk-deletes all
  `_is_rejected` rows in one trip, returning `{deleted, files_removed}`.
  Cleans `correction_log` rows first so FK enforcement doesn't reject.
- `api.deleteRejectedResumes()` wires the button.

Eval ground truth from CSV:

- Confirmed `archive/Resume/Resume.csv` only has `ID, Resume_str,
  Resume_html, Category` — no structured labels. Resumes are also fully
  anonymized (no real names / emails / URLs).
- Wrote `eval/scripts/gen_ground_truth.py` that:
  - Joins each PDF in `eval/dataset/resumes/` to the CSV by numeric ID
    (extracted from the filename).
  - Regex-extracts emails / phones / linkedin / github / website (none
    of these matched in the Kaggle subset, but the code is there for
    future non-anonymized PDFs).
  - Whole-word matches a fixed `SKILL_VOCAB` (50 common tools spanning
    SWE / design / data / office) against the resume body and writes
    those into `technical_skills`.
  - Skips `engineering_10030015.json` (hand-labelled) and the negatives.
- Re-ran the generator → 7 fresh `<stem>.json` files; finance picked up
  "Java" via the vocab match.
- `eval/dataset/README.md` updated to describe the partial / machine-
  derived ground truth.

QA pass — fixes applied:

- **Upload size + type guards.** New constants
  `MAX_UPLOAD_BYTES = 10 MB`, `ALLOWED_UPLOAD_SUFFIXES`, `_safe_suffix()`.
  Upload endpoint now rejects empty files (422), oversized files (413),
  and unsupported extensions (415), and strips path-separator characters
  out of the suffix to keep the storage path clean.
- New `test_upload_safety.py` covers all four guards plus the path-char
  scrubber.

QA pass — recorded as Known Limitations in DESIGN.md (no fix this turn):

- ID-based URLs are guessable (single-recruiter, no auth, by design).
- Tier filtering happens in Python after fetching all rows (acceptable
  to ~10K rows; would need a stored column past that).

Final verification: `make test` → 40/40 passed; `make check` clean.
