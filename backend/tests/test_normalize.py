from app.extraction.normalize import normalize_extraction


def test_normalize_skills_uses_seed_aliases(db):
    ex = {
        "technical_skills": ["js", "PY", "React.js", "CustomThing"],
        "education": [],
    }
    out = normalize_extraction(ex, db)
    assert "JavaScript" in out["technical_skills"]
    assert "Python" in out["technical_skills"]
    assert "React" in out["technical_skills"]
    assert "CustomThing" in out["technical_skills"]


def test_normalize_dedupes_after_canonicalization(db):
    ex = {
        "technical_skills": ["js", "javascript", "JavaScript"],
        "education": [],
    }
    out = normalize_extraction(ex, db)
    assert out["technical_skills"] == ["JavaScript"]


def test_normalize_project_tags_new_shape(db):
    ex = {
        "projects": [
            {
                "name": "p",
                "description_bullets": ["did a thing"],
                "tags": ["js", "PY"],
            }
        ],
        "education": [],
    }
    out = normalize_extraction(ex, db)
    assert out["projects"][0]["tags"] == ["JavaScript", "Python"]
    assert out["projects"][0]["description_bullets"] == ["did a thing"]


def test_normalize_migrates_legacy_education_date(db):
    ex = {
        "education": [
            {
                "institution": "UCSD",
                "degree": "BS",
                "graduation_date": "Jun 2026",
            }
        ],
        "projects": [],
    }
    out = normalize_extraction(ex, db)
    edu = out["education"][0]
    assert edu["start_date"] is None
    assert edu["end_date"] == "Jun 2026"
    assert "graduation_date" not in edu
    # Defaults should be filled in for the new keys.
    assert edu["major"] is None
    assert edu["gpa"] is None


def test_normalize_splits_legacy_experience_dates(db):
    ex = {
        "education": [],
        "experience": [
            {
                "company": "Acme",
                "role": "Engineer",
                "dates": "Jan 2024 - Present",
                "description_bullets": ["did stuff"],
            }
        ],
    }
    out = normalize_extraction(ex, db)
    exp = out["experience"][0]
    assert exp["start_date"] == "Jan 2024"
    assert exp["end_date"] == "Present"
    assert "dates" not in exp


def test_normalize_project_migrates_legacy_shape(db):
    ex = {
        "projects": [
            {
                "name": "p",
                "description": "did a thing",
                "technologies": ["js"],
            }
        ],
        "education": [],
    }
    out = normalize_extraction(ex, db)
    proj = out["projects"][0]
    assert proj["tags"] == ["JavaScript"]
    assert proj["description_bullets"] == ["did a thing"]
    assert "technologies" not in proj
    assert "description" not in proj
