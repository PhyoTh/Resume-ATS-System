"""Typer-based eval harness for extraction + ranking.

Examples:
    # single file, prints diff against a ground-truth JSON
    python -m eval.harness run --file eval/dataset/resumes/jane.pdf \
        --truth eval/dataset/ground_truth/jane.json

    # full dataset
    python -m eval.harness run --dataset eval/dataset

    # subset by directory name
    python -m eval.harness run --dataset eval/dataset --subset edge_cases

    # pick a different model (TritonAI model id)
    python -m eval.harness run --dataset eval/dataset --model claude-haiku-4-5

    # ranking: pass a directory with jd.md + resumes/ + expected_ranking.json
    python -m eval.harness rank --jd-pair eval/dataset/jd_pairs/python_ml
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Allow running as `python -m eval.harness` from repo root by adding backend/
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "backend"))

from app.db.models import Base  # noqa: E402
from app.db.seed import seed_aliases  # noqa: E402
from app.extraction.pipeline import extract  # noqa: E402
from app.scoring.rank import score_candidate  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from eval.metrics import (  # noqa: E402
    education_match,
    email_match,
    name_match,
    skills_f1,
    spearman,
    yoe_abs_error,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _make_session() -> Session:
    """In-memory SQLite for evals — same code path, zero persistence."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionFactory()
    seed_aliases(db)
    return db


def _resolve_truth_path(resume_path: Path, dataset_root: Path | None) -> Path | None:
    if dataset_root is None:
        return None
    gt = dataset_root / "ground_truth" / (resume_path.stem + ".json")
    return gt if gt.exists() else None


def _score_one(pred: dict, truth: dict) -> dict:
    pred_contact = pred.get("contact") or {}
    truth_contact = truth.get("contact") or {}
    return {
        "is_resume_correct": pred.get("is_resume") == truth.get("is_resume", True),
        "name": name_match(pred_contact.get("name"), truth_contact.get("name")),
        "email": email_match(pred_contact.get("email"), truth_contact.get("email")),
        "yoe_abs_err": yoe_abs_error(
            pred.get("calculated_yoe"), truth.get("calculated_yoe")
        ),
        "skills_f1": skills_f1(
            pred.get("technical_skills", []), truth.get("technical_skills", [])
        ).f1,
        "education_match": education_match(
            pred.get("education", []), truth.get("education", [])
        ),
    }


@app.command()
def run(
    file: Path | None = typer.Option(None, "--file", help="Single resume to extract."),
    truth: Path | None = typer.Option(None, "--truth", help="Ground truth JSON for --file."),
    dataset: Path | None = typer.Option(None, "--dataset", help="Dataset root with resumes/ + ground_truth/."),
    subset: str | None = typer.Option(None, "--subset", help="Subdirectory name to restrict to (e.g. edge_cases)."),
    model: str | None = typer.Option(None, "--model", help="TritonAI model id override."),
    out: Path = typer.Option(Path("eval/out"), "--out", help="Output directory for run artifacts."),
):
    """Run extraction on a single file or a whole dataset and summarize metrics."""
    db = _make_session()

    items: list[tuple[Path, Path | None]] = []
    if file is not None:
        items.append((file, truth))
    elif dataset is not None:
        root = dataset / subset if subset else dataset / "resumes"
        if not root.exists():
            console.print(f"[red]no such directory: {root}[/red]")
            raise typer.Exit(2)
        # `.txt` and `.md` are accepted so negative examples (invoices,
        # recipes, blank docs) can live alongside real resumes without
        # tripping the filter.
        accepted = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt", ".md"}
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() in accepted:
                items.append((p, _resolve_truth_path(p, dataset)))
    else:
        console.print("[red]must pass --file or --dataset[/red]")
        raise typer.Exit(2)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for path, truth_path in items:
        console.print(f"[cyan]extracting[/cyan] {path.name}")
        try:
            result = extract(path, db, model=model)
        except Exception as e:
            console.print(f"  [red]FAIL[/red]: {e}")
            rows.append({"file": path.name, "error": str(e)})
            continue
        record = {
            "file": path.name,
            "prediction": result.normalized,
        }
        if truth_path and truth_path.exists():
            truth = json.loads(truth_path.read_text())
            record["truth"] = truth
            record["metrics"] = _score_one(result.normalized, truth)
            _print_field_diff(path.name, result.normalized, truth)
            _print_per_file_metrics(record["metrics"])
        (out_dir / f"{path.stem}.json").write_text(json.dumps(record, indent=2))
        rows.append(record)

    _print_summary(rows)
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2))
    console.print(f"\n[green]wrote[/green] {out_dir}")


def _norm(value):
    """Loose comparator: trim whitespace, ignore case, collapse `None`/`""`/`[]`/`{}`."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip().lower()
        return s or None
    if isinstance(value, (list, dict)) and not value:
        return None
    if isinstance(value, float):
        return round(value, 2)
    return value


def _eq(a, b) -> bool:
    return _norm(a) == _norm(b)


def _fmt(value, width: int = 60) -> str:
    if value is None:
        return "[dim]∅[/dim]"
    if isinstance(value, list):
        return f"[{len(value)} item(s)]"
    s = str(value).replace("\n", " ⏎ ")
    if len(s) > width:
        s = s[: width - 1] + "…"
    return s


def _list_diff_summary(truth_list: list, pred_list: list) -> tuple[str, str]:
    """For lists of strings: return (truth_cell, pred_cell) for a Rich table.

    `pred_cell` calls out what pred is *missing* (in truth, not in pred)
    and what pred has *extra* (in pred, not in truth) so the recruiter
    can see at a glance where the LLM disagrees with the labels.
    """
    t = {_norm(x) for x in (truth_list or []) if isinstance(x, (str, int, float))}
    p = {_norm(x) for x in (pred_list or []) if isinstance(x, (str, int, float))}
    t.discard(None)
    p.discard(None)
    pred_missing = sorted(str(x) for x in (t - p))
    pred_extra = sorted(str(x) for x in (p - t))
    truth_cell = f"{len(t)} item(s)"
    parts = [f"{len(p)} item(s)"]
    if pred_missing:
        parts.append(f"missing {len(pred_missing)}: {pred_missing[:3]}")
    if pred_extra:
        parts.append(f"extra {len(pred_extra)}: {pred_extra[:3]}")
    return truth_cell, "; ".join(parts)


def _print_field_diff(filename: str, pred: dict, truth: dict) -> None:
    """Per-file table comparing every field present in the truth JSON.

    The truth JSON may omit fields (e.g. `concerns`, `validity_reason`) —
    we only diff what's actually labelled. ✓ = exact match, ✗ = mismatch.
    """
    rows: list[tuple[str, str, str, str]] = []  # (status, field, truth, pred)

    def add_scalar(label: str, t_val, p_val):
        ok = _eq(t_val, p_val)
        rows.append(
            ("[green]✓[/green]" if ok else "[red]✗[/red]", label, _fmt(t_val), _fmt(p_val))
        )

    def add_list_summary(label: str, t_list, p_list):
        ok = (
            isinstance(t_list, list)
            and isinstance(p_list, list)
            and {_norm(x) for x in t_list} == {_norm(x) for x in p_list}
        )
        t_str, p_str = _list_diff_summary(t_list or [], p_list or [])
        rows.append(
            (
                "[green]✓[/green]" if ok else "[yellow]≈[/yellow]",
                label,
                t_str,
                p_str,
            )
        )

    def add_list_of_dicts(label: str, t_list, p_list, key_fields):
        """One row per labelled entry; compare position-aligned only."""
        t_list = t_list or []
        p_list = p_list or []
        n = max(len(t_list), len(p_list))
        if n == 0:
            return
        rows.append(
            (
                "[green]✓[/green]" if len(t_list) == len(p_list) else "[red]✗[/red]",
                f"{label} (count)",
                str(len(t_list)),
                str(len(p_list)),
            )
        )
        for i in range(n):
            t_entry = t_list[i] if i < len(t_list) else {}
            p_entry = p_list[i] if i < len(p_list) else {}
            for k in key_fields:
                t_val = (t_entry or {}).get(k)
                p_val = (p_entry or {}).get(k)
                if t_val is None and p_val is None:
                    continue  # both empty → not labelled, skip
                add_scalar(f"  {label}[{i}].{k}", t_val, p_val)

    if "is_resume" in truth:
        add_scalar("is_resume", truth.get("is_resume"), pred.get("is_resume"))

    if "contact" in truth:
        t_c = truth.get("contact") or {}
        p_c = pred.get("contact") or {}
        for k in ("name", "email", "phone", "linkedin", "github", "website"):
            if k in t_c:  # truth opted-in to label this contact subfield
                add_scalar(f"contact.{k}", t_c.get(k), p_c.get(k))

    if "education" in truth:
        add_list_of_dicts(
            "education",
            truth.get("education"),
            pred.get("education"),
            ("institution", "degree", "major", "gpa", "start_date", "end_date"),
        )

    if "experience" in truth:
        add_list_of_dicts(
            "experience",
            truth.get("experience"),
            pred.get("experience"),
            ("company", "role", "start_date", "end_date"),
        )
        # bullets: count match + extra/missing summary, not per-bullet diff
        for i, t_entry in enumerate(truth.get("experience") or []):
            t_bullets = (t_entry or {}).get("description_bullets") or []
            p_entry = (pred.get("experience") or [{}])[i] if i < len(pred.get("experience") or []) else {}
            p_bullets = (p_entry or {}).get("description_bullets") or []
            if t_bullets or p_bullets:
                add_list_summary(
                    f"  experience[{i}].bullets",
                    t_bullets,
                    p_bullets,
                )

    if "projects" in truth:
        add_list_of_dicts(
            "projects",
            truth.get("projects"),
            pred.get("projects"),
            ("name",),
        )

    if "technical_skills" in truth:
        add_list_summary(
            "technical_skills",
            truth.get("technical_skills"),
            pred.get("technical_skills"),
        )

    if "awards" in truth:
        add_list_summary("awards", truth.get("awards"), pred.get("awards"))
    if "certificates" in truth:
        add_list_summary(
            "certificates",
            truth.get("certificates"),
            pred.get("certificates"),
        )

    if "calculated_yoe" in truth:
        add_scalar(
            "calculated_yoe",
            truth.get("calculated_yoe"),
            pred.get("calculated_yoe"),
        )

    t = Table(title=f"Field-by-field diff — {filename}")
    t.add_column("✓"); t.add_column("field"); t.add_column("truth"); t.add_column("prediction")
    for status, field, t_val, p_val in rows:
        t.add_row(status, field, t_val, p_val)
    console.print(t)


def _print_per_file_metrics(m: dict) -> None:
    """Compact one-table summary of the pre-computed numeric metrics."""
    t = Table(title="Metrics")
    t.add_column("metric"); t.add_column("value", justify="right")
    t.add_row("is_resume_correct", "✓" if m.get("is_resume_correct") else "✗")
    t.add_row("name (exact)", "✓" if m.get("name") else "✗")
    t.add_row("email (exact)", "✓" if m.get("email") else "✗")
    yoe = m.get("yoe_abs_err")
    t.add_row("YOE abs error", f"{yoe:.2f}" if yoe is not None else "n/a")
    t.add_row("skills F1", f"{m.get('skills_f1', 0):.2f}")
    t.add_row("education match", f"{m.get('education_match', 0):.2f}")
    console.print(t)


def _print_summary(rows: list[dict]) -> None:
    scored = [r for r in rows if "metrics" in r]
    if not scored:
        console.print("[yellow]no ground-truth comparisons[/yellow]")
        return

    n = len(scored)
    name_em = sum(1 for r in scored if r["metrics"]["name"]) / n
    email_em = sum(1 for r in scored if r["metrics"]["email"]) / n
    is_resume_acc = sum(1 for r in scored if r["metrics"]["is_resume_correct"]) / n
    yoe_errors = [r["metrics"]["yoe_abs_err"] for r in scored if r["metrics"]["yoe_abs_err"] is not None]
    yoe_mae = sum(yoe_errors) / len(yoe_errors) if yoe_errors else None
    skills_mean = sum(r["metrics"]["skills_f1"] for r in scored) / n
    edu_mean = sum(r["metrics"]["education_match"] for r in scored) / n

    t = Table(title=f"Extraction metrics (n={n})")
    t.add_column("metric"); t.add_column("value", justify="right")
    t.add_row("is_resume accuracy", f"{is_resume_acc:.2f}")
    t.add_row("name EM", f"{name_em:.2f}")
    t.add_row("email EM", f"{email_em:.2f}")
    t.add_row("YOE MAE", f"{yoe_mae:.2f}" if yoe_mae is not None else "n/a")
    t.add_row("skills F1", f"{skills_mean:.2f}")
    t.add_row("education match", f"{edu_mean:.2f}")
    console.print(t)


@app.command()
def rank(
    jd_pair: Path = typer.Option(..., "--jd-pair", help="Directory with jd.md, resumes/, expected_ranking.json."),
    model: str | None = typer.Option(None, "--model"),
):
    """Score resumes against a JD and compare to expected ranking."""
    db = _make_session()
    jd_md = (jd_pair / "jd.md").read_text()
    required = json.loads((jd_pair / "required_skills.json").read_text()) if (jd_pair / "required_skills.json").exists() else []
    expected_order: list[str] = json.loads((jd_pair / "expected_ranking.json").read_text())

    resumes_dir = jd_pair / "resumes"
    scored: dict[str, float] = {}
    for p in sorted(resumes_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in {".pdf", ".docx", ".png", ".jpg", ".jpeg"}:
            continue
        console.print(f"[cyan]extract+score[/cyan] {p.name}")
        ex = extract(p, db, model=model)
        s = score_candidate(jd_md, required, ex.normalized, model=model)
        scored[p.stem] = s.score

    predicted_order = [name for name, _ in sorted(scored.items(), key=lambda x: -x[1])]
    xs = [scored.get(name, 0.0) for name in expected_order]
    ys = [-i for i in range(len(expected_order))]  # expected: first is best
    rho = spearman(xs, ys)

    t = Table(title=f"Ranking — {jd_pair.name}")
    t.add_column("rank"); t.add_column("predicted"); t.add_column("expected"); t.add_column("score", justify="right")
    for i in range(max(len(predicted_order), len(expected_order))):
        pred = predicted_order[i] if i < len(predicted_order) else ""
        exp = expected_order[i] if i < len(expected_order) else ""
        sc = f"{scored.get(pred, 0):.1f}" if pred else ""
        t.add_row(str(i + 1), pred, exp, sc)
    console.print(t)
    console.print(f"\n[bold]Spearman rho[/bold] = {rho:.3f}")


if __name__ == "__main__":
    app()
