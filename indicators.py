"""
Technical indicators. Pure-Python implementations — no pandas/numpy needed
to keep the GitHub Actions install small and fast.
"""
from typing import List, Optional


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Exponential Moving Average. Returns list aligned with input length."""
    if len(values) < period:
        return [None] * len(values)

    k = 2 / (period + 1)
    result: List[Optional[float]] = [None] * (period - 1)
    # Seed with SMA of the first `period` values
    sma = sum(values[:period]) / period
    result.append(sma)
    prev = sma
    for v in values[period:]:
        cur = (v - prev) * k + prev
        result.append(cur)
        prev = cur
    return result


def rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder's RSI. Returns list aligned with input length."""
    if len(closes) < period + 1:
        return [None] * len(closes)

    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    # Wilder's smoothing
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result: List[Optional[float]] = [None] * period
    rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
    result.append(100 - (100 / (1 + rs)))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
        result.append(100 - (100 / (1 + rs)))

    return result


def recent_swing_low(candles: List[dict], lookback: int = 30) -> float:
    """Lowest low in the last `lookback` candles (excluding current)."""
    window = candles[-lookback - 1:-1]
    return min(c["low"] for c in window) if window else candles[-1]["low"]


def recent_swing_high(candles: List[dict], lookback: int = 30) -> float:
    """Highest high in the last `lookback` candles (excluding current)."""
    window = candles[-lookback - 1:-1]
    return max(c["high"] for c in window) if window else candles[-1]["high"]


def avg_volume(candles: List[dict], period: int = 20) -> float:
    """Average volume over last `period` candles."""
    window = candles[-period:]
    return sum(c["volume"] for c in window) / len(window) if window else 0


def atr(candles: List[dict], period: int = 14) -> float:
    """Average True Range — simple version."""
    if len(candles) < period + 1:
        return 0
    trs = []
    for i in range(-period, 0):
        c = candles[i]
        prev_close = candles[i - 1]["close"]
        tr = max(
            c["high"] - c["low"],
            abs(c["high"] - prev_close),
            abs(c["low"] - prev_close),
        )
        trs.append(tr)
    return sum(trs) / len(trs)


def is_bullish_engulfing(candles: List[dict]) -> bool:
    """Last candle bullishly engulfs previous bearish candle."""
    if len(candles) < 2:
        return False
    prev, cur = candles[-2], candles[-1]
    return (
        prev["close"] < prev["open"]            # prev bearish
        and cur["close"] > cur["open"]          # cur bullish
        and cur["close"] >= prev["open"]        # engulfs body
        and cur["open"] <= prev["close"]
    )


def is_bearish_engulfing(candles: List[dict]) -> bool:
    """Last candle bearishly engulfs previous bullish candle."""
    if len(candles) < 2:
        return False
    prev, cur = candles[-2], candles[-1]
    return (
        prev["close"] > prev["open"]
        and cur["close"] < cur["open"]
        and cur["close"] <= prev["open"]
        and cur["open"] >= prev["close"]
    )


def is_bullish_rejection(candles: List[dict]) -> bool:
    """Strong bullish close with long lower wick (hammer-like)."""
    c = candles[-1]
    body = abs(c["close"] - c["open"])
    rng = c["high"] - c["low"]
    if rng == 0:
        return False
    lower_wick = min(c["open"], c["close"]) - c["low"]
    return (
        c["close"] > c["open"]
        and lower_wick > body * 1.5
        and body / rng > 0.2
    )


def is_bearish_rejection(candles: List[dict]) -> bool:
    """Strong bearish close with long upper wick (shooting-star-like)."""
    c = candles[-1]
    body = abs(c["close"] - c["open"])
    rng = c["high"] - c["low"]
    if rng == 0:
        return False
    upper_wick = c["high"] - max(c["open"], c["close"])
    return (
        c["close"] < c["open"]
        and upper_wick > body * 1.5
        and body / rng > 0.2
    )
