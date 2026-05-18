"""
Binance Futures USDT-M public API client.

NOTE: File is still called bybit_client.py and class is BybitClient
to keep diffs minimal — but underlying data source is now Binance Futures.
Bybit's CloudFront WAF blocks GitHub Actions IPs (and most cloud IPs),
so we use Binance Futures public API which has the same top-100 perps
with virtually identical prices (arbitrage keeps spread < 0.05%).

You can still TRADE on Bybit — only the analysis data source changed.
"""
import logging
import time
from typing import List, Optional

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://fapi.binance.com"
TIMEOUT = 15

# Map Bybit-style numeric intervals to Binance string intervals so the
# rest of the codebase (main.py, strategy.py) doesn't need changes.
INTERVAL_MAP = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
    "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
    "D": "1d", "W": "1w", "M": "1M",
}


class BybitClient:
    """Public Binance Futures client (despite the legacy name)."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "binance-4h-scanner/1.0"})

    def _get(self, path: str, params: dict):
        url = f"{BASE_URL}{path}"
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == 2:
                    raise
                log.warning(f"Retry {attempt + 1}: {e}")
                time.sleep(1)

    def get_top_pairs(self, n: int = 100) -> List[str]:
        """Top N USDT-margined perpetuals by 24h USD quote volume."""
        data = self._get("/fapi/v1/ticker/24hr", {})
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected response shape: {type(data)}")

        usdt_perps = [
            t for t in data
            if t["symbol"].endswith("USDT")
            and "_" not in t["symbol"]
            and float(t.get("quoteVolume", 0)) > 0
        ]

        usdt_perps.sort(key=lambda t: float(t["quoteVolume"]), reverse=True)
        return [t["symbol"] for t in usdt_perps[:n]]

    def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> Optional[List[dict]]:
        """
        Fetch klines from Binance Futures.
        Accepts both Bybit-style ("240", "15") and Binance-style ("4h", "15m")
        intervals via INTERVAL_MAP.
        Returns oldest-to-newest list of dicts:
            {time, open, high, low, close, volume, turnover}
        """
        binance_interval = INTERVAL_MAP.get(interval, interval)

        data = self._get(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": binance_interval,
                "limit": min(limit, 1500),
            },
        )
        if not data:
            return None

        candles = []
        for k in data:
            candles.append({
                "time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "turnover": float(k[7]),
            })
        return candles
