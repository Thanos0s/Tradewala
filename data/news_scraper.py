import aiohttp
import asyncio
import logging
import json
# duplicate import removed
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os

class NewsScraper:
    """
    Scrapes financial news from public Indian market sources.
    Uses aiohttp for async requests and BeautifulSoup for parsing.
    """

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    RATE_LIMIT_SECONDS = 1  # simple delay between requests

    def __init__(self):
        self.session = None
        self.last_request = None

    async def _ensure_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(headers=self.BASE_HEADERS, timeout=timeout)

    async def _throttle(self):
        if self.last_request:
            elapsed = (datetime.utcnow() - self.last_request).total_seconds()
            if elapsed < self.RATE_LIMIT_SECONDS:
                await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self.last_request = datetime.utcnow()

    async def _fetch(self, url: str) -> str:
        await self._ensure_session()
        await self._throttle()
        async with self.session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def scrape_moneycontrol_news(self) -> list:
        """Scrape latest market news from MoneyControl. Returns last 20 articles."""
        urls = [
            "https://www.moneycontrol.com/news/business/markets/",
            "https://www.moneycontrol.com/news/business/stocks/",
        ]
        articles = []
        for url in urls:
            try:
                html = await self._fetch(url)
                soup = BeautifulSoup(html, "lxml")
                cards = soup.select("div.news-list li")[:20]
                for card in cards:
                    headline = card.select_one("h2 a").get_text(strip=True)
                    summary = card.select_one("p").get_text(strip=True) if card.select_one("p") else ""
                    timestamp_tag = card.select_one("span.time")
                    ts = timestamp_tag.get_text(strip=True) if timestamp_tag else datetime.utcnow().isoformat()
                    # rudimentary stock detection based on watchlist symbols
                    stock_mentioned = []
                    for sym in []:  # placeholder; stock detection handled later
                        if sym in headline or sym in summary:
                            stock_mentioned.append(sym)
                    articles.append({
                        "headline": headline,
                        "summary": summary,
                        "timestamp": ts,
                        "stock_mentioned": stock_mentioned,
                    })
            except Exception as e:
                logging.error(f"MoneyControl scrape error for {url}: {e}")
        return articles[:20]

    async def scrape_et_markets_news(self) -> list:
        """Scrape Economic Times Markets section. Returns last 20 headlines + summaries."""
        url = "https://economictimes.indiatimes.com/markets/stocks/news"
        articles = []
        try:
            html = await self._fetch(url)
            soup = BeautifulSoup(html, "lxml")
            items = soup.select("div.listingNewsItem")[:20]
            for item in items:
                headline_tag = item.select_one("h2 a")
                headline = headline_tag.get_text(strip=True) if headline_tag else ""
                summary_tag = item.select_one("p")
                summary = summary_tag.get_text(strip=True) if summary_tag else ""
                ts = datetime.utcnow().isoformat()
                articles.append({"headline": headline, "summary": summary, "timestamp": ts, "stock_mentioned": []})
        except Exception as e:
            logging.error(f"ET Markets scrape error: {e}")
        return articles

    async def scrape_bse_announcements(self) -> list:
        """Fetch corporate announcements from BSE API. Returns last 50 announcements."""
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%d-%m-%Y")
        today = datetime.utcnow().strftime("%d-%m-%Y")
        url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?strCat=-1&strPrevDate={yesterday}&strScrip=&strSearch=P&strToDate={today}&strType=C&subcategory=-1"
        articles = []
        try:
            txt = await self._fetch(url)
            data = json.loads(txt)
            for rec in data.get("d", [])[:50]:
                headline = rec.get("annTitle", "")
                summary = rec.get("annDesc", "")
                ts = rec.get("annDate", datetime.utcnow().isoformat())
                articles.append({"headline": headline, "summary": summary, "timestamp": ts, "stock_mentioned": []})
        except Exception as e:
            logging.error(f"BSE announcements error: {e}")
        return articles

    async def scrape_nse_announcements(self) -> list:
        """Fetch NSE corporate announcements from last 24 hours."""
        url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
        articles = []
        try:
            txt = await self._fetch(url)
            data = json.loads(txt)
            for rec in data.get("data", [])[:50]:
                headline = rec.get("headline", "")
                summary = rec.get("description", "")
                ts = rec.get("date", datetime.utcnow().isoformat())
                articles.append({"headline": headline, "summary": summary, "timestamp": ts, "stock_mentioned": []})
        except Exception as e:
            logging.error(f"NSE announcements error: {e}")
        return articles

    def get_sector_news_summary(self, sectors: list, news_items: list) -> dict:
        """Filter scraped news by sector keywords. Returns dict of sector -> headlines list."""
        mapping = {
            "IT": ["IT", "software", "tech", "TCS", "Infosys", "Wipro", "HCL"],
            "Banking": ["bank", "NBFC", "RBI", "credit", "NPA", "loan"],
            "Pharma": ["pharma", "drug", "FDA", "USFDA", "medicine", "API"],
            "Auto": ["auto", "vehicle", "EV", "electric vehicle", "Maruti", "sales"],
            "Energy": ["oil", "gas", "crude", "power", "renewable", "solar"],
            "Metals": ["steel", "aluminium", "copper", "zinc", "NMDC"],
            "FMCG": ["FMCG", "consumer", "rural demand", "inflation", "HUL"],
        }
        result = {sector: [] for sector in sectors}
        for item in news_items:
            txt = f"{item.get('headline') or ''} {item.get('summary') or ''}".lower()
            for sector in sectors:
                keywords = mapping.get(sector, [])
                if any(k.lower() in txt for k in keywords):
                    result[sector].append(item)
        return result

    def score_news_sentiment(self, news_items: list, stock_symbol: str) -> dict:
        """Score news sentiment for a specific stock (0-100)."""
        positive = ["upgrade", "buyback", "dividend", "beat estimates", "record profit", "new contract", "expansion", "FII buying", "52-week high", "strong growth"]
        negative = ["downgrade", "probe", "raid", "miss estimates", "loss", "debt", "default", "regulatory action", "recall"]
        score = 50
        found_headlines = []
        clean_symbol = stock_symbol.replace('.NS', '').lower()
        for item in news_items:
            txt = f"{item.get('headline') or ''} {item.get('summary') or ''}".lower()
            if clean_symbol in txt:
                found_headlines.append(item)
                if any(p.lower() in txt for p in positive):
                    score += 10
                if any(n.lower() in txt for n in negative):
                    score -= 10
        
        if not found_headlines:
            return {
                "sentiment_score": 50,
                "sentiment": "NEUTRAL",
                "relevant_headlines": [],
                "catalyst_strength": "NONE"
            }
            
        # Clamp score 0-100
        score = max(0, min(100, score))
        sentiment = "POSITIVE" if score > 60 else ("NEGATIVE" if score < 40 else "NEUTRAL")
        # Determine catalyst strength
        if score >= 80:
            strength = "STRONG"
        elif score >= 60:
            strength = "MODERATE"
        elif score > 40:
            strength = "WEAK"
        else:
            strength = "NONE"
        return {
            "sentiment_score": int(score),
            "sentiment": sentiment,
            "relevant_headlines": found_headlines,
            "catalyst_strength": strength
        }

    async def close(self):
        if self.session:
            await self.session.close()


def scrape_news():
    """Convenient wrapper to fetch news from all sources and return combined list.
    Bypasses slow/buggy browser news scrapers and directly uses robust, async static scrapers.
    """
    import asyncio
    import threading
    logging.info("Scraping news via fast async static scrapers...")
    
    articles = []
    
    async def _run():
        scraper = NewsScraper()
        results = await asyncio.gather(
            scraper.scrape_moneycontrol_news(),
            scraper.scrape_et_markets_news(),
            scraper.scrape_bse_announcements(),
            scraper.scrape_nse_announcements(),
            return_exceptions=True
        )
        await scraper.close()
        combined_articles = []
        for res in results:
            if isinstance(res, list):
                combined_articles.extend(res)
            elif isinstance(res, Exception):
                logging.error(f"Scraper task encountered error: {res}")
        return combined_articles

    result_container = []
    def thread_target():
        try:
            res = asyncio.run(_run())
            result_container.append(res)
        except Exception as thread_exc:
            logging.error(f"News scraping thread failed: {thread_exc}")
    
    t = threading.Thread(target=thread_target)
    t.start()
    t.join()
    
    if result_container:
        articles = result_container[0]
        
    logging.info(f"Successfully scraped {len(articles)} articles.")
    return articles

