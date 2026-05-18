"""
Telegram alert sender.
Uses Bot API directly via requests — no extra dependencies needed.
"""
import logging
import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


def _fmt_price(p: float) -> str:
    """Smart price formatting based on magnitude."""
    if p >= 100:
        return f"{p:,.2f}"
    elif p >= 1:
        return f"{p:.4f}"
    elif p >= 0.01:
        return f"{p:.5f}"
    else:
        return f"{p:.8f}".rstrip("0").rstrip(".")


def _fmt_pair(symbol: str) -> str:
    """BTCUSDT -> BTC/USDT"""
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}/USDT"
    return symbol


def format_alert(s: dict) -> str:
    pair = _fmt_pair(s["symbol"])
    side = s["side"]
    trend_icon = "🟢" if side == "LONG" else "🔴"

    entry = (
        f"{_fmt_price(s['entry_low'])} – {_fmt_price(s['entry_high'])}"
        if abs(s["entry_high"] - s["entry_low"]) / s["price"] > 0.001
        else _fmt_price(s["price"])
    )

    reason = " | ".join(s["reasons"]) if s["reasons"] else "trend continuation setup"

    return (
        f"{trend_icon} *NEW SIGNAL*\n"
        f"📊 *PAIR:* `{pair}`\n"
        f"📈 *SIGNAL:* *{side}*\n"
        f"💰 *ENTRY:* `{entry}`\n"
        f"🛑 *STOP LOSS:* `{_fmt_price(s['stop_loss'])}`\n"
        f"🎯 *TP 1 (1R):* `{_fmt_price(s['tp1'])}`\n"
        f"🎯 *TP 2 (2.5R):* `{_fmt_price(s['tp2'])}`\n"
        f"📉 *RSI:* `{s['rsi']:.1f}`\n"
        f"📊 *TREND:* {s['trend']}\n"
        f"🔥 *CONFIDENCE:* `{s['confidence']}/100`\n\n"
        f"🧠 *REASON:*\n_{reason}_\n\n"
        f"⚠️ Leverage 5x–15x isolated · Risk max 2% capital"
    )


def send_alert(token: str, chat_id: str, signal: dict) -> None:
    text = format_alert(signal)
    url = f"{API_BASE}/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if not r.ok:
        log.error(f"Telegram error {r.status_code}: {r.text}")
        r.raise_for_status()


def send_summary(token: str, chat_id: str, summary: dict, alerts: list) -> None:
    """Send a brief scan summary, especially useful for 'NO TRADE' rounds."""
    if alerts:
        # Already sent individual alerts; just send a short footer
        text = (
            f"✅ Scan done · {summary['scanned']} pairs · "
            f"{summary['alerts']} alert(s) · "
            f"{summary['duration_sec']}s"
        )
    else:
        text = (
            f"⏸ *NO TRADE – WAIT FOR CLEAN SETUP*\n"
            f"_Scanned {summary['scanned']} pairs · "
            f"{summary['duration_sec']}s · "
            f"{summary['errors']} errors_"
        )

    url = f"{API_BASE}/bot{token}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_notification": True,
        },
        timeout=15,
    )
