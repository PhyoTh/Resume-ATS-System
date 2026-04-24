from app.scoring.rank import match_tier_for_score


def test_excellent_at_or_above_90():
    assert match_tier_for_score(90.0) == "Excellent"
    assert match_tier_for_score(99.5) == "Excellent"


def test_good_band():
    assert match_tier_for_score(89.9) == "Good"
    assert match_tier_for_score(80) == "Good"


def test_average_band():
    assert match_tier_for_score(79) == "Average"
    assert match_tier_for_score(40) == "Average"


def test_bad_below_40():
    assert match_tier_for_score(39.9) == "Bad"
    assert match_tier_for_score(0) == "Bad"


def test_none_score_returns_none():
    assert match_tier_for_score(None) is None
