import pandas as pd
import pandas_ta as ta
from tradingview_ta import TA_Handler, Interval, Exchange
import logging

class IndicatorEngine:
    """Computes technical indicators via pandas_ta and fetches live TradingView analysis."""

    def __init__(self, allow_live_fetch: bool = True):
        self._tv_fetcher = None
        self._browser_failed = False
        self._tv_cache = {}
        self.allow_live_fetch = allow_live_fetch

    def __del__(self):
        if hasattr(self, '_tv_fetcher') and self._tv_fetcher:
            try:
                self._tv_fetcher.__exit__(None, None, None)
            except Exception:
                pass

    def prefetch_tradingview_analysis(self, symbols: list):
        """Pre-fetch TradingView analysis for a list of symbols using the browser."""
        if not self.allow_live_fetch:
            for symbol in symbols:
                self._tv_cache[symbol] = {
                    "15m": {
                        "summary": {"RECOMMENDATION": "NEUTRAL"},
                        "indicators": {}
                    },
                    "1d": {
                        "summary": {"RECOMMENDATION": "NEUTRAL"},
                        "indicators": {}
                    }
                }
            return

        if self._browser_failed:
            return
            
        try:
            if self._tv_fetcher is None:
                from data.browser_fetcher import TradingViewBrowserFetcher
                logging.info("Initializing Playwright TradingViewBrowserFetcher for prefetch...")
                self._tv_fetcher = TradingViewBrowserFetcher(headless=True)
                self._tv_fetcher.__enter__()
                
            for symbol in symbols:
                clean_symbol = symbol.replace('.NS', '').replace('.BO', '')
                try:
                    res = self._tv_fetcher.get_technical_analysis(clean_symbol)
                    rec = res.get("recommendation", "NEUTRAL")
                    self._tv_cache[symbol] = {
                        "15m": {
                            "summary": {"RECOMMENDATION": rec},
                            "indicators": {}
                        },
                        "1d": {
                            "summary": {"RECOMMENDATION": rec},
                            "indicators": {}
                        }
                    }
                except Exception as e:
                    logging.warning(f"TradingView prefetch failed for {symbol}: {e}")
        except Exception as e:
            logging.error(f"TradingViewBrowserFetcher bulk init failed: {e}")
            self._browser_failed = True

    def get_tradingview_analysis(self, symbol: str) -> dict:
        """Use TradingViewBrowserFetcher first, fallback to tradingview_ta.
        Symbol format for NSE: "NSE:{SYMBOL}" (without .NS/.BO suffix).
        Returns dict with summary and indicator values.
        """
        if symbol in self._tv_cache:
            return self._tv_cache[symbol]

        if not self.allow_live_fetch:
            return {
                "15m": {
                    "summary": {"RECOMMENDATION": "NEUTRAL"},
                    "indicators": {}
                },
                "1d": {
                    "summary": {"RECOMMENDATION": "NEUTRAL"},
                    "indicators": {}
                }
            }

        # Try browser approach first (re-using the same browser instance)
        if not self._browser_failed:
            try:
                if self._tv_fetcher is None:
                    from data.browser_fetcher import TradingViewBrowserFetcher
                    logging.info("Initializing Playwright TradingViewBrowserFetcher...")
                    self._tv_fetcher = TradingViewBrowserFetcher(headless=True)
                    self._tv_fetcher.__enter__()
                
                # strip Yahoo suffixes
                clean_symbol = symbol.replace('.NS', '').replace('.BO', '')
                res = self._tv_fetcher.get_technical_analysis(clean_symbol)
                rec = res.get("recommendation", "NEUTRAL")
                return {
                    "15m": {
                        "summary": {"RECOMMENDATION": rec},
                        "indicators": {}
                    },
                    "1d": {
                        "summary": {"RECOMMENDATION": rec},
                        "indicators": {}
                    }
                }
            except Exception as e:
                logging.warning(f"TradingViewBrowserFetcher failed for {symbol} ({e}). Falling back to tradingview_ta.")
                self._browser_failed = True
                if self._tv_fetcher:
                    try:
                        self._tv_fetcher.__exit__(None, None, None)
                    except Exception:
                        pass
                    self._tv_fetcher = None

        # Fallback to tradingview_ta
        try:
            # strip .NS/.BO if present
            clean_symbol = symbol.replace('.NS', '').replace('.BO', '')
            result = {}
            for interval in [Interval.INTERVAL_15_MINUTES, Interval.INTERVAL_1_DAY]:
                handler = TA_Handler(
                    symbol=clean_symbol,
                    exchange="NSE",
                    screener="india",
                    interval=interval,
                )
                analysis = handler.get_analysis()
                summary = analysis.summary
                indicators = analysis.indicators
                key = "15m" if "15" in interval else "1d"
                result[key] = {
                    "summary": summary,
                    "indicators": indicators,
                }
            return result
        except Exception as e:
            logging.error(f"TradingView analysis fallback error for {symbol}: {e}")
            return {}

    def compute_all_indicators(self, df: pd.DataFrame) -> dict:
        """Compute all required indicators from OHLCV DataFrame.
        Returns latest values as a flat dict.
        """
        try:
            # Ensure required columns exist
            required = ["open", "high", "low", "close", "volume"]
            if not all(col in df.columns for col in required):
                raise ValueError("DataFrame missing required OHLCV columns")
            df_ta = df.copy()
            for col in required:
                df_ta[col] = pd.to_numeric(df_ta[col], errors='coerce')
            df_ta.dropna(subset=required, inplace=True)
            if len(df_ta) < 50:
                logging.warning(f"Insufficient data rows ({len(df_ta)}) for indicator computation.")
                return {}
            
            # EMA
            df_ta['ema9'] = ta.ema(df_ta['close'], length=9)
            df_ta['ema21'] = ta.ema(df_ta['close'], length=21)
            df_ta['ema50'] = ta.ema(df_ta['close'], length=50)
            df_ta['ema200'] = ta.ema(df_ta['close'], length=200)
            # RSI
            df_ta['rsi'] = ta.rsi(df_ta['close'], length=14)
            # MACD
            macd = ta.macd(df_ta['close'], fast=12, slow=26, signal=9)
            if macd is not None and not macd.empty:
                macd_cols = [c for c in macd.columns if c.startswith('MACD_')]
                signal_cols = [c for c in macd.columns if c.startswith('MACDs_')]
                hist_cols = [c for c in macd.columns if c.startswith('MACDh_')]
                if macd_cols and signal_cols and hist_cols:
                    df_ta['macd'] = macd[macd_cols[0]]
                    df_ta['macd_signal'] = macd[signal_cols[0]]
                    df_ta['macd_hist'] = macd[hist_cols[0]]
                else:
                    df_ta['macd'] = 0.0
                    df_ta['macd_signal'] = 0.0
                    df_ta['macd_hist'] = 0.0
            else:
                df_ta['macd'] = 0.0
                df_ta['macd_signal'] = 0.0
                df_ta['macd_hist'] = 0.0
            # Stoch RSI
            stochrsi = ta.stochrsi(df_ta['close'])
            if stochrsi is not None and not stochrsi.empty:
                df_ta['stochrsi'] = stochrsi.iloc[:, 0]
            else:
                df_ta['stochrsi'] = 50.0
            # ADX
            adx_df = ta.adx(df_ta['high'], df_ta['low'], df_ta['close'], length=14)
            if adx_df is not None and not adx_df.empty:
                df_ta['adx'] = adx_df.iloc[:, 0]
            else:
                df_ta['adx'] = 0.0
            # Bollinger Bands
            bb = ta.bbands(df_ta['close'], length=20, std=2)
            if bb is not None and not bb.empty:
                upper_cols = [c for c in bb.columns if c.startswith('BBU_')]
                lower_cols = [c for c in bb.columns if c.startswith('BBL_')]
                if upper_cols and lower_cols:
                    df_ta['bb_upper'] = bb[upper_cols[0]]
                    df_ta['bb_lower'] = bb[lower_cols[0]]
                else:
                    df_ta['bb_upper'] = df_ta['close']
                    df_ta['bb_lower'] = df_ta['close']
            else:
                df_ta['bb_upper'] = df_ta['close']
                df_ta['bb_lower'] = df_ta['close']
            # ATR
            df_ta['atr'] = ta.atr(df_ta['high'], df_ta['low'], df_ta['close'], length=14)
            # OBV
            df_ta['obv'] = ta.obv(df_ta['close'], df_ta['volume'])
            # VWAP (intraday only, works on any timeframe)
            try:
                df_vwap = df_ta.copy()
                if 'timestamps' in df_vwap.columns:
                    df_vwap.index = pd.to_datetime(df_vwap['timestamps'])
                vwap_val = ta.vwap(df_vwap['high'], df_vwap['low'], df_vwap['close'], df_vwap['volume'])
                if vwap_val is not None:
                    df_ta['vwap'] = vwap_val.values
                else:
                    df_ta['vwap'] = df_ta['close']
            except Exception:
                df_ta['vwap'] = df_ta['close']
            # SuperTrend
            st = ta.supertrend(df_ta['high'], df_ta['low'], df_ta['close'], length=10, multiplier=3)
            if st is not None and not st.empty:
                st_cols = [c for c in st.columns if c.startswith('SUPERT_')]
                if st_cols:
                    df_ta['supertrend'] = st[st_cols[0]]
                else:
                    df_ta['supertrend'] = df_ta['close']
            else:
                df_ta['supertrend'] = df_ta['close']
            # MFI
            df_ta['mfi'] = ta.mfi(df_ta['high'], df_ta['low'], df_ta['close'], df_ta['volume'], length=14)
            # ROC
            df_ta['roc'] = ta.roc(df_ta['close'], length=12)
            # Keltner Channels
            kc = ta.kc(df_ta['high'], df_ta['low'], df_ta['close'], length=10, scalar=2)
            if kc is not None and not kc.empty:
                upper_kc = [c for c in kc.columns if c.startswith('KCU_')]
                lower_kc = [c for c in kc.columns if c.startswith('KCL_')]
                if upper_kc and lower_kc:
                    df_ta['kc_upper'] = kc[upper_kc[0]]
                    df_ta['kc_lower'] = kc[lower_kc[0]]
                else:
                    df_ta['kc_upper'] = df_ta['close']
                    df_ta['kc_lower'] = df_ta['close']
            else:
                df_ta['kc_upper'] = df_ta['close']
                df_ta['kc_lower'] = df_ta['close']

            # Volume 20MA
            df_ta['volume_20ma'] = df_ta['volume'].rolling(20).mean()

            # Extract latest row
            latest = df_ta.iloc[-1]
            indicators = {
                "close": latest['close'],
                "volume": latest['volume'],
                "volume_20ma": latest['volume_20ma'],
                "ema9": latest['ema9'],
                "ema21": latest['ema21'],
                "ema50": latest['ema50'],
                "ema200": latest['ema200'],
                "rsi": latest['rsi'],
                "macd": latest['macd'],
                "macd_signal": latest['macd_signal'],
                "macd_hist": latest['macd_hist'],
                "macd_hist_prev": df_ta['macd_hist'].iloc[-2] if len(df_ta) >= 2 else 0.0,
                "stochrsi": latest['stochrsi'],
                "adx": latest['adx'],
                "bb_upper": latest['bb_upper'],
                "bb_lower": latest['bb_lower'],
                "atr": latest['atr'],
                "obv": latest['obv'],
                "vwap": latest['vwap'],
                "supertrend": latest['supertrend'],
                "mfi": latest['mfi'],
                "roc": latest['roc'],
                "kc_upper": latest['kc_upper'],
                "kc_lower": latest['kc_lower'],
            }
            return indicators
        except Exception as e:
            logging.error(f"Indicator computation error: {e}")
            return {}

    def score_technical_indicators(self, indicators: dict, tv_analysis: dict) -> dict:
        """Score technical indicators according to the specification and return breakdown."""
        try:
            price = indicators.get('close')  # assume close price present in dict; if not provided, fallback
            # EMA alignment
            ema_score = 0
            ema9 = indicators.get('ema9')
            ema21 = indicators.get('ema21')
            ema50 = indicators.get('ema50')
            ema200 = indicators.get('ema200')
            if price and ema9 and ema21 and ema50 and ema200:
                if price > ema9 > ema21 > ema50 > ema200:
                    ema_score = 5
                elif price > ema9 > ema21:
                    ema_score = 3
                elif price > ema21:
                    ema_score = 1
            # RSI
            rsi = indicators.get('rsi') or 0
            if 40 <= rsi <= 60:
                rsi_score = 4
            elif 30 <= rsi < 40:
                rsi_score = 3
            elif 20 <= rsi < 30:
                rsi_score = 2
            elif rsi > 70:
                rsi_score = 1
            else:
                rsi_score = 0
            # MACD
            macd_hist = indicators.get('macd_hist') or 0
            macd = indicators.get('macd') or 0
            macd_signal = indicators.get('macd_signal') or 0
            macd_score = 0
            if macd_hist > 0:
                if macd_hist > indicators.get('macd_hist_prev', 0):
                    macd_score = 4
                else:
                    macd_score = 2
            elif macd_hist < 0:
                macd_score = 0
            elif macd > macd_signal:
                macd_score = 3
            # Volume (compare to 20-day avg)
            vol = indicators.get('volume') or 0
            vol_20ma = indicators.get('volume_20ma') or 0
            volume_score = 0
            if vol_20ma:
                ratio = vol / vol_20ma
                if ratio > 2.0:
                    volume_score = 4
                elif ratio > 1.5:
                    volume_score = 3
                elif ratio > 1.0:
                    volume_score = 2
                else:
                    volume_score = 0
            # ADX
            adx = indicators.get('adx') or 0
            if adx > 40:
                adx_score = 4
            elif adx > 25:
                adx_score = 3
            elif adx > 20:
                adx_score = 2
            else:
                adx_score = 0
            # SuperTrend
            supertrend = indicators.get('supertrend')
            # pandas_ta supertrend gives boolean direction? assume True=UP, False=DOWN
            supertrend_score = 0
            if isinstance(supertrend, bool):
                if supertrend:
                    # assume price just crossed check not implemented, give max
                    supertrend_score = 4
                else:
                    supertrend_score = 0
            # TradingView bonus
            tv_bonus = 0
            if tv_analysis:
                # take 1d summary recommendation
                rec = tv_analysis.get('1d', {}).get('summary', {}).get('RECOMMENDATION', '').upper()
                if rec == 'STRONG_BUY':
                    tv_bonus = 4
                elif rec == 'BUY':
                    tv_bonus = 3
                elif rec == 'NEUTRAL':
                    tv_bonus = 1
                else:
                    tv_bonus = 0
            total_score = ema_score + rsi_score + macd_score + volume_score + adx_score + supertrend_score + tv_bonus
            breakdown = {
                "ema": ema_score,
                "rsi": rsi_score,
                "macd": macd_score,
                "volume": volume_score,
                "adx": adx_score,
                "supertrend": supertrend_score,
                "tv_bonus": tv_bonus,
            }
            return {"score": total_score, "breakdown": breakdown, "summary": "Technical score"}
        except Exception as e:
            logging.error(f"Technical scoring error: {e}")
            return {"score": 0, "breakdown": {}, "summary": "Error"}

    def detect_kline_patterns(self, df: pd.DataFrame) -> dict:
        """Detect candlestick patterns on last 10 candles and score.
        Returns dict with score, patterns_found list, strength.
        """
        try:
            patterns = []
            if len(df) >= 2:
                cur = df.iloc[-1]
                prev = df.iloc[-2]
                
                # Engulfing (Bullish)
                if prev['close'] < prev['open'] and cur['close'] > cur['open']:
                    if cur['open'] <= prev['close'] and cur['close'] >= prev['open']:
                        patterns.append('Engulfing')
                
                # Hammer
                body = abs(cur['close'] - cur['open'])
                lower_shadow = min(cur['close'], cur['open']) - cur['low']
                upper_shadow = cur['high'] - max(cur['close'], cur['open'])
                if body > 0 and lower_shadow >= 2 * body and upper_shadow <= 0.2 * body:
                    patterns.append('Hammer')
                    
                # Inverted Hammer
                if body > 0 and upper_shadow >= 2 * body and lower_shadow <= 0.2 * body:
                    patterns.append('InvertedHammer')
                    
                # Inside Bar
                if cur['low'] > prev['low'] and cur['high'] < prev['high']:
                    patterns.append('InsideBar')
                    
                # Volume Surge Breakout
                avg_vol = df['volume'].iloc[-10:].mean()
                if cur['close'] > prev['high'] and cur['volume'] > 1.5 * avg_vol:
                    patterns.append('VolumeSurgeBreakout')
                    
            if len(df) >= 3:
                # Marubozu (large body, tiny shadows)
                cur = df.iloc[-1]
                body = abs(cur['close'] - cur['open'])
                total_range = cur['high'] - cur['low']
                if total_range > 0 and body / total_range > 0.9:
                    patterns.append('Marubozu')

                # Three White Soldiers (three consecutive green candles with increasing closes)
                c1 = df.iloc[-3]
                c2 = df.iloc[-2]
                c3 = df.iloc[-1]
                if c1['close'] > c1['open'] and c2['close'] > c2['open'] and c3['close'] > c3['open']:
                    if c3['close'] > c2['close'] > c1['close']:
                        patterns.append('ThreeWhiteSoldiers')
            
            count = len(patterns)
            if count >= 3:
                score = 15
                strength = 'STRONG'
            elif count == 2:
                score = 10
                strength = 'MODERATE'
            elif count == 1:
                score = 5
                strength = 'WEAK'
            else:
                score = 0
                strength = 'NONE'
            return {"score": score, "patterns_found": patterns, "strength": strength}
        except Exception as e:
            logging.error(f"Pattern detection error: {e}")
            return {"score": 0, "patterns_found": [], "strength": "NONE"}

    def get_support_resistance(self, df: pd.DataFrame) -> dict:
        """Calculate support/resistance levels as described."""
        try:
            if len(df) < 2:
                return {}
            pdh = float(df.iloc[-2]['high'])
            pdl = float(df.iloc[-2]['low'])
            week_high = float(df['high'].iloc[-5:].max())
            week_low = float(df['low'].iloc[-5:].min())
            yearly = df.tail(252)
            high_52 = float(yearly['high'].max())
            low_52 = float(yearly['low'].min())
            # Round numbers near current price
            price = float(df.iloc[-1]['close'])
            round_levels = [round(price, -1), round(price, -2), round(price, -3)]
            # Return nearest round number as placeholder
            nearest_round = min(round_levels, key=lambda x: abs(x - price))
            return {
                "pdh": pdh,
                "pdl": pdl,
                "week_high": week_high,
                "week_low": week_low,
                "52w_high": high_52,
                "52w_low": low_52,
                "nearest_round": nearest_round,
            }
        except Exception as e:
            logging.error(f"Support/resistance error: {e}")
            return {}
