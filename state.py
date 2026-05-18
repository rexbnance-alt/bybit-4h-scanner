"""
Persistent state for alert deduplication.
Keeps a small JSON file mapping {symbol_side_4hCandleOpenMs} -> timestamp.

Cached across GitHub Actions runs via actions/cache.
This prevents re-alerting the same setup every 15 minutes while
the 4H conditions remain true. New 4H candle = fresh alerting window.
"""
import json
import logging
import os
import time

log = logging.getLogger(__name__)

STATE_FILE = os.environ.get("STATE_FILE", "state.json")
TTL_SECONDS = 12 * 3600  # prune entries older than 12 hours


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        log.info(f"No existing state file at {STATE_FILE}, starting fresh")
        return {}
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        now = time.time()
        pruned = {k: v for k, v in data.items() if now - v < TTL_SECONDS}
        log.info(f"Loaded state: {len(pruned)} active entries (pruned {len(data) - len(pruned)})")
        return pruned
    except Exception as e:
        log.warning(f"Failed to load state: {e}, starting fresh")
        return {}


def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        log.info(f"Saved state: {len(state)} entries to {STATE_FILE}")
    except Exception as e:
        log.error(f"Failed to save state: {e}")


def make_key(symbol: str, side: str, candle_4h_open_ms: int) -> str:
    return f"{symbol}_{side}_{candle_4h_open_ms}"
