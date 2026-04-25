from app.db.models import EntityAlias
from app.learning.aliases import learn_from_education_diff, learn_from_skill_diff


def test_learn_skill_correction_creates_alias(db):
    learn_from_skill_diff(db, raw_skills=["GoLang", "reactjs"], edited_skills=["Go", "React"])
    db.commit()
    golang = db.query(EntityAlias).filter_by(alias="golang", kind="skill").one()
    assert golang.canonical == "Go"
    assert golang.source == "user_correction"


def test_learn_skill_idempotent_bumps_frequency(db):
    learn_from_skill_diff(db, ["GoLang"], ["Go"])
    learn_from_skill_diff(db, ["GoLang"], ["Go"])
    db.commit()
    row = db.query(EntityAlias).filter_by(alias="golang", kind="skill").one()
    assert row.frequency == 2


def test_learn_skill_records_case_only_correction(db):
    """Regression: 'FastAPI' → 'fastapi' used to be skipped because the
    early-return compared lowercased values. The recruiter is teaching a
    canonical form (case matters), so we MUST record it."""
    learn_from_skill_diff(db, raw_skills=["FastAPI"], edited_skills=["fastapi"])
    db.commit()
    row = db.query(EntityAlias).filter_by(alias="fastapi", kind="skill").one()
    assert row.canonical == "fastapi"
    assert row.source == "user_correction"


def test_learn_skill_skips_no_op(db):
    """Identical alias and canonical (case-sensitive) shouldn't add a row."""
    before = db.query(EntityAlias).filter_by(kind="skill").count()
    learn_from_skill_diff(db, raw_skills=["Django"], edited_skills=["Django"])
    db.commit()
    after = db.query(EntityAlias).filter_by(kind="skill").count()
    assert before == after


def test_learn_education_creates_university_alias(db):
    learn_from_education_diff(
        db,
        raw_edu=[{"degree": "BS", "institution": "UCSD"}],
        edited_edu=[
            {"degree": "BS", "institution": "University of California, San Diego"}
        ],
    )
    db.commit()
    row = db.query(EntityAlias).filter_by(alias="ucsd", kind="university").one()
    assert row.canonical == "University of California, San Diego"
