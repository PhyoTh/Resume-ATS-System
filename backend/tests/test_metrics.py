import sys
from math import isclose
from pathlib import Path

# Let the harness tests import from eval/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.metrics import email_match, name_match, skills_f1, spearman, yoe_abs_error


def test_skills_f1_perfect():
    r = skills_f1(["Python", "Django"], ["python", "django"])
    assert r.f1 == 1.0


def test_skills_f1_partial():
    r = skills_f1(["Python", "Django", "Flask"], ["Python", "Django", "FastAPI"])
    assert r.tp == 2 and r.fp == 1 and r.fn == 1
    assert 0.6 < r.f1 < 0.7


def test_email_match_case_insensitive():
    assert email_match("Jane@Example.com", "jane@example.com")
    assert not email_match(None, "jane@example.com")


def test_name_match_punctuation_insensitive():
    assert name_match("Dr. Jane Doe", "Dr Jane Doe")
    assert not name_match("Jane Doe", "John Doe")


def test_yoe_abs_error_handles_none():
    assert yoe_abs_error(None, 5) is None
    assert isclose(yoe_abs_error(3.2, 3.0), 0.2, abs_tol=1e-9)


def test_spearman_perfect_correlation():
    assert isclose(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0, abs_tol=1e-9)


def test_spearman_perfect_anticorrelation():
    assert isclose(spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0, abs_tol=1e-9)
