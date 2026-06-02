import logging
import pandas as pd
import yfinance as yf
import pandas_ta as ta

logger = logging.getLogger(__name__)

class RegimeFilter:
    """Classifies the overall market regime using India VIX, Nifty 50 moving averages, and Put-Call Ratio."""
    
    def __init__(self):
        logger.info("RegimeFilter initialized")
        
    def fetch_nifty_index_data(self) -> pd.DataFrame:
        """Fetch historical daily data for Nifty 50 index (^NSEI)."""
        try:
            ticker = yf.Ticker("^NSEI")
            df = ticker.history(period="100d", interval="1d")
            if df.empty:
                raise ValueError("Nifty index history is empty")
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            return df
        except Exception as e:
            logger.error(f"Failed to fetch Nifty index data: {e}")
            return pd.DataFrame()

    def get_market_regime(self, fo_result: dict) -> dict:
        """Analyze indicators and return consolidated market regime.
        Outcomes: BULL_MARKET, BEAR_MARKET, SIDEWAYS, VOLATILE
        """
        try:
            # 1. Fetch India VIX (fear gauge)
            vix_level = 15.0
            try:
                vix_df = yf.Ticker("^INDIAVIX").history(period="1d")
                if not vix_df.empty:
                    vix_level = float(vix_df["Close"].iloc[-1])
            except Exception as e:
                logger.warning(f"Could not fetch India VIX: {e}")

            # 2. Fetch Nifty 50 Index trend (crossover)
            nifty_trend = "NEUTRAL"
            nifty_close = 0.0
            adx_level = 15.0  # default sideways
            nifty_df = self.fetch_nifty_index_data()
            if not nifty_df.empty:
                nifty_close = float(nifty_df["close"].iloc[-1])
                ema50 = ta.ema(nifty_df["close"], length=50)
                if ema50 is not None and not nifty_df.empty:
                    latest_ema50 = float(ema50.iloc[-1])
                    nifty_trend = "BULLISH" if nifty_close > latest_ema50 else "BEARISH"
                
                # ADX calculation
                adx_df = ta.adx(nifty_df["high"], nifty_df["low"], nifty_df["close"], length=14)
                if adx_df is not None and not adx_df.empty:
                    adx_level = float(adx_df.iloc[-1, 0])
            
            # 3. PCR from F&O results
            pcr_valid = fo_result.get("nifty_pcr_valid", True)
            pcr = fo_result.get("nifty_pcr", 1.0)
            if not pcr_valid or pcr is None or pcr <= 0:
                logger.warning("PCR is unavailable or invalid; using neutral fallback of 1.0 for regime analysis.")
                pcr = 1.0
            
            # 4. Consolidate regime rules
            if vix_level > 21.0:
                regime = "VOLATILE"
                action_rule = "RESTRICT_SWING_AND_HIGH_RISK"
                reason = f"India VIX is elevated at {vix_level:.2f} signaling high volatility."
            elif adx_level > 25.0:
                # Strong trend detected
                if nifty_trend == "BEARISH":
                    regime = "BEAR_MARKET"
                    action_rule = "INCREASE_CONFIDENCE_THRESHOLD"
                    reason = f"Nifty strongly trending downwards (ADX: {adx_level:.1f})."
                else:
                    regime = "BULL_MARKET"
                    action_rule = "ALLOW_ALL"
                    reason = f"Nifty strongly trending upwards (ADX: {adx_level:.1f})."
            elif pcr < 0.70 or (nifty_trend == "BEARISH" and pcr < 0.85):
                regime = "BEAR_MARKET"
                action_rule = "INCREASE_CONFIDENCE_THRESHOLD"
                reason = f"Nifty trend is {nifty_trend} and PCR is bearish ({pcr:.2f})."
            elif nifty_trend == "BULLISH" and 0.85 <= pcr <= 1.4:
                regime = "BULL_MARKET"
                action_rule = "ALLOW_ALL"
                reason = f"Nifty index is above 50-day EMA and PCR is healthy ({pcr:.2f})."
            else:
                regime = "SIDEWAYS"
                action_rule = "FAVOR_INTRADAY"
                reason = f"VIX ({vix_level:.2f}), PCR ({pcr:.2f}), ADX ({adx_level:.1f}) are range-bound."
                
            logger.info(f"Consolidated Market Regime: {regime} | Rule: {action_rule}")
            return {
                "regime": regime,
                "action_rule": action_rule,
                "vix": vix_level,
                "nifty_close": nifty_close,
                "nifty_trend": nifty_trend,
                "pcr": pcr,
                "pcr_valid": pcr_valid,
                "adx": adx_level,
                "reason": reason
            }
        except Exception as e:
            logger.error(f"Error calculating market regime: {e}")
            return {
                "regime": "SIDEWAYS",
                "action_rule": "ALLOW_ALL",
                "vix": 15.0,
                "nifty_close": 0.0,
                "nifty_trend": "NEUTRAL",
                "pcr": 1.0,
                "pcr_valid": False,
                "reason": f"Fallback due to regime filter exception: {e}"
            }
            
    def apply_regime_filtering(self, scored_stocks: list, regime_info: dict) -> list:
        """Filter out scored stocks based on the current market regime rules."""
        action_rule = regime_info.get("action_rule", "ALLOW_ALL")
        filtered = []
        
        for stock in scored_stocks:
            cat = stock.get("trade_category", "SKIP")
            if cat == "SKIP":
                continue
                
            score = stock.get("total_score", 0.0)
            
            # Apply regime overrides
            if action_rule == "RESTRICT_SWING_AND_HIGH_RISK":
                # In volatile markets, only allow Intraday trades and high score filters
                if cat in ("SWING", "HIGH_RISK_HIGH_REWARD"):
                    stock["trade_category"] = "SKIP"
                    logger.info(f"[{stock['symbol']}] Filtered out {cat} due to High Volatility regime.")
                    continue
                elif score < 65:
                    # Stricter score hurdle for intraday
                    stock["trade_category"] = "SKIP"
                    continue
            elif action_rule == "INCREASE_CONFIDENCE_THRESHOLD":
                # In bearish markets, raise minimum score requirement for entry
                if score < 60:
                    stock["trade_category"] = "SKIP"
                    logger.info(f"[{stock['symbol']}] Filtered out because score {score} is below Bear Market minimum of 60.")
                    continue
            elif action_rule == "FAVOR_INTRADAY":
                # In sideways markets, downgrade High Risk to skip and only take premium swing/intraday
                if cat == "HIGH_RISK_HIGH_REWARD":
                    stock["trade_category"] = "SKIP"
                    continue
                elif cat == "SWING" and score < 55:
                    stock["trade_category"] = "SKIP"
                    continue
                    
            filtered.append(stock)
            
        return filtered
