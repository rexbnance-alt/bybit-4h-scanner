"""
Bybit V5 public API client.
No auth needed for market data.
"""
import logging
import time
from typing import List, Optional

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.bybit.com"
TIMEOUT = 15


class BybitClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "bybit-4h-scanner/1.0"})

    def _get(self, path: str, params: dict) -> dict:
        url = f"{BASE_URL}{path}"
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT)
                r.raise_for_status()
                data = r.json()
                if data.get("retCode") != 0:
                    raise RuntimeError(f"Bybit error: {data.get('retMsg')}")
                return data["result"]
            except Exception as e:
                if attempt == 2:
                    raise
                log.warning(f"Retry {attempt + 1}: {e}")
                time.sleep(1)

    def get_top_pairs(self, n: int = 100) -> List[str]:
        """Top N USDT-perp pairs by 24h turnover (USD volume)."""
        result = self._get(
            "/v5/market/tickers",
            {"category": "linear"},
        )
        tickers = result.get("list", [])

        # Filter: USDT perpetuals only, exclude weird/dead pairs
        usdt_perps = [
            t for t in tickers
            if t["symbol"].endswith("USDT")
            and float(t.get("turnover24h", 0)) > 0
        ]

        # Sort by USD turnover descending
        usdt_perps.sort(key=lambda t: float(t["turnover24h"]), reverse=True)

        return [t["symbol"] for t in usdt_perps[:n]]

    def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> Optional[List[dict]]:
        """
        Fetch klines. Interval values: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
        Returns oldest-to-newest list of dicts:
          {open_time, open, high, low, close, volume, turnover}
        Bybit returns NEWEST first — we reverse so the latest is last.
        """
        result = self._get(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": min(limit, 1000),
            },
        )
        raw = result.get("list", [])
        if not raw:
            return None

        # Bybit kline format: [start, open, high, low, close, volume, turnover]
        # API returns newest first; reverse for chronological order.
        candles = []
        for k in reversed(raw):
            candles.append({
                "time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "turnover": float(k[6]),
            })
        return candles
