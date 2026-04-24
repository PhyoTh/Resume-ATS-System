"""Pipeline test with the LLM mocked — proves extract() is pure over DB + inputs."""
from unittest.mock import patch

from app.extraction import pipeline as pipeline_mod


FAKE_LLM_RESPONSE = {
    "is_resume": True,
    "validity_confidence": 0.9,
    "validity_reason": "Standard resume structure with contact, education, and experience.",
    "contact": {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-1212",
        "linkedin": None,
        "github": None,
        "website": None,
    },
    "education": [
        {
            "institution": "UCSD",
            "degree": "Bachelor of Science",
            "major": "Computer Science",
            "gpa": "3.6",
            "start_date": None,
            "end_date": "June 2021",
        }
    ],
    "experience": [
        {
            "company": "Acme",
            "role": "Engineer",
            "start_date": "January 2022",
            "end_date": "Present",
            "description_bullets": ["Built things"],
        }
    ],
    "projects": [],
    "technical_skills": ["js", "python3", "Django"],
    "awards": [],
    "certificates": [],
    "calculated_yoe": 3.5,
    "concerns": [],
    "custom": {},
}


def test_pipeline_runs_normalization_over_llm_output(db, tmp_path):
    resume = tmp_path / "fake.txt"
    resume.write_text("dummy")

    with patch.object(pipeline_mod, "complete_json", return_value=dict(FAKE_LLM_RESPONSE)):
        result = pipeline_mod.extract(resume, db)

    # raw preserves model output
    assert result.raw["technical_skills"] == ["js", "python3", "Django"]
    # normalized uses seeded aliases
    assert "JavaScript" in result.normalized["technical_skills"]
    assert "Python" in result.normalized["technical_skills"]
    assert "Django" in result.normalized["technical_skills"]
    assert result.prompt_version == "extract-v6"


def test_pipeline_unwraps_curly_brace_wrapper(db, tmp_path):
    """The model has been observed to nest the real result under a "{}" key
    and emit empty defaults at the top. Pipeline should recover the inner
    object rather than serving the empty defaults.
    """
    resume = tmp_path / "fake.txt"
    resume.write_text("dummy")

    wrapped = {
        "{}": dict(FAKE_LLM_RESPONSE),
        "is_resume": True,
        "validity_confidence": 0.5,
        "validity_reason": "",
        "contact": {
            "name": None,
            "email": None,
            "phone": None,
            "linkedin": None,
            "github": None,
        },
        "education": [],
        "experience": [],
        "projects": [],
        "technical_skills": [],
        "awards": [],
        "certificates": [],
        "calculated_yoe": None,
        "custom": {},
    }

    with patch.object(pipeline_mod, "complete_json", return_value=wrapped):
        result = pipeline_mod.extract(resume, db)

    assert result.raw["contact"]["name"] == "Jane Doe"
    assert len(result.raw["education"]) == 1
    assert len(result.raw["experience"]) == 1


def test_pipeline_fills_missing_keys(db, tmp_path):
    resume = tmp_path / "fake.txt"
    resume.write_text("dummy")

    minimal = {"is_resume": False, "validity_confidence": 0.1}
    with patch.object(pipeline_mod, "complete_json", return_value=dict(minimal)):
        result = pipeline_mod.extract(resume, db)

    # All schema keys must exist with sane defaults.
    assert result.raw["contact"] == {
        "name": None,
        "email": None,
        "phone": None,
        "linkedin": None,
        "github": None,
        "website": None,
    }
    assert result.raw["education"] == []
    assert result.raw["experience"] == []
    assert result.raw["projects"] == []
    assert result.raw["technical_skills"] == []
    assert result.raw["awards"] == []
    assert result.raw["certificates"] == []
    assert result.raw["calculated_yoe"] is None
    assert result.raw["concerns"] == []
    assert result.raw["custom"] == {}
