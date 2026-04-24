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
