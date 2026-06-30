"""
Sentiment filter — macro-direction confluence layer.

This is NOT an entry signal. It is a filter that rejects technical signals
which conflict with the manually-set macro sentiment for a symbol.

Modes:
  off           — sentiment filter disabled, all signals pass
  directional   — reject signals opposing the sentiment direction
  extreme_only  — only reject when sentiment is "strong_bullish" / "strong_bearish"

Sentiment values:
  bullish, strong_bullish  → allow BUY, reject SELL
  bearish, strong_bearish  → allow SELL, reject BUY
  neutral                  → allow both
"""

from config import (
    SENTIMENT_FILTER_MODE,
    SENTIMENT_OVERRIDES,
)


_VALID_SENTIMENTS = {
    "bullish", "strong_bullish",
    "bearish", "strong_bearish",
    "neutral",
}


def _sentiment_allows_buy(sentiment: str) -> bool:
    return sentiment in ("bullish", "strong_bullish", "neutral")


def _sentiment_allows_sell(sentiment: str) -> bool:
    return sentiment in ("bearish", "strong_bearish", "neutral")


def check_sentiment_conflict(symbol: str, signal: str) -> str | None:
    """
    Return rejection reason if signal conflicts with sentiment, else None.
    """
    if SENTIMENT_FILTER_MODE == "off":
        return None

    sentiment = SENTIMENT_OVERRIDES.get(symbol, "neutral").lower().strip()
    if sentiment not in _VALID_SENTIMENTS:
        # Unknown sentiment value → log warning but don't block (fail-open)
        return None

    if sentiment == "neutral":
        return None

    if SENTIMENT_FILTER_MODE == "extreme_only":
        if sentiment not in ("strong_bullish", "strong_bearish"):
            return None

    if signal == "BUY" and not _sentiment_allows_buy(sentiment):
        return (
            f"Sentiment conflict — macro view for {symbol} is {sentiment}, "
            f"signal is {signal}"
        )

    if signal == "SELL" and not _sentiment_allows_sell(sentiment):
        return (
            f"Sentiment conflict — macro view for {symbol} is {sentiment}, "
            f"signal is {signal}"
        )

    return None
