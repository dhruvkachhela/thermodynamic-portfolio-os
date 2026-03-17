"""
LIVE PRICE FETCHER
===================
Fetches real NSE stock prices from Yahoo Finance.
Free. No API key needed.

NSE stocks: symbol must end in .NS  (e.g. RELIANCE.NS)
BSE stocks: symbol must end in .BO  (e.g. RELIANCE.BO)

No SQLAlchemy needed — this version is standalone.
Prices are cached in memory for 15 minutes to avoid
hammering Yahoo Finance on every request.
"""

import os, sys
from datetime import datetime, timedelta
from typing import Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Try importing yfinance — if not installed yet, use fallback prices
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("⚠️  yfinance not installed. Run: pip install yfinance")

# ── In-memory price cache ──────────────────────────────────────────────────────
# Stores prices in a dict so we don't call Yahoo Finance on every request.
# Format: { "RELIANCE.NS": {"price": 2847.5, "fetched_at": datetime} }
_price_cache: Dict[str, dict] = {}
CACHE_MINUTES = 15

# ── Fallback prices ────────────────────────────────────────────────────────────
# Used when Yahoo Finance is unavailable (no internet, rate limited, etc.)
# Update these occasionally to keep demo data realistic.
FALLBACK_PRICES = {
    "RELIANCE.NS":    2850.0,
    "TCS.NS":         4200.0,
    "HDFCBANK.NS":    1680.0,
    "INFY.NS":        1950.0,
    "WIPRO.NS":        480.0,
    "BAJFINANCE.NS":  7200.0,
    "TATAMOTORS.NS":   980.0,
    "SBIN.NS":         780.0,
    "GOLDBEES.NS":      58.0,
    "LIQUIDBEES.NS":  1004.0,
}


class PriceFetcher:
    """
    Fetches live stock prices with in-memory caching.

    Usage:
        fetcher = PriceFetcher()
        prices  = fetcher.fetch_prices(["RELIANCE.NS", "TCS.NS"])
        # Returns: {"RELIANCE.NS": 2847.5, "TCS.NS": 4198.0}
    """

    def fetch_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current prices for a list of symbols.
        Uses memory cache if fresh (< 15 min), otherwise fetches live.
        """
        prices          = {}
        need_to_fetch   = []

        # Check cache for each symbol
        for symbol in symbols:
            cached = _price_cache.get(symbol)
            if cached and self._is_fresh(cached["fetched_at"]):
                prices[symbol] = cached["price"]  # use cache
            else:
                need_to_fetch.append(symbol)       # needs live fetch

        # Fetch stale/missing symbols from Yahoo Finance
        if need_to_fetch:
            live = self._fetch_from_yahoo(need_to_fetch)
            for symbol, price in live.items():
                prices[symbol] = price
                # Save to cache
                _price_cache[symbol] = {"price": price, "fetched_at": datetime.now()}

        return prices

    def fetch_single(self, symbol: str) -> float:
        """Fetch price for one symbol."""
        return self.fetch_prices([symbol]).get(symbol, 0.0)

    def _is_fresh(self, fetched_at: datetime) -> bool:
        """Returns True if cache is less than 15 minutes old."""
        return (datetime.now() - fetched_at) < timedelta(minutes=CACHE_MINUTES)

    def _fetch_from_yahoo(self, symbols: List[str]) -> Dict[str, float]:
        """
        Calls Yahoo Finance API to get real live prices.
        Falls back to hardcoded prices if Yahoo Finance fails.
        """
        if not YFINANCE_AVAILABLE:
            print("⚠️  yfinance not available — using fallback prices")
            return {s: FALLBACK_PRICES.get(s, 100.0) for s in symbols}

        prices = {}
        print(f"  📡 Fetching live prices for: {symbols}")

        try:
            # Fetch all symbols in one batch call (efficient)
            tickers = yf.Tickers(" ".join(symbols))

            for symbol in symbols:
                try:
                    info  = tickers.tickers[symbol].fast_info
                    price = (
                        getattr(info, 'last_price', None) or
                        getattr(info, 'regular_market_price', None)
                    )
                    if price and float(price) > 0:
                        prices[symbol] = float(price)
                        print(f"    ✅ {symbol}: ₹{price:.2f}")
                    else:
                        prices[symbol] = FALLBACK_PRICES.get(symbol, 100.0)
                        print(f"    ⚠️  {symbol}: no price returned, using fallback")
                except Exception as e:
                    prices[symbol] = FALLBACK_PRICES.get(symbol, 100.0)
                    print(f"    ❌ {symbol}: {e} — using fallback")

        except Exception as e:
            print(f"❌ Yahoo Finance failed: {e} — using all fallbacks")
            prices = {s: FALLBACK_PRICES.get(s, 100.0) for s in symbols}

        return prices

    def clear_cache(self):
        """Clears the in-memory price cache — forces fresh fetch next time."""
        _price_cache.clear()
        print("🗑️  Price cache cleared")
