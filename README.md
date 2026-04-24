# Resume ATS — CSE 190 Assignment 2

A document-scanning app for recruiters. Upload a JD, upload applicant resumes
(PDF, DOCX, or image). Claude (via TritonAI) extracts a structured JSON for
each resume; the recruiter verifies and corrects any field. Corrections feed
a learned skill-alias dictionary + recruiter-defined custom fields so future
extractions get more consistent and more tailored.

The current focus is **resume parsing quality**. JD-vs-candidate scoring still
runs end-to-end on upload, but it is intentionally not the centerpiece while
parsing is being tuned.

Full design rationale lives in [DESIGN.md](DESIGN.md).

---

## Prerequisites

- **Python 3.11+** (check: `python3 --version`)
- **Node 18+** and npm (check: `node --version`)
- **Poppler** — required only if you want scanned-PDF rasterization to work.
  On macOS: `brew install poppler`. Text-based PDFs, DOCX, and images work without it.

---

## First-time setup (once)

### 1. Install dependencies

From the repo root:

```bash
make install
```

That creates `backend/.venv`, installs the Python backend into it (editable
mode), and runs `npm install` in `frontend/`.

If you've already run `npm install` manually in `frontend/`, you can just run:

```bash
make install-backend
```

### 2. Configure your TritonAI key

```bash
cp .env.example .env
```

Then edit `.env` and fill in `TRITON_API_KEY`. The default model is
`claude-sonnet-4-5` — change `LLM_MODEL` if your TritonAI hub lists a different
id. The backend will auto-fall back to an accessible Claude model if the
configured one is denied.

### 3. Sanity-check the install

```bash
make test       # runs pytest on the backend (LLM is mocked)
make check      # imports the backend app + typechecks the frontend
```

Both should exit 0.

---

## Running the app (daily workflow)

The frontend and backend run in **two separate terminals**.

**Terminal 1 — backend:**

```bash
make backend
```

You should see `Uvicorn running on http://0.0.0.0:8000`. Leave it running.

**Terminal 2 — frontend:**

```bash
make frontend
```

You should see `Local: http://localhost:5173`. Open that URL in your browser.

> The frontend proxies `/api/*` requests to the backend on port 8000, so the
> two processes talk to each other automatically. Don't open `:8000` directly
> in the browser for testing — use `:5173`.

---

## How the parsing pipeline works

1. **Set or pick a JD** on the Job Description page. JDs are persisted; the
   page lists every saved JD with title + last-modified timestamp and lets
   you edit, activate, or delete any of them.
2. **Upload a resume** on the Upload page. You can pick which JD an upload
   should be scored against (defaults to the active JD).
3. Backend stores the file in `backend/data/uploads/`, creates a `resume`
   row + a `resume_processing_task` row, and returns **HTTP 202 Accepted**
   immediately with `{ task_id, resume_id }`.
4. Frontend polls `GET /api/resumes/tasks/{task_id}` and shows per-file
   progress (`Reading document` → `AI extracting data` → `AI scoring` →
   `Done` / `Rejected document` / `Failed`).
5. Background worker runs:
   1. Document parse (text or image parts) — `parse_doc.py`.
   2. LLM extraction with the system prompt assembled from the seed alias
      dictionary, learned aliases, and any recruiter-defined custom fields.
   3. Defensive defaults + nested-wrapper unwrap.
   4. Deterministic alias normalization (skills, institutions, degrees) and
      backwards-compat migration of older field shapes.
   5. Validity gate: if `is_resume` is false OR
      `validity_confidence < threshold (default 0.5)`, the row is marked
      **Rejected document**; otherwise scoring runs against the chosen JD.
6. Frontend lets you **Verify / edit** any resume. Saving updates the
   extracted JSON and (opt-in via checkbox) feeds skill / institution / degree
   corrections back into the alias table.

### What the LLM returns

The current extraction prompt is `extract-v6`. The schema (top-level keys
in the order the model produces them):

```jsonc
{
  "is_resume": true,                   // false for invoices, blank pages, etc.
  "validity_reason": "string",         // model writes its reasoning FIRST
  "validity_confidence": 0.0,          // 0..1, used to filter via the threshold
                                       // (not surfaced as a form field — only
                                       // visible in the raw-JSON expander)

  "contact": {
    "name": "First Last",
    "email": "email@example.com",
    "phone": "123-456-7890",
    "linkedin": "url",                 // Optional (PDF link text often hides URL)
    "github": "url",                   // Optional
    "website": "johndoe.dev"           // Optional — personal site / portfolio
                                       // (Kaggle, Behance, etc.) for non-SWE roles
  },

  "education": [                        // there might be more than one
    {
      "institution": "University Name",
      "degree": "Bachelor of Science",  // expanded from B.S. / B.A. / etc.
      "major": "Computer Science",      // separate from degree; null if absent
      "gpa": "3.6 / 4.0",               // optional, key always present
      "start_date": null,               // optional; if only one date is shown
      "end_date": "June 2026"           // it is treated as the end date
    }
  ],

  "experience": [
    {
      "company": "Company Name",
      "role": "Job Title",
      "start_date": "January 2026",     // dates normalized to "<Month> <Year>"
      "end_date": "Present",            // or year-only when no month is given
      "description_bullets": ["bullet 1", "bullet 2"]
    }
  ],

  "projects": [
    {
      "name": "Project Name",
      "description_bullets": ["bullet 1", "bullet 2"], // parse all bullets
                                                       // (not just the first)
      "tags": ["React", "Node.js"]      // renamed from "technologies"; optional
                                        // — empty list if the resume doesn't
                                        // list a stack
    }
  ],

  "technical_skills": [],               // flat, soft-skills excluded
  "awards": [],                         // optional, key always present, never invented
  "certificates": [],                   // optional, key always present, never invented

  "calculated_yoe": 0.0,                // sum of professional experience durations
                                        // ONLY (no projects / school / weighting).
                                        // Internships count at full weight.
                                        // Returned as a float (e.g. 0.8, 1.5).
  "concerns": [                         // neutral notes for the recruiter to
    "Gap of ~14 months between ..."     // follow up on during a phone screen
  ],                                    // (timeline gaps, very short tenures,
                                        // overlapping roles). Does NOT affect
                                        // the score.
  "custom": {}                          // recruiter-defined custom fields land here
}
```

### Match tiers and pipeline status

After scoring, every candidate is bucketed into a recruiter-facing tier so
the dashboard can communicate "how good a match is this?" at a glance:

| Tier      | Score range |
| --------- | ----------- |
| Excellent | 90 – 100    |
| Good      | 80 – 89     |
| Average   | 40 – 79     |
| Bad       | 0 – 39      |

Tiers are derived from `score`; they are not stored separately. Rejected
documents and resumes uploaded with no JD selected (parse-only) have a
`null` tier.

---

## Testing the extraction pipeline standalone (eval harness)

`extract()` is a pure function over inputs + DB reads. The Typer harness in
`eval/` calls it directly without booting FastAPI, satisfying the
assignment's "extraction is separately testable" requirement.

```bash
# Single resume (no ground truth — just print extraction)
make eval FILE=path/to/resume.pdf

# Single resume vs. a ground-truth JSON
make eval FILE=eval/dataset/resumes/jane.pdf TRUTH=eval/dataset/ground_truth/jane.json

# Whole dataset
make eval DATASET=eval/dataset

# A subset directory (e.g. edge cases only)
make eval DATASET=eval/dataset SUBSET=edge_cases

# Different model
make eval DATASET=eval/dataset MODEL=claude-haiku-4-5

# Ranking test against a JD-pair directory
make eval-rank JDPAIR=eval/dataset/jd_pairs/python_ml
```

Output: a summary table (name/email exact-match, YOE MAE, skills F1,
education match, Spearman rho for rankings) and per-file JSON artifacts
under `eval/out/<timestamp>/`.

---

## The pages

### Dashboard (`/`)

The recruiter's primary view. Read-only — extraction edits happen on the
Verify page, not here. The page is built around three filters and a
paginated ranking table:

- **Job description filter** — pick one JD or "All JDs". Resumes uploaded
  with no JD selected (parse-only) only show under "All JDs".
- **Match tier filter** — Excellent / Good / Average / Bad (or all).
- **Status filter** — any of the eight pipeline statuses (or all).
- **Pagination** — 50 candidates per page, "Previous 50" / "Next 50"
  buttons. Real recruiter pipelines hit thousands of applicants; the page
  refuses to render the entire dataset at once.

Each row shows rank, name, email, YOE, top skills, tier badge, score,
the pipeline-status dropdown (changes are persisted immediately), the JD
the score was computed against, and a **View Resume** link that opens the
original file in a new tab. There are no per-row edit buttons — the
dashboard is a triage view.

### Job Description (`/jd`)

Two-pane layout:

- Left: edit form (Title, Body markdown, Required skills). Save creates a
  new JD or updates the one you're editing.
- Right: scrollable list of all saved JDs with title + "Updated …" timestamp.
  Each row supports **delete** — and **deleting a JD also deletes every
  resume submitted under it** (and the underlying file on disk). The
  confirm dialog spells this out.

There is no "active JD" concept. Earlier prototypes had a single active
JD; that was removed once the dashboard learned to filter by JD.

### Upload (`/upload`)

- Pick which JD an upload should target. Leave blank to **parse only** —
  the resume is extracted but not scored. Useful when you're tuning the
  extractor and don't want noise from scoring.
- Drop in PDF / DOCX / PNG / JPG.
- Each row shows a live status (`Reading document` → `AI extracting data`
  → `Done` / `Rejected document` / `Failed`) and exposes **Verify**,
  **Delete**, and — when the status is `Failed` — a **Retry** button that
  re-queues the already-stored file through the extractor. This avoids
  asking the recruiter to re-upload the original PDF after a transient
  LLM error (rate-limit, 529 Overloaded, timeout).
- Recent saved resumes are listed below the drop zone for convenience.

### Verify (`/resumes/:id`)

- Left: source preview (PDF iframe or image), filename, file link, raw JSON
  expander, **Delete resume** action.
- Right: edit form. Each section sits in its own labeled card:
  - **Contact** – name, email, phone, linkedin, github, website/portfolio.
  - **Score against a JD** – if the resume was uploaded parse-only (no JD
    selected) or you want to score it against a different JD, pick one from
    the dropdown and hit *Score now*. Works for any non-rejected resume.
  - **Calculated YoE** – numeric input.
  - **Education** – one labeled row per field (Institution, Degree, Major,
    GPA, Start date, End date) per entry, with add/remove.
  - **Concerns** – neutral notes the LLM thinks the recruiter may want to
    ask about (timeline gaps, very short tenures, overlapping roles).
    Editable via the same `•` bullet editor. Does not affect scoring.
  - **Experience** – Company, Role, Start date, End date, plus a bullet
    editor that prefixes each row with `•` and lets you add / remove bullets
    individually.
  - **Projects** – Name, Tags, bullets (same `•` editor).
  - **Technical skills** – comma-separated input.
  - **Awards** / **Certificates** – bullet editors.
  - **Custom fields JSON** – arbitrary recruiter schema extension.
- Alias learning is **opt-in** via a checkbox at the bottom. Saving without
  it just updates the extraction; saving with it teaches the alias table
  from any skill / institution / degree corrections.

### Schema (`/schema`)

Manage the two learned dictionaries:

- **Skill aliases** — view + add + delete entries in the `entity_alias`
  table. Recruiter corrections (when alias-learning is opted in) show up
  here with `source = user_correction`.
- **Custom fields** — define optional schema extensions
  (`name`, `type`, `description`). Definitions are injected into the
  extraction prompt; values land under the `custom` object.

---

## Where data is stored (and how to inspect it)

When running with `make backend`, paths are relative to `backend/`:

- SQLite DB: `backend/data/app.db`
- Uploaded files: `backend/data/uploads/`

```bash
ls -lah backend/data/uploads
sqlite3 backend/data/app.db
# inside the shell:
SELECT id, filename, mime_type, storage_path, is_resume, validity_confidence, score
FROM resume ORDER BY id DESC LIMIT 20;

SELECT id, resume_id, status, step, error_message, updated_at
FROM resume_processing_task ORDER BY updated_at DESC LIMIT 20;

SELECT id, title, is_active, created_at, updated_at FROM job_description;
```

API endpoints worth knowing:

- `GET    /api/jd`                            — list JDs (title + timestamps)
- `GET    /api/jd/{id}`, `POST /api/jd`,
  `PUT /api/jd/{id}`, `DELETE /api/jd/{id}`   — JD CRUD; delete cascades to all resumes scored against that JD
- `GET    /api/resumes`                       — list resumes; query: `jd_id`, `status_filter`, `tier`, `limit`, `offset`. Returns `{items, total, limit, offset}`
- `GET    /api/resumes/{id}`                  — single resume + extraction
- `GET    /api/resumes/{id}/file`             — original uploaded bytes
- `DELETE /api/resumes/{id}`                  — remove DB row + file
- `POST   /api/resumes/upload`                — multipart upload, returns 202
- `POST   /api/resumes/{id}/retry`            — re-queue extraction for a failed row (re-uses the stored file, returns 202)
- `GET    /api/resumes/tasks/{task_id}`       — poll processing status
- `PUT    /api/resumes/{id}/verify`           — save edits, optional alias learning
- `POST   /api/resumes/{id}/score`            — retroactively (re)score against a chosen JD; body `{jd_id: int}`
- `PUT    /api/resumes/{id}/status`           — update pipeline status (one of `Ready`, `Recruiter-Call`, `Round 1`, `Round 2`, `Final Round`, `Rejected`, `Awaiting Acceptance`, `Accepted`)
- `GET    /api/resumes/_meta/statuses`        — list of allowed status values
- `GET    /api/aliases`, `POST`, `DELETE`     — alias CRUD
- `GET    /api/custom_fields`, `POST`, `DELETE` — custom-field CRUD
- `GET    /api/dashboard/stats`               — aggregate counts (legacy, no longer rendered on the Dashboard)

---

## Troubleshooting

- **`make: command not found`** — install Xcode command-line tools: `xcode-select --install`.
- **`python: command not found`** — the Makefile uses `python3`. Override with `make install PYTHON=/path/to/python`.
- **`externally-managed-environment` from pip** — PEP 668. `make install` builds a venv to sidestep it.
- **Uploads hang at "AI extracting data…"** — usually `TRITON_API_KEY` is missing or `LLM_MODEL` is not enabled for your team. Check the `make backend` terminal.
- **`team_model_access_denied`** — your key is valid but that model id isn't allowed. Set `LLM_MODEL` to one of your allowed `/models` ids; the backend also tries an automatic fallback.
- **Scanned PDFs come back empty** — install poppler (`brew install poppler`).
- **Frontend can't reach the backend** — make sure `make backend` is running and you're using http://localhost:**5173**, not :8000.

---