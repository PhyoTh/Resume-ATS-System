# Evaluation dataset

Small, hand-curated subset of the public Kaggle resume corpus
(<https://www.kaggle.com/datasets/hadikp/resume-data-pdf>) plus a few
hand-written negatives. The goal is to be small enough that
`make eval DATASET=eval/dataset` is a cheap LLM call (≤10 documents) but
diverse enough to cover positive AND negative cases.

## Layout

```
eval/dataset/
├── resumes/         # positive examples (real PDFs)
├── negatives/       # documents that ARE NOT resumes (.txt / .pdf / etc.)
├── ground_truth/    # *.json hand-labelled, matched to resumes/negatives by stem
└── edge_cases/      # reserved for tricky-layout examples (currently empty)
```

## Positive examples (`resumes/`)

8 PDFs, one from each of these Kaggle categories:
ENGINEERING, DIGITAL-MEDIA, HEALTHCARE, TEACHER, FINANCE, SALES, DESIGNER,
ARTS. Filenames are prefixed with the category name so the eval output is
easy to read.

These resumes are anonymized in the source dataset (no real names; companies
are written as "Company Name"). That makes them ideal for testing the
extractor's structural fields (sections, dates, skills) without leaking PII
into the eval artifacts.

## Negative examples (`negatives/`)

Two short text files representing typical mis-uploads:

- `invoice.txt` — looks like a billing document.
- `recipe.txt` — completely off-topic.

Both have ground-truth `is_resume: false`, so the validity gate is
asserted as part of the metrics.

## Ground truth (`ground_truth/`)

Only one of the eight Kaggle PDFs has a hand-labelled JSON
(`engineering_10030015.json`). The rest run as **smoke tests** — the
harness still extracts and persists the prediction, but skips per-field
metrics for them. That trade-off is deliberate: hand-labelling every
field on a 200-resume corpus would dominate the assignment timeline; the
single labelled example confirms the harness arithmetic works end-to-end.

If you add more labelled examples, drop `<resume_stem>.json` into
`ground_truth/` and only fill in the fields you want to assert against —
omitted fields are not penalized.

## Running

```bash
# Whole dataset (positives + negatives via the resumes subset, then the
# negatives subset)
make eval DATASET=eval/dataset
make eval DATASET=eval/dataset SUBSET=negatives

# Single file
make eval FILE=eval/dataset/resumes/engineering_10030015.pdf \
          TRUTH=eval/dataset/ground_truth/engineering_10030015.json
```

Output lands in `eval/out/<timestamp>/` (per-file JSON + a `summary.json`).
