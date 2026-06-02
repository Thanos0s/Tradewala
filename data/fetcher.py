import os
import pandas as pd
import yfinance as yf
import requests
import json
from datetime import datetime, timedelta
import pytz
from pathlib import Path
from tqdm import tqdm
import logging

CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache"))
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

class DataFetcher:
    """
    Fetches OHLCV data for NSE stocks.
    Primary: yfinance (reliable, free, works for .NS suffix)
    Fallback: nsepy for real-time intraday data
    """

    def __init__(self):
        self.session = requests.Session()
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com",
        }
        # Initialise NSE cookies
        try:
            self.session.get("https://www.nseindia.com", headers=self.base_headers, timeout=10)
        except Exception as e:
            logging.warning(f"Failed to initialise NSE session: {e}")

    def _cache_path(self, symbol: str, suffix: str) -> str:
        filename = f"{symbol}_{suffix}.parquet"
        return os.path.join(CACHE_DIR, filename)

    def get_historical_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """Download historical daily OHLCV from yfinance.
        Returns DataFrame with columns: open, high, low, close, volume, amount, timestamps.
        Caches result to ./data/cache/{symbol}_daily.parquet
        """
        cache_file = self._cache_path(symbol, "daily")
        if os.path.exists(cache_file):
            df = pd.read_parquet(cache_file)
            return df
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                raise ValueError("Empty dataframe from yfinance")
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            df["amount"] = df["close"] * df["volume"]
            df["timestamps"] = df.index.tz_localize(None)
            df.reset_index(drop=True, inplace=True)
            df.to_parquet(cache_file, index=False)
            return df
        except Exception as e:
            logging.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise

    def get_intraday_ohlcv(self, symbol: str, interval: str = "15m") -> pd.DataFrame:
        """Download today's intraday candles from yfinance.
        Returns same format as get_historical_ohlcv.
        """
        cache_file = self._cache_path(symbol, f"intraday_{interval}")
        if os.path.exists(cache_file):
            mod_time = datetime.fromtimestamp(os.path.getmtime(cache_file), pytz.UTC)
            if mod_time.date() == datetime.utcnow().date():
                return pd.read_parquet(cache_file)
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval=interval)
            if df.empty:
                raise ValueError("Empty intraday data")
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            df["amount"] = df["close"] * df["volume"]
            df["timestamps"] = df.index.tz_localize(None)
            df.reset_index(drop=True, inplace=True)
            df.to_parquet(cache_file, index=False)
            return df
        except Exception as e:
            logging.error(f"Intraday fetch error for {symbol}: {e}")
            raise

    def get_batch_historical(self, symbols: list, period: str = "2y") -> dict:
        """Download historical data for multiple symbols at once.
        Returns dict: {symbol: DataFrame}
        """
        result = {}
        try:
            logging.info(f"Downloading historical data for {len(symbols)} tickers...")
            data = yf.download(tickers=symbols, period=period, interval="1d", group_by='ticker', auto_adjust=False, threads=True)
            
            is_multi = isinstance(data.columns, pd.MultiIndex)
            for sym in symbols:
                try:
                    df = None
                    if len(symbols) == 1:
                        df = data
                    else:
                        if is_multi and sym in data.columns.levels[0]:
                            df = data[sym]
                        elif not is_multi and sym in data:
                            df = data[sym]
                    
                    # If ticker was not in batch download or returned empty, try individual fetch
                    if df is None or df.empty or "Close" not in df.columns:
                        logging.warning(f"Ticker {sym} not found or empty in batch yfinance results. Attempting individual fetch...")
                        try:
                            ticker = yf.Ticker(sym)
                            df = ticker.history(period=period, interval="1d")
                        except Exception as ind_err:
                            logging.error(f"Individual fetch failed for {sym}: {ind_err}")
                            df = None
                    
                    if df is None or df.empty or "Close" not in df.columns:
                        logging.warning(f"Skipping {sym} due to lack of historical data.")
                        continue
                        
                    df = df.rename(columns={
                        "Open": "open",
                        "High": "high",
                        "Low": "low",
                        "Close": "close",
                        "Volume": "volume",
                    })
                    df["amount"] = df["close"] * df["volume"]
                    df["timestamps"] = df.index.tz_localize(None)
                    df.reset_index(drop=True, inplace=True)
                    result[sym] = df
                    cache_file = self._cache_path(sym, "daily")
                    df.to_parquet(cache_file, index=False)
                except Exception as e:
                    logging.error(f"Error processing ticker {sym}: {e}")
        except Exception as e:
            logging.error(f"Batch fetch error: {e}")
            raise
        return result

    def _make_nse_request(self, url: str) -> dict:
        """Helper to fetch NSE APIs with proper cookies and headers."""
        try:
            response = self.session.get(url, headers=self.base_headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"NSE request failed for {url}: {e}")
            raise

    def get_nse_market_status(self) -> dict:
        url = "https://www.nseindia.com/api/marketStatus"
        data = self._make_nse_request(url)
        return {"market_open": data.get("marketOpen", False), "status": data.get("marketStatus", "")}

    def get_gift_nifty(self) -> dict:
        try:
            url = "https://www.nseindia.com/api/liveEquity-derivatives"
            data = self._make_nse_request(url)
            gift = data.get("giftNifty", {})
            return {
                "gift_nifty_level": float(gift.get("giftNiftyValue", 0)),
                "change": float(gift.get("giftNiftyChng", 0)),
                "change_pct": float(gift.get("giftNiftyPerc", 0)),
            }
        except Exception:
            logging.warning("Falling back to investing.com for Gift Nifty")
            return {"gift_nifty_level": 0.0, "change": 0.0, "change_pct": 0.0}

    def get_fii_dii_data(self) -> dict:
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        data = self._make_nse_request(url)
        return {"fii_net": float(data.get("fiiNet", 0)), "dii_net": float(data.get("diiNet", 0)), "date": data.get("timestamp", "")}

    def get_india_vix(self) -> dict:
        try:
            vix = yf.Ticker("^INDIAVIX").history(period="1d")
            if vix.empty:
                raise ValueError
            level = float(vix["Close"].iloc[-1])
            mood = "HIGH_FEAR" if level > 20 else ("LOW_FEAR" if level < 14 else "NEUTRAL")
            return {"vix": level, "level": mood}
        except Exception as e:
            logging.error(f"India VIX fetch error: {e}")
            return {"vix": 0.0, "level": "NEUTRAL"}
def fetch_price_data(symbols=None, period="2y"):
    """Fetch historical OHLCV data for the watchlist or given symbols.
    Returns a dict of DataFrames keyed by symbol.
    """
    if symbols is None:
        from config import NSE_WATCHLIST
        symbols = NSE_WATCHLIST
    fetcher = DataFetcher()
    return fetcher.get_batch_historical(symbols, period)

def fetch_global_indicators() -> dict:
    """Fetch daily closed levels for Nasdaq, Shanghai, Gold Futures, and DXY."""
    tickers = {
        "nasdaq": "^IXIC",
        "shanghai": "000001.SS",
        "gold": "GC=F",
        "dxy": "DX-Y.NYB"
    }
    results = {}
    for name, sym in tickers.items():
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period="5d")
            if not df.empty and len(df) >= 2:
                prev_close = float(df["Close"].iloc[-2])
                curr_close = float(df["Close"].iloc[-1])
                ret_1d = ((curr_close - prev_close) / prev_close) * 100.0
                results[name] = {
                    "current": curr_close,
                    "return_1d": round(ret_1d, 4)
                }
            else:
                results[name] = {"current": 0.0, "return_1d": 0.0}
        except Exception as e:
            logging.error(f"Failed to fetch global indicator {name}: {e}")
            results[name] = {"current": 0.0, "return_1d": 0.0}
    return results

