# Ground-truth labels

Each `<resume_stem>.json` here matches a file under
`../resumes/<resume_stem>.<ext>` (or any `--subset`). The harness loads it
when computing per-field metrics (name/email exact-match, YOE MAE, skills
F1, education match).

For files in `../resumes/` that have no matching ground-truth JSON, the
harness still runs extraction and writes the prediction to
`eval/out/<run>/<stem>.json`, but no metrics are computed for them — they
serve as "smoke tests" that the pipeline doesn't crash and the validity
gate passes.

For negatives (`../negatives/`), set `is_resume: false` so the harness
checks the validity gate did its job.

Schema: same as the live extraction (`extract-v6`). Only fill in the
fields you actually want to assert against — anything you leave out is
ignored by the metric (it isn't a partial-credit penalty).
