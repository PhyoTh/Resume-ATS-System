from app.scoring import rank as rank_mod


def _sample_extraction() -> dict:
    return {
        "technical_skills": ["Python", "SQL", "FastAPI"],
        "projects": [{"tags": ["Docker"]}],
        "calculated_yoe": 2.5,
        "education": [{"degree": "Bachelor of Science"}],
    }


def test_score_candidate_falls_back_when_llm_raises(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(rank_mod, "complete_json", _boom)

    result = rank_mod.score_candidate(
        "We need 2+ years of experience and strong Python + SQL skills.",
        ["Python", "SQL", "AWS"],
        _sample_extraction(),
    )

    assert result.score is not None
    assert 0 <= result.score <= 100
    assert set(result.subscores.keys()) == {
        "skills", "experience", "education"}
    assert "Deterministic fallback" in result.rationale


def test_score_candidate_falls_back_when_llm_score_missing(monkeypatch):
    monkeypatch.setattr(
        rank_mod,
        "complete_json",
        lambda *_args, **_kwargs: {
            "subscores": {"skills": 99},
            "rationale": "missing score field",
        },
    )

    result = rank_mod.score_candidate(
        "Need 3-5 years and React.",
        ["React", "TypeScript"],
        _sample_extraction(),
    )

    assert result.score is not None
    assert "Deterministic fallback" in result.rationale


def test_score_candidate_parses_string_score(monkeypatch):
    monkeypatch.setattr(
        rank_mod,
        "complete_json",
        lambda *_args, **_kwargs: {
            "score": "87/100",
            "subscores": {"skills": 80},
            "rationale": "LLM output",
        },
    )

    result = rank_mod.score_candidate(
        "Need backend engineer.",
        ["Python"],
        _sample_extraction(),
    )

    assert result.score == 87.0
    assert result.rationale == "LLM output"
