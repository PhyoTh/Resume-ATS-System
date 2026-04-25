"""Per-JD custom field scoping for the extraction prompt loader."""
from app.db.models import CustomField, JobDescription
from app.extraction.pipeline import _load_custom_fields


def _make_jd(db, title: str) -> JobDescription:
    jd = JobDescription(title=title, body_md="...", required_skills_json=[])
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return jd


def test_global_field_visible_for_any_jd(db):
    db.add(
        CustomField(
            name="aws_certified",
            description="...",
            type="bool",
            job_description_id=None,
        )
    )
    db.commit()
    fields = _load_custom_fields(db, jd_id=None)
    assert any(f["name"] == "aws_certified" for f in fields)


def test_jd_scoped_field_only_visible_for_that_jd(db):
    jd_a = _make_jd(db, "Backend")
    jd_b = _make_jd(db, "Frontend")
    db.add(
        CustomField(
            name="kafka_experience",
            description="...",
            type="bool",
            job_description_id=jd_a.id,
        )
    )
    db.commit()

    a = _load_custom_fields(db, jd_id=jd_a.id)
    b = _load_custom_fields(db, jd_id=jd_b.id)
    none = _load_custom_fields(db, jd_id=None)

    assert any(f["name"] == "kafka_experience" for f in a)
    assert not any(f["name"] == "kafka_experience" for f in b)
    # Parse-only path (no JD) should not see JD-scoped fields either.
    assert not any(f["name"] == "kafka_experience" for f in none)


def test_loader_combines_global_and_jd_scoped(db):
    jd = _make_jd(db, "Data")
    db.add(
        CustomField(
            name="aws_certified",
            description="...",
            type="bool",
            job_description_id=None,
        )
    )
    db.add(
        CustomField(
            name="dbt_experience",
            description="...",
            type="bool",
            job_description_id=jd.id,
        )
    )
    db.commit()
    fields = _load_custom_fields(db, jd_id=jd.id)
    names = {f["name"] for f in fields}
    assert {"aws_certified", "dbt_experience"} <= names
