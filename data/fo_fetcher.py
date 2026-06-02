import os
import requests
import json
import logging
import math
from typing import List, Dict


class FOFetcher:
    """
    Fetches all F&O data from NSE.
    PRIMARY: Playwright browser (bypasses NSE bot detection & API 404s)
    FALLBACK: Direct HTTP with session cookies (works when browser unavailable)
    """

    def __init__(self):
        self.session = requests.Session()
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com",
        }
        # Warm-up HTTP session with cookies.
        try:
            self.session.get("https://www.nseindia.com", headers=self.base_headers, timeout=10)
        except Exception as e:
            logging.warning(f"NSE session warmup failed: {e}")

        # Try to initialize Upstox Fetcher.
        self._upstox_fetcher = None
        try:
            from data.upstox_fetcher import UpstoxFetcher
            self._upstox_fetcher = UpstoxFetcher()
            if not self._upstox_fetcher.access_token:
                self._upstox_fetcher = None
        except Exception as e:
            logging.warning(f"UpstoxFetcher initialization failed: {e}")

        # Browser fetcher (lazy initialized)
        self._browser_fetcher = None

    def _init_browser_fetcher(self):
        """Lazy-initialize the Playwright browser fetcher."""
        if self._browser_fetcher is not None:
            return
        try:
            from data.browser_fetcher import NSEBrowserFetcher
            self._browser_fetcher = NSEBrowserFetcher(headless=True)
            self._browser_fetcher.__enter__()
            logging.info("FOFetcher: Lazy-initialized Playwright browser fallback")
        except Exception as e:
            logging.warning(f"Browser fetcher unavailable ({e}) - using HTTP fallback")

    def __del__(self):
        """Clean up browser on garbage collection."""
        if getattr(self, "_browser_fetcher", None):
            try:
                self._browser_fetcher.__exit__(None, None, None)
            except Exception:
                pass

    def _make_request(self, url: str) -> Dict:
        """HTTP fallback request with NSE session cookies."""
        try:
            resp = self.session.get(url, headers=self.base_headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"NSE FO request failed for {url}: {e}")
            return {}

    def get_option_chain(self, symbol: str = "NIFTY") -> Dict:
        """Fetch complete option chain. Upstox first, Browser second, HTTP fallback."""
        # Try Upstox approach first
        if self._upstox_fetcher:
            try:
                data = self._upstox_fetcher.get_option_chain(symbol)
                if data:
                    logging.info(f"FOFetcher: Option chain for {symbol} successfully fetched via Upstox API")
                    return data
            except Exception as e:
                logging.warning(f"Upstox option chain fetch failed for {symbol} ({e}), falling back to browser")

        # Try browser approach second
        self._init_browser_fetcher()
        if self._browser_fetcher:
            try:
                data = self._browser_fetcher.get_option_chain(symbol)
                if data:
                    return data
            except Exception as e:
                logging.warning(f"Browser option chain failed ({e}), trying HTTP")

        # HTTP fallback
        if symbol.upper() in {"NIFTY", "BANKNIFTY"}:
            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol.upper()}"
        else:
            url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol.upper()}"
        return self._make_request(url)

    def calculate_pcr(self, option_chain: Dict):
        """Calculate Put-Call Ratio from option chain data.
        Supports both NSE-shaped payloads and Upstox-mapped payloads.

        Returns:
            float | None: PCR value when it can be computed, otherwise None.
        """
        try:
            if not option_chain or not isinstance(option_chain, dict):
                return None

            data = option_chain.get("records", {}).get("data", [])
            if not data and isinstance(option_chain.get("data"), list):
                data = option_chain.get("data", [])

            total_put_oi = 0.0
            total_call_oi = 0.0
            rows_seen = 0

            for item in data:
                if not isinstance(item, dict):
                    continue
                rows_seen += 1

                ce = item.get("CE") or item.get("call_options") or {}
                pe = item.get("PE") or item.get("put_options") or {}

                ce_oi = 0
                pe_oi = 0

                if isinstance(ce, dict):
                    ce_oi = ce.get("openInterest", 0)
                    if not ce_oi and isinstance(ce.get("market_data"), dict):
                        ce_oi = ce["market_data"].get("oi", 0)

                if isinstance(pe, dict):
                    pe_oi = pe.get("openInterest", 0)
                    if not pe_oi and isinstance(pe.get("market_data"), dict):
                        pe_oi = pe["market_data"].get("oi", 0)

                total_call_oi += float(ce_oi or 0)
                total_put_oi += float(pe_oi or 0)

            if rows_seen == 0 or total_call_oi <= 0:
                logging.warning(
                    "PCR calculation skipped: no usable call OI rows were found in option chain data."
                )
                return None

            pcr = total_put_oi / total_call_oi
            if not math.isfinite(pcr) or pcr < 0:
                return None
            return float(pcr)
        except Exception as e:
            logging.error(f"PCR calculation error: {e}")
            return None

    def calculate_max_pain(self, option_chain: Dict) -> int:
        """Calculate Max Pain strike price.
        For each possible expiry strike, compute total loss for all holders.
        Returns the strike with minimum total loss.
        """
        try:
            data = option_chain.get("records", {}).get("data", [])
            # Gather all strikes
            strikes = set()
            for itm in data:
                if "strikePrice" in itm:
                    strikes.add(itm["strikePrice"])
            min_loss = float("inf")
            max_pain_strike = 0
            for strike in strikes:
                loss = 0
                for itm in data:
                    ce = itm.get("CE")
                    pe = itm.get("PE")
                    if ce:
                        # Call holder loss if strike ends below expiry strike
                        loss += max(strike - ce["strikePrice"], 0) * ce.get("openInterest", 0)
                    if pe:
                        # Put holder loss if expiry strike ends above expiry strike
                        loss += max(pe["strikePrice"] - strike, 0) * pe.get("openInterest", 0)
                if loss < min_loss:
                    min_loss = loss
                    max_pain_strike = strike
            return int(max_pain_strike)
        except Exception as e:
            logging.error(f"Max Pain calculation error: {e}")
            return 0

    def get_highest_oi_strikes(self, option_chain: Dict) -> Dict:
        """Find strikes with highest OI on call side (resistance) and put side (support)."""
        try:
            data = option_chain.get("records", {}).get("data", [])
            max_ce_oi = max_ce_strike = 0
            max_pe_oi = max_pe_strike = 0
            for itm in data:
                ce = itm.get("CE")
                pe = itm.get("PE")
                if ce:
                    if ce.get("openInterest", 0) > max_ce_oi:
                        max_ce_oi = ce["openInterest"]
                        max_ce_strike = ce["strikePrice"]
                if pe:
                    if pe.get("openInterest", 0) > max_pe_oi:
                        max_pe_oi = pe["openInterest"]
                        max_pe_strike = pe["strikePrice"]
            return {
                "ce_resistance": int(max_ce_strike),
                "pe_support": int(max_pe_strike),
                "ce_oi": int(max_ce_oi),
                "pe_oi": int(max_pe_oi),
            }
        except Exception as e:
            logging.error(f"Highest OI strikes error: {e}")
            return {}

    def get_fo_ban_list(self) -> List[str]:
        """Fetch today's F&O ban list. CSV first, then API, then Browser fallback."""
        # 1. Try CSV archive first (simplest, fastest, no bot protection)
        try:
            csv_url = "https://archives.nseindia.com/content/fo/fo_secban.csv"
            resp = self.session.get(csv_url, timeout=10)
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                ban_symbols = []
                for line in lines[1:]:
                    if "," in line:
                        parts = line.split(",")
                        if len(parts) > 1:
                            sym = parts[1].strip().upper()
                            if sym:
                                ban_symbols.append(sym)
                logging.info(f"FOFetcher: Ban list successfully fetched via NSE CSV archive: {ban_symbols}")
                return ban_symbols
        except Exception as e:
            logging.warning(f"CSV archive ban list failed: {e}")

        # 2. Try API fallback
        try:
            url = "https://www.nseindia.com/api/fo-mktlots"
            data = self._make_request(url)
            bans = data.get("data", [])
            ban_symbols = [item.get("symbol", "") for item in bans]
            if ban_symbols:
                logging.info(f"FOFetcher: Ban list fetched via NSE API fallback: {ban_symbols}")
                return ban_symbols
        except Exception as e:
            logging.warning(f"HTTP API ban list failed: {e}")

        # 3. Try Playwright browser fallback
        self._init_browser_fetcher()
        if self._browser_fetcher:
            try:
                ban = self._browser_fetcher.get_ban_list()
                if ban:
                    logging.info(f"Ban list via browser: {ban}")
                    return ban
            except Exception as e:
                logging.warning(f"Browser ban list failed ({e})")

        return []

    def get_stock_futures_activity(self, symbols: List[str]) -> Dict:
        """For each symbol, get futures OI change and price change, classify activity.
        Returns dict with four categories of lists.
        """
        result = {
            "long_buildup": [],
            "short_buildup": [],
            "long_unwinding": [],
            "short_covering": [],
        }
        for sym in symbols:
            try:
                url = f"https://www.nseindia.com/api/quote-derivative?symbol={sym.upper()}"
                data = self._make_request(url)
                futures = data.get("priceInfo", {})
                price_change = futures.get("priceChange", 0)
                oi_change = futures.get("oiChange", 0)
                if price_change > 0 and oi_change > 0:
                    result["long_buildup"].append(sym)
                elif price_change < 0 and oi_change > 0:
                    result["short_buildup"].append(sym)
                elif price_change < 0 and oi_change < 0:
                    result["long_unwinding"].append(sym)
                elif price_change > 0 and oi_change < 0:
                    result["short_covering"].append(sym)
            except Exception as e:
                logging.error(f"Futures activity fetch error for {sym}: {e}")
        return result

    def get_banknifty_option_chain(self) -> Dict:
        """Fetch option chain for BANKNIFTY indices."""
        return self.get_option_chain(symbol="BANKNIFTY")
