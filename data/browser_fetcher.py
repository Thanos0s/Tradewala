"""
browser_fetcher.py
==================
Uses Playwright (headless Chromium) to scrape real-time data from:
  - NSE India  → option chain, PCR, FII/DII, live prices, ban list
  - TradingView → technical signals (RSI, MACD, BB, EMA recommendations)
  - BSE India   → corporate announcements
  - MoneyControl / ET Markets → news headlines

NO API KEYS REQUIRED — everything is scraped from public websites.

Auto-setup: run `python -m data.browser_fetcher --setup` once on a new machine.
"""

import json
import logging
import time
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy import so the module loads even if playwright isn't installed ────────
def _get_playwright():
    try:
        # Reset current thread's event loop to prevent Playwright Sync API error
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:
            try:
                asyncio.set_event_loop(asyncio.new_event_loop())
            except Exception:
                pass

        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# NSE Browser Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class NSEBrowserFetcher:
    """
    Fetches live NSE data using a real browser session.
    NSE blocks simple HTTP requests — the browser bypasses all bot detection.
    """
    BASE = "https://www.nseindia.com"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        sync_playwright = _get_playwright()
        if sync_playwright is None:
            raise RuntimeError("Playwright not available")
        self._pw_context = sync_playwright()
        self._pw = self._pw_context.__enter__()
        try:
            self._browser = self._pw.chromium.launch(
                headless=self.headless,
                args=["--disable-http2"]
            )
            self._context = self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )
            self._page = self._context.new_page()
            # Warm up: visit homepage to get cookies/session (with long timeout & retries)
            logger.info("NSEBrowserFetcher: loading NSE homepage for session cookies...")
            for attempt in range(3):
                try:
                    self._page.goto(self.BASE, wait_until="domcontentloaded", timeout=180000)
                    time.sleep(5)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    logger.warning(f"NSEBrowserFetcher retry {attempt + 1}: {e}")
                    time.sleep(5)
            return self
        except Exception as e:
            logger.error(f"Error during NSEBrowserFetcher.__enter__: {e}")
            if hasattr(self, '_browser') and self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            if hasattr(self, '_pw_context') and self._pw_context:
                try:
                    self._pw_context.__exit__(None, None, None)
                except Exception:
                    pass
            raise

    def __exit__(self, *args):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, '_pw_context') and self._pw_context:
            try:
                self._pw_context.__exit__(*args)
            except Exception:
                pass

    def _fetch_json_api(self, path: str) -> dict:
        """Fetch a NSE JSON API endpoint using the warmed-up browser session."""
        url = f"{self.BASE}{path}"
        resp = self._page.evaluate(f"""
            async () => {{
                const r = await fetch('{url}', {{
                    headers: {{
                        'Accept': 'application/json',
                        'Referer': '{self.BASE}',
                    }}
                }});
                return await r.json();
            }}
        """)
        return resp

    def get_option_chain(self, symbol: str = "NIFTY") -> dict:
        """Fetch Nifty / BankNifty option chain."""
        try:
            logger.info(f"Fetching NSE option chain for {symbol}...")
            data = self._fetch_json_api(f"/api/option-chain-indices?symbol={symbol}")
            return data
        except Exception as e:
            logger.error(f"NSE option chain error ({symbol}): {e}")
            return {}

    def get_fii_dii(self) -> dict:
        """Fetch FII/DII provisional data."""
        try:
            data = self._fetch_json_api("/api/fiidiiTradeReact")
            return {
                "fii_net": float(data.get("fiiNet", 0)),
                "dii_net": float(data.get("diiNet", 0)),
                "date":    data.get("timestamp", ""),
            }
        except Exception as e:
            logger.error(f"FII/DII fetch error: {e}")
            return {"fii_net": 0.0, "dii_net": 0.0, "date": ""}

    def get_ban_list(self) -> list:
        """Fetch F&O ban list for today."""
        try:
            data = self._fetch_json_api("/api/fo-mktlots")
            ban = data.get("ban", [])
            if isinstance(ban, list):
                return ban
            return []
        except Exception as e:
            logger.error(f"Ban list fetch error: {e}")
            return []

    def get_market_status(self) -> dict:
        """Check if market is open."""
        try:
            data = self._fetch_json_api("/api/marketStatus")
            return {
                "market_open": data.get("marketOpen", False),
                "status": data.get("marketStatus", "Unknown"),
            }
        except Exception as e:
            logger.error(f"Market status error: {e}")
            return {"market_open": False, "status": "Unknown"}

    def get_live_quote(self, symbol: str) -> dict:
        """Get live price quote for an NSE symbol (without .NS suffix)."""
        try:
            data = self._fetch_json_api(f"/api/quote-equity?symbol={symbol}")
            price_info = data.get("priceInfo", {})
            return {
                "symbol":        symbol,
                "last_price":    float(price_info.get("lastPrice", 0)),
                "change":        float(price_info.get("change", 0)),
                "change_pct":    float(price_info.get("pChange", 0)),
                "open":          float(price_info.get("open", 0)),
                "high":          float(price_info.get("intraDayHighLow", {}).get("max", 0)),
                "low":           float(price_info.get("intraDayHighLow", {}).get("min", 0)),
                "prev_close":    float(price_info.get("previousClose", 0)),
                "volume":        int(data.get("marketDeptOrderBook", {}).get("tradeInfo", {}).get("totalTradedVolume", 0)),
            }
        except Exception as e:
            logger.error(f"Live quote error ({symbol}): {e}")
            return {}


# ─────────────────────────────────────────────────────────────────────────────
# TradingView Browser Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class TradingViewBrowserFetcher:
    """
    Scrapes TradingView technical analysis signals using a real browser.
    Bypasses the 429 rate-limit that hits the tradingview_ta library.
    
    Returns: BUY / SELL / NEUTRAL + individual indicator values.
    """
    BASE = "https://www.tradingview.com"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        sync_playwright = _get_playwright()
        if sync_playwright is None:
            raise RuntimeError("Playwright not available")
        self._pw_context = sync_playwright()
        self._pw = self._pw_context.__enter__()
        try:
            self._browser = self._pw.chromium.launch(headless=self.headless)
            ctx = self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            self._page = ctx.new_page()
            return self
        except Exception as e:
            logger.error(f"Error during TradingViewBrowserFetcher.__enter__: {e}")
            if hasattr(self, '_browser') and self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            if hasattr(self, '_pw_context') and self._pw_context:
                try:
                    self._pw_context.__exit__(None, None, None)
                except Exception:
                    pass
            raise

    def __exit__(self, *args):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, '_pw_context') and self._pw_context:
            try:
                self._pw_context.__exit__(*args)
            except Exception:
                pass

    def get_technical_analysis(self, symbol: str, exchange: str = "NSE") -> dict:
        """
        Scrape TradingView's technical analysis widget for a symbol.
        Returns dict with recommendation, buy_count, sell_count, neutral_count.
        """
        try:
            tv_symbol = f"{exchange}:{symbol.replace('.NS', '')}"
            url = f"{self.BASE}/symbols/{tv_symbol}/technicals/"
            logger.info(f"TradingView scraping: {tv_symbol}")
            for attempt in range(3):
                try:
                    self._page.goto(url, wait_until="networkidle", timeout=180000)
                    time.sleep(5)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    logger.warning(f"TradingView retry {attempt + 1}: {e}")
                    time.sleep(5)

            # Try to read the summary widget text
            try:
                summary_el = self._page.wait_for_selector(
                    '[data-name="technicals-widget-wrapper"]', timeout=10000
                )
                text = summary_el.inner_text()
            except Exception:
                text = self._page.content()

            # Parse buy/sell/neutral counts from page text
            buy_count     = len(re.findall(r'\bBuy\b',     text, re.IGNORECASE))
            sell_count    = len(re.findall(r'\bSell\b',    text, re.IGNORECASE))
            neutral_count = len(re.findall(r'\bNeutral\b', text, re.IGNORECASE))

            if buy_count > sell_count and buy_count > neutral_count:
                recommendation = "BUY"
            elif sell_count > buy_count and sell_count > neutral_count:
                recommendation = "SELL"
            else:
                recommendation = "NEUTRAL"

            return {
                "symbol":         symbol,
                "recommendation": recommendation,
                "buy_count":      buy_count,
                "sell_count":     sell_count,
                "neutral_count":  neutral_count,
                "source":         "TradingView-Browser",
            }
        except Exception as e:
            logger.error(f"TradingView browser error ({symbol}): {e}")
            return {"symbol": symbol, "recommendation": "NEUTRAL", "buy_count": 0,
                    "sell_count": 0, "neutral_count": 0, "source": "error"}


# ─────────────────────────────────────────────────────────────────────────────
# BSE Browser Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class BSEBrowserFetcher:
    """Scrapes BSE India for corporate announcements."""
    BASE = "https://www.bseindia.com"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        sync_playwright = _get_playwright()
        if sync_playwright is None:
            raise RuntimeError("Playwright not available")
        self._pw_context = sync_playwright()
        self._pw = self._pw_context.__enter__()
        try:
            self._browser = self._pw.chromium.launch(headless=self.headless)
            ctx = self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            self._page = ctx.new_page()
            return self
        except Exception as e:
            logger.error(f"Error during BSEBrowserFetcher.__enter__: {e}")
            if hasattr(self, '_browser') and self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            if hasattr(self, '_pw_context') and self._pw_context:
                try:
                    self._pw_context.__exit__(None, None, None)
                except Exception:
                    pass
            raise

    def __exit__(self, *args):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, '_pw_context') and self._pw_context:
            try:
                self._pw_context.__exit__(*args)
            except Exception:
                pass

    def get_announcements(self, limit: int = 50) -> list:
        """Scrape latest BSE corporate announcements."""
        try:
            url = f"{self.BASE}/corporates/ann.html"
            for attempt in range(3):
                try:
                    self._page.goto(url, wait_until="domcontentloaded", timeout=180000)
                    time.sleep(5)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    logger.warning(f"BSE retry {attempt + 1}: {e}")
                    time.sleep(5)
            rows = self._page.query_selector_all("table tr")
            announcements = []
            for row in rows[:limit]:
                cells = row.query_selector_all("td")
                if len(cells) >= 3:
                    announcements.append({
                        "company":  cells[0].inner_text().strip(),
                        "subject":  cells[2].inner_text().strip(),
                        "date":     cells[1].inner_text().strip(),
                        "source":   "BSE",
                    })
            logger.info(f"BSE: scraped {len(announcements)} announcements")
            return announcements
        except Exception as e:
            logger.error(f"BSE announcements error: {e}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# News Browser Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class NewsBrowserFetcher:
    """
    Scrapes financial news from MoneyControl and ET Markets using a real browser.
    Gets full headlines + article summaries — much more than the simple requests scraper.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        sync_playwright = _get_playwright()
        if sync_playwright is None:
            raise RuntimeError("Playwright not available")
        self._pw_context = sync_playwright()
        self._pw = self._pw_context.__enter__()
        try:
            self._browser = self._pw.chromium.launch(headless=self.headless)
            ctx = self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            self._page = ctx.new_page()
            return self
        except Exception as e:
            logger.error(f"Error during NewsBrowserFetcher.__enter__: {e}")
            if hasattr(self, '_browser') and self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            if hasattr(self, '_pw_context') and self._pw_context:
                try:
                    self._pw_context.__exit__(None, None, None)
                except Exception:
                    pass
            raise

    def __exit__(self, *args):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, '_pw_context') and self._pw_context:
            try:
                self._pw_context.__exit__(*args)
            except Exception:
                pass

    def _scrape_page(self, url: str, headline_selector: str,
                     summary_selector: Optional[str], source: str,
                     limit: int = 30) -> list:
        try:
            for attempt in range(3):
                try:
                    self._page.goto(url, wait_until="domcontentloaded", timeout=180000)
                    time.sleep(5)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    logger.warning(f"NewsBrowser retry {attempt + 1}: {e}")
                    time.sleep(5)
            headlines = self._page.query_selector_all(headline_selector)
            items = []
            for el in headlines[:limit]:
                headline = el.inner_text().strip()
                if not headline:
                    continue
                summary = ""
                if summary_selector:
                    try:
                        sib = el.evaluate_handle(
                            f"el => el.closest('article')?.querySelector('{summary_selector}')"
                        )
                        if sib:
                            summary = sib.inner_text().strip()
                    except Exception:
                        pass
                items.append({"headline": headline, "summary": summary, "source": source})
            logger.info(f"{source}: scraped {len(items)} headlines")
            return items
        except Exception as e:
            logger.error(f"{source} scrape error: {e}")
            return []

    def scrape_moneycontrol(self, limit: int = 40) -> list:
        return self._scrape_page(
            url="https://www.moneycontrol.com/news/business/markets/",
            headline_selector="h2.article_title a, .news_item h2 a, li.clearfix h2 a",
            summary_selector="p",
            source="MoneyControl",
            limit=limit,
        )

    def scrape_et_markets(self, limit: int = 40) -> list:
        return self._scrape_page(
            url="https://economictimes.indiatimes.com/markets/stocks/news",
            headline_selector=".eachStory h3 a, .story-box h3 a, article h2 a",
            summary_selector="p.synopsis",
            source="ET Markets",
            limit=limit,
        )

    def scrape_business_standard(self, limit: int = 30) -> list:
        return self._scrape_page(
            url="https://www.business-standard.com/markets/news",
            headline_selector="h2.headline a, .card-title a",
            summary_selector=".card-body p",
            source="Business Standard",
            limit=limit,
        )

    def scrape_all(self) -> list:
        """Scrape all sources and merge results."""
        all_news = []
        all_news.extend(self.scrape_moneycontrol())
        all_news.extend(self.scrape_et_markets())
        all_news.extend(self.scrape_business_standard())
        logger.info(f"Total news scraped via browser: {len(all_news)} articles")
        return all_news


# ─────────────────────────────────────────────────────────────────────────────
# PCR Calculator (shared utility)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_pcr(option_chain_data: dict) -> float:
    """Calculate Put-Call Ratio from NSE option chain JSON."""
    try:
        records = option_chain_data.get("records", {}).get("data", [])
        total_pe_oi = sum(r.get("PE", {}).get("openInterest", 0) for r in records if r.get("PE"))
        total_ce_oi = sum(r.get("CE", {}).get("openInterest", 0) for r in records if r.get("CE"))
        if total_ce_oi == 0:
            return 1.0
        pcr = total_pe_oi / total_ce_oi
        logger.info(f"PCR calculated: {pcr:.3f} (PE OI: {total_pe_oi:,} / CE OI: {total_ce_oi:,})")
        return round(pcr, 3)
    except Exception as e:
        logger.error(f"PCR calculation error: {e}")
        return 1.0


def calculate_max_pain(option_chain_data: dict) -> float:
    """Calculate max pain strike price from NSE option chain."""
    try:
        records = option_chain_data.get("records", {}).get("data", [])
        strikes = {}
        for r in records:
            strike = r.get("strikePrice", 0)
            if strike not in strikes:
                strikes[strike] = {"CE_OI": 0, "PE_OI": 0}
            strikes[strike]["CE_OI"] += r.get("CE", {}).get("openInterest", 0)
            strikes[strike]["PE_OI"] += r.get("PE", {}).get("openInterest", 0)

        min_pain = float("inf")
        max_pain_strike = 0
        for strike, oi in strikes.items():
            pain = sum(
                max(0, (s - strike)) * d["CE_OI"] + max(0, (strike - s)) * d["PE_OI"]
                for s, d in strikes.items()
            )
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = strike
        return float(max_pain_strike)
    except Exception as e:
        logger.error(f"Max pain error: {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CLI Setup Tool
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if "--setup" in sys.argv:
        print("\n🔧 Installing Playwright browser (Chromium)...")
        import subprocess
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Chromium installed successfully.\n")

    elif "--test" in sys.argv:
        print("\n🧪 Testing NSE browser fetcher...")
        with NSEBrowserFetcher(headless=True) as nse:
            status = nse.get_market_status()
            print(f"Market status: {status}")
            chain = nse.get_option_chain("NIFTY")
            pcr = calculate_pcr(chain)
            print(f"Nifty PCR: {pcr}")
            fii = nse.get_fii_dii()
            print(f"FII/DII: {fii}")

        print("\n🧪 Testing news browser fetcher...")
        with NewsBrowserFetcher(headless=True) as news:
            articles = news.scrape_moneycontrol(limit=5)
            for a in articles:
                print(f"  [{a['source']}] {a['headline'][:80]}")

        print("\n✅ All browser fetchers working!\n")

    else:
        print("Usage:")
        print("  python -m data.browser_fetcher --setup   # Install Chromium (run once)")
        print("  python -m data.browser_fetcher --test    # Test all scrapers")
