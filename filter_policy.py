def rsi_exhausted(signal: str, rsi: float, buy_max: float = 78.0, sell_min: float = 22.0):
    if signal == "BUY" and rsi > buy_max:
        return f"RSI exhaustion — RSI {rsi} above {buy_max} on BUY"
    if signal == "SELL" and rsi < sell_min:
        return f"RSI exhaustion — RSI {rsi} below {sell_min} on SELL"
    return None


def volume_below_threshold(volume: float, volume_avg20: float, min_ratio: float = 0.85) -> bool:
    if volume_avg20 <= 0:
        return False
    return (volume / volume_avg20) < min_ratio


def ema_overextended(signal: str, price: float, ema200: float, max_distance_pct: float = 5.0):
    if ema200 is None or ema200 == 0:
        return None
    distance_pct = ((price - ema200) / ema200) * 100
    if abs(distance_pct) > max_distance_pct:
        side = "above" if distance_pct > 0 else "below"
        return (
            f"EMA overextension — price {round(abs(distance_pct), 2)}% {side} EMA200 "
            f"(limit {max_distance_pct}%) on {signal}"
        )
    return None


def ema_pullback_invalid(signal: str, price: float, ema200: float, max_distance_pct: float = 3.0):
    """Pullback validation: entry must be NEAR EMA200 (within 3%).
    
    For pullback strategy, price should have retraced to the EMA. If entry is
    too far from EMA200, it's not a genuine pullback — it's a breakout or chase.
    """
    if ema200 is None or ema200 == 0:
        return None
    distance_pct = ((price - ema200) / ema200) * 100
    if abs(distance_pct) > max_distance_pct:
        side = "above" if distance_pct > 0 else "below"
        return (
            f"Pullback invalid — price {round(abs(distance_pct), 2)}% {side} EMA200 "
            f"(max {max_distance_pct}% for pullback entry) on {signal}"
        )
    return None
