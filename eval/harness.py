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
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".png", ".jpg", ".jpeg"}:
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
        (out_dir / f"{path.stem}.json").write_text(json.dumps(record, indent=2))
        rows.append(record)

    _print_summary(rows)
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2))
    console.print(f"\n[green]wrote[/green] {out_dir}")


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
