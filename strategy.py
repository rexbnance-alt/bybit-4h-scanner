"""
4H trend-following strategy with 15m confirmation.
Applies the 7-condition checklist from the user's spec.
"""
import logging
from typing import List, Optional

from indicators import (
    ema, rsi, atr, avg_volume,
    recent_swing_low, recent_swing_high,
    is_bullish_engulfing, is_bearish_engulfing,
    is_bullish_rejection, is_bearish_rejection,
)

log = logging.getLogger(__name__)

# Tunables
EMA_PROXIMITY_PCT = 2.5      # "near EMA 50" = within 2.5%
SUPPORT_PROXIMITY_PCT = 3.0  # "near support/resistance" = within 3%
VOL_MULT_REQUIRED = 1.2      # confirmation candle volume > 1.2x avg
RSI_LONG_MIN, RSI_LONG_MAX = 40, 55
RSI_SHORT_MIN, RSI_SHORT_MAX = 45, 60


def evaluate_pair(symbol: str, k4h: List[dict], k15m: List[dict]) -> Optional[dict]:
    """
    Returns a signal dict if conditions met, else None.
    Confidence 0–100. Caller filters by MIN_CONFIDENCE.
    """
    closes_4h = [c["close"] for c in k4h]
    ema200_series = ema(closes_4h, 200)
    ema50_series = ema(closes_4h, 50)
    rsi_series = rsi(closes_4h, 14)

    ema200 = ema200_series[-1]
    ema50 = ema50_series[-1]
    rsi_val = rsi_series[-1]
    if ema200 is None or ema50 is None or rsi_val is None:
        return None

    price = closes_4h[-1]
    atr_4h = atr(k4h, 14)
    if atr_4h == 0:
        return None

    # Try long first, then short
    for side in ("LONG", "SHORT"):
        result = _check_side(
            side, symbol, price, ema50, ema200, rsi_val,
            k4h, k15m, atr_4h,
        )
        if result:
            return result
    return None


def _check_side(
    side: str, symbol: str, price: float,
    ema50: float, ema200: float, rsi_val: float,
    k4h: List[dict], k15m: List[dict], atr_4h: float,
) -> Optional[dict]:

    reasons = []
    confidence = 50

    if side == "LONG":
        # 1. Price above EMA 200
        if price <= ema200:
            return None
        # 2. EMA 50 above EMA 200 (golden cross alignment)
        if ema50 <= ema200:
            return None
        # 3. Price pulling back (not pumping) — current candle not a strong green
        last_4h = k4h[-1]
        body = last_4h["close"] - last_4h["open"]
        rng = last_4h["high"] - last_4h["low"]
        if rng > 0 and body > 0 and body / rng > 0.7:
            # Strong bullish candle = pumping, not pullback. Reject.
            return None
        # 4. RSI in pullback zone
        if not (RSI_LONG_MIN <= rsi_val <= RSI_LONG_MAX):
            return None
        # 5. Near EMA 50 or recent support
        dist_to_ema50_pct = abs(price - ema50) / price * 100
        swing_low = recent_swing_low(k4h, lookback=30)
        dist_to_support_pct = abs(price - swing_low) / price * 100
        near_ema50 = dist_to_ema50_pct <= EMA_PROXIMITY_PCT
        near_support = dist_to_support_pct <= SUPPORT_PROXIMITY_PCT
        if not (near_ema50 or near_support):
            return None
        # 6. Bullish confirmation candle on 15m
        bull_engulf = is_bullish_engulfing(k15m)
        bull_reject = is_bullish_rejection(k15m)
        if not (bull_engulf or bull_reject):
            return None
        # 7. Volume increase on confirmation
        avg_vol_15m = avg_volume(k15m[:-1], period=20)
        last_vol = k15m[-1]["volume"]
        if avg_vol_15m == 0 or last_vol < avg_vol_15m * VOL_MULT_REQUIRED:
            return None

        # All 7 pass — compute entry/SL/TP
        entry_low = min(price, ema50)
        entry_high = max(price, ema50) if near_ema50 else price * 1.002
        # Stop below swing low or 1.5×ATR, whichever is wider
        stop_loss = min(swing_low, price - 1.5 * atr_4h) * 0.998
        risk = price - stop_loss
        tp1 = price + risk * 1.0
        tp2 = price + risk * 2.5

        # Confidence scoring
        ema_spread = (ema50 - ema200) / ema200 * 100
        if ema_spread > 3:
            confidence += 8
            reasons.append(f"strong EMA spread ({ema_spread:.1f}%)")
        if 42 <= rsi_val <= 50:
            confidence += 8
            reasons.append(f"RSI in sweet spot ({rsi_val:.0f})")
        if last_vol >= avg_vol_15m * 1.8:
            confidence += 10
            reasons.append("strong volume spike")
        elif last_vol >= avg_vol_15m * 1.4:
            confidence += 5
        if bull_engulf:
            confidence += 8
            reasons.append("bullish engulfing on 15m")
        elif bull_reject:
            confidence += 6
            reasons.append("bullish rejection on 15m")
        if near_ema50 and near_support:
            confidence += 7
            reasons.append("confluence: EMA50 + support")
        elif near_support:
            confidence += 4
            reasons.append("at swing support")
        confidence = min(confidence, 100)

        return {
            "symbol": symbol,
            "side": "LONG",
            "price": price,
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rsi": rsi_val,
            "ema50": ema50,
            "ema200": ema200,
            "trend": "Bullish",
            "confidence": int(confidence),
            "reasons": reasons,
            "candle_4h_open": k4h[-1]["time"],
        }

    else:  # SHORT
        # 1. Price below EMA 200
        if price >= ema200:
            return None
        # 2. EMA 50 below EMA 200
        if ema50 >= ema200:
            return None
        # 3. Pulling back upward (not dumping)
        last_4h = k4h[-1]
        body = last_4h["open"] - last_4h["close"]
        rng = last_4h["high"] - last_4h["low"]
        if rng > 0 and body > 0 and body / rng > 0.7:
            return None
        # 4. RSI in retrace zone
        if not (RSI_SHORT_MIN <= rsi_val <= RSI_SHORT_MAX):
            return None
        # 5. Near EMA 50 or resistance
        dist_to_ema50_pct = abs(price - ema50) / price * 100
        swing_high = recent_swing_high(k4h, lookback=30)
        dist_to_res_pct = abs(price - swing_high) / price * 100
        near_ema50 = dist_to_ema50_pct <= EMA_PROXIMITY_PCT
        near_resistance = dist_to_res_pct <= SUPPORT_PROXIMITY_PCT
        if not (near_ema50 or near_resistance):
            return None
        # 6. Bearish confirmation candle on 15m
        bear_engulf = is_bearish_engulfing(k15m)
        bear_reject = is_bearish_rejection(k15m)
        if not (bear_engulf or bear_reject):
            return None
        # 7. Volume confirms
        avg_vol_15m = avg_volume(k15m[:-1], period=20)
        last_vol = k15m[-1]["volume"]
        if avg_vol_15m == 0 or last_vol < avg_vol_15m * VOL_MULT_REQUIRED:
            return None

        entry_low = min(price, ema50) if near_ema50 else price * 0.998
        entry_high = max(price, ema50)
        stop_loss = max(swing_high, price + 1.5 * atr_4h) * 1.002
        risk = stop_loss - price
        tp1 = price - risk * 1.0
        tp2 = price - risk * 2.5

        ema_spread = (ema200 - ema50) / ema200 * 100
        if ema_spread > 3:
            confidence += 8
            reasons.append(f"strong EMA spread ({ema_spread:.1f}%)")
        if 50 <= rsi_val <= 58:
            confidence += 8
            reasons.append(f"RSI in sweet spot ({rsi_val:.0f})")
        if last_vol >= avg_vol_15m * 1.8:
            confidence += 10
            reasons.append("strong volume on rejection")
        elif last_vol >= avg_vol_15m * 1.4:
            confidence += 5
        if bear_engulf:
            confidence += 8
            reasons.append("bearish engulfing on 15m")
        elif bear_reject:
            confidence += 6
            reasons.append("bearish rejection on 15m")
        if near_ema50 and near_resistance:
            confidence += 7
            reasons.append("confluence: EMA50 + resistance")
        elif near_resistance:
            confidence += 4
            reasons.append("at swing resistance")
        confidence = min(confidence, 100)

        return {
            "symbol": symbol,
            "side": "SHORT",
            "price": price,
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "rsi": rsi_val,
            "ema50": ema50,
            "ema200": ema200,
            "trend": "Bearish",
            "confidence": int(confidence),
            "reasons": reasons,
            "candle_4h_open": k4h[-1]["time"],
        }
