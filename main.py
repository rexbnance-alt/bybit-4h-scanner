"""
Bybit Top-100 Futures 4H Trend Scanner.
Runs every 15 minutes via GitHub Actions; dedupes per 4H candle.
"""
import os
import sys
import time
import logging
from datetime import datetime, timezone

from bybit_client import BybitClient
from strategy import evaluate_pair
from telegram_notify import send_alert, send_summary
from state import load_state, save_state, make_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SEND_SUMMARY = os.environ.get("SEND_SUMMARY", "false").lower() == "true"
TOP_N = int(os.environ.get("TOP_N", "100"))
MIN_CONFIDENCE = int(os.environ.get("MIN_CONFIDENCE", "70"))
LTF_INTERVAL = os.environ.get("LTF_INTERVAL", "15")  # 15 or 5


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)

    start = time.time()
    log.info(f"=== Scan started at {datetime.now(timezone.utc).isoformat()} ===")
    log.info(f"Config: TOP_N={TOP_N} MIN_CONFIDENCE={MIN_CONFIDENCE} LTF={LTF_INTERVAL}m")

    state = load_state()
    client = BybitClient()

    log.info(f"Fetching top {TOP_N} pairs by volume...")
    pairs = client.get_top_pairs(n=TOP_N)
    log.info(f"Got {len(pairs)} pairs to scan")

    new_alerts = []
    duplicate_skips = 0
    weak_signals = 0
    scanned = 0
    errors = 0

    for symbol in pairs:
        try:
            klines_4h = client.get_klines(symbol, interval="240", limit=250)
            if not klines_4h or len(klines_4h) < 200:
                continue

            klines_ltf = client.get_klines(symbol, interval=LTF_INTERVAL, limit=50)
            if not klines_ltf or len(klines_ltf) < 20:
                continue

            signal = evaluate_pair(symbol, klines_4h, klines_ltf)
            scanned += 1

            if not signal:
                continue

            if signal["confidence"] < MIN_CONFIDENCE:
                weak_signals += 1
                log.info(
                    f"⚠️  {symbol}: {signal['side']} weak "
                    f"(conf={signal['confidence']}) - skipped"
                )
                continue

            # Dedup: skip if we already alerted this 4H candle for this side
            key = make_key(symbol, signal["side"], signal["candle_4h_open"])
            if key in state:
                duplicate_skips += 1
                log.info(f"🔁 {symbol}: {signal['side']} already alerted this 4H candle")
                continue

            log.info(
                f"✅ {symbol}: {signal['side']} NEW SIGNAL "
                f"(conf={signal['confidence']})"
            )
            new_alerts.append(signal)
            state[key] = time.time()

            time.sleep(0.05)

        except Exception as e:
            errors += 1
            log.exception(f"{symbol}: error - {e}")

    # Send only fresh alerts (no duplicates)
    for signal in new_alerts:
        try:
            send_alert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, signal)
            time.sleep(0.5)
        except Exception as e:
            log.exception(f"Failed to send alert for {signal['symbol']}: {e}")

    save_state(state)

    duration = time.time() - start
    summary = {
        "scanned": scanned,
        "new_alerts": len(new_alerts),
        "dedup_skips": duplicate_skips,
        "weak_skips": weak_signals,
        "errors": errors,
        "duration_sec": round(duration, 1),
    }
    log.info(f"=== Scan complete: {summary} ===")

    # Only send chat summary if SEND_SUMMARY is on AND we have alerts
    # (we don't want a "NO TRADE" ping every 15 minutes)
    if SEND_SUMMARY and new_alerts:
        try:
            send_summary(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, summary, new_alerts)
        except Exception as e:
            log.exception(f"Failed to send summary: {e}")


if __name__ == "__main__":
    main()
