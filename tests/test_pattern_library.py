from intelligence.pattern_library import PATTERN_CHEATSHEET, find_matching_patterns


def test_bullish_reversal_match() -> None:
    state = {
        "rsi": 30.0,
        "ema_ratio": 1.0,
        "volume_change": 0.2,
        "price_change": -0.002,
    }
    matches = find_matching_patterns(state)
    names = [pattern.name for pattern in matches]
    assert "bullish_reversal" in names


def test_no_match_outside_ranges() -> None:
    state = {
        "rsi": 80.0,
        "ema_ratio": 1.2,
        "volume_change": -0.1,
        "price_change": 0.05,
    }
    matches = find_matching_patterns(state)
    assert matches == []


def test_sorted_by_win_rate() -> None:
    state = {
        "rsi": 60.0,
        "ema_ratio": 1.01,
        "volume_change": 0.25,
        "price_change": 0.005,
    }
    matches = find_matching_patterns(state)
    assert matches
    win_rates = [pattern.historical_win_rate for pattern in matches]
    assert win_rates == sorted(win_rates, reverse=True)
