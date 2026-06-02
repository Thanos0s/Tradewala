import logging
import math
from datetime import datetime
from .indicators import IndicatorEngine
from .news_analyzer import NewsAnalyzer
from .fo_analyzer import FOAnalyzer
from config import SCORING_WEIGHTS, MIN_CONFIDENCE_SCORE, ADAPTIVE_SCORING_WEIGHTS, NEWS_DECAY_HALFLIFE_HOURS

class ScoringEngine:
    """Combines all signals into a final score (0-100) and trade recommendation."""

    def __init__(self, indicator_engine: IndicatorEngine, news_analyzer: NewsAnalyzer, fo_analyzer: FOAnalyzer):
        self.indicator_engine = indicator_engine
        self.news_analyzer = news_analyzer
        self.fo_analyzer = fo_analyzer
        from .xgboost_model import XGBoostPredictor
        self.xgb_predictor = XGBoostPredictor()
        logging.info("ScoringEngine initialized")

    def score_stock(self, symbol: str, kronos_result: dict, df: dict, news_result: dict, fo_result: dict, ban_list: list, regime_info: dict = None, news_data: list = None, global_modifiers: dict = None) -> dict:
        """Score a stock according to the spec.
        Returns full dict with component scores, conflict tags, reasons, and recommendation.
        """
        if symbol in ban_list:
            logging.info(f"{symbol} is in F&O ban list – skipping")
            return None

        # Determine market regime and weights
        regime = "SIDEWAYS"
        if regime_info and isinstance(regime_info, dict):
            r = regime_info.get("regime", "SIDEWAYS")
            if r in ("BULL_MARKET", "BEAR_MARKET"):
                regime = "TRENDING"
            elif r in ("SIDEWAYS", "VOLATILE"):
                regime = r
                
        weights = ADAPTIVE_SCORING_WEIGHTS.get(regime, ADAPTIVE_SCORING_WEIGHTS["SIDEWAYS"])
        
        kronos_w = weights.get("kronos_forecast", 30)
        xgb_w = weights.get("xgboost_forecast", 15)
        tech_w = weights.get("technical_indicators", 15)
        news_w = weights.get("news_sentiment", 25)
        fo_w = weights.get("fo_signals", 10)
        pattern_w = weights.get("kline_patterns", 5)

        # ── Time Decay Model ─────────────────────────────────────────────────
        decay_factor = 1.0
        latest_article_time = None
        symbol_news = news_result.get(symbol, {})
        headlines = symbol_news.get('relevant_headlines', [])
        
        if news_data and headlines:
            for hl in headlines:
                hl_lower = hl.lower().strip()
                for article in news_data:
                    art_hl = article.get('headline', '').lower().strip()
                    if hl_lower in art_hl or art_hl in hl_lower:
                        ts_str = article.get('timestamp')
                        if ts_str:
                            try:
                                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                if latest_article_time is None or dt > latest_article_time:
                                    latest_article_time = dt
                            except Exception:
                                pass
        
        if latest_article_time:
            try:
                # Use timezone-aware comparison if possible
                now = datetime.now(latest_article_time.tzinfo)
                age_seconds = (now - latest_article_time).total_seconds()
                news_age_hours = max(0.0, age_seconds / 3600.0)
                decay_constant = NEWS_DECAY_HALFLIFE_HOURS / 0.693147
                decay_factor = math.exp(-news_age_hours / decay_constant)
                if news_age_hours > 6.0:
                    decay_factor = 0.0
            except Exception as e:
                logging.warning(f"Error calculating news time decay: {e}")

        # ── Kronos score (0 to kronos_w pts) ──────────────────────────────────
        pct = kronos_result.get('predicted_change_pct', 0)
        mode = kronos_result.get('mode', 'FALLBACK_EMA')
        if pct >= 3:
            kronos_raw = 40
        elif pct >= 2:
            kronos_raw = 32
        elif pct >= 1:
            kronos_raw = 24
        elif pct >= 0.5:
            kronos_raw = 16
        elif pct >= 0:
            kronos_raw = 8
        else:
            kronos_raw = 0
            
        kronos_norm = kronos_raw / 40.0
        if 'KRONOS_AI' in mode:
            conf = kronos_result.get('kronos_confidence', 50) / 100.0
            kronos_score = kronos_w * kronos_norm * (0.6 + 0.4 * conf)
        else:
            kronos_score = kronos_w * kronos_norm * 0.6

        # ── XGBoost score (0 to xgb_w pts) ───────────────────────────────────
        xgb_prob = self.xgb_predictor.predict_probability(df)
        xgb_score = xgb_prob * xgb_w

        # ── Technical indicators (0 to tech_w pts) ───────────────────────────
        tech_ind = self.indicator_engine.compute_all_indicators(df)
        tv_analysis = self.indicator_engine.get_tradingview_analysis(symbol)
        tech_score_dict = self.indicator_engine.score_technical_indicators(tech_ind, tv_analysis)
        technical_raw = tech_score_dict.get('score', 0)
        technical_score = (technical_raw / 29.0) * tech_w

        # ── News sentiment (0 to news_w pts, with Time Decay) ────────────────
        news_raw = symbol_news.get('sentiment_score', 50)
        decayed_news_raw = 50.0 + (news_raw - 50.0) * decay_factor
        news_score = (decayed_news_raw / 100.0) * news_w

        # ── F&O signals (0 to fo_w pts) ──────────────────────────────────────
        pcr = fo_result.get('nifty_pcr', 1.0)
        if pcr > 1.2:
            fo_raw = 10
        elif pcr > 1.0:
            fo_raw = 7
        elif pcr >= 0.8:
            fo_raw = 4
        else:
            fo_raw = 1
        fo_score = (fo_raw / 10.0) * fo_w

        # ── Pattern score (0 to pattern_w pts) ───────────────────────────────
        pattern_dict = self.indicator_engine.detect_kline_patterns(df)
        pattern_raw = pattern_dict.get('score', 0)
        pattern_score = (pattern_raw / 15.0) * pattern_w

        total_score = kronos_score + xgb_score + technical_score + news_score + fo_score + pattern_score

        # Apply Global Impact Engine Modifiers
        global_reasons = []
        if global_modifiers:
            # General EM market pressure modifier
            gen_mod = global_modifiers.get("general_modifier", 0.0)
            total_score += gen_mod
            if gen_mod > 0:
                global_reasons.append("Supported by positive global macro flows (EM relief)")
            elif gen_mod < 0:
                global_reasons.append("Pressured by strong US Dollar Index (capital outflow)")
            
            # Sector specific modifier
            sector_mods = global_modifiers.get("sector_modifiers", {})
            symbol_upper = symbol.upper()
            
            if "IT" in sector_mods and any(kw in symbol_upper for kw in ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "OFSS", "PERSISTENT", "LTIM"]):
                sec_mod = sector_mods["IT"]
                total_score += sec_mod
                if sec_mod > 0:
                    global_reasons.append("Thematic tailwind: Nasdaq tech strength")
                elif sec_mod < 0:
                    global_reasons.append("Thematic headwind: Nasdaq tech weakness")
            elif "Chemicals" in sector_mods and any(kw in symbol_upper for kw in ["CLEAN", "FINEORG", "NAVINFLUOR", "FLUOROCHEM", "NOCIL", "DEEPAKNTR", "TATACHEM", "ATUL", "SUDARSCHEM", "VINATIORGA", "ROSSARI", "HIMADRI"]):
                sec_mod = sector_mods["Chemicals"]
                total_score += sec_mod
                if sec_mod > 0:
                    global_reasons.append("Thematic tailwind: Weak Chinese competitor outputs")
            elif "Gold" in sector_mods and "GOLD" in symbol_upper:
                sec_mod = sector_mods["Gold"]
                total_score += sec_mod
                if sec_mod > 0:
                    global_reasons.append("Thematic tailwind: Gold futures rally")

        # ── Smart Conflict Engine ────────────────────────────────────────────
        conflict_tag = "NEUTRAL"
        news_normalized = decayed_news_raw
        tech_normalized_pct = (technical_raw / 29.0) * 100.0
        
        if news_normalized >= 70 and tech_normalized_pct >= 70:
            conflict_tag = "HIGH CONFIDENCE"
        elif news_normalized >= 75 and tech_normalized_pct < 50:
            conflict_tag = "EARLY BREAKOUT"
        elif tech_normalized_pct >= 75 and news_normalized < 55:
            conflict_tag = "TECHNICAL ONLY"

        # ── Explainable AI ───────────────────────────────────────────────────
        reasons = []
        if kronos_result.get('kronos_direction') == "UP":
            reasons.append("Kronos model predicts short-term upward trend")
        if xgb_prob >= 0.55:
            reasons.append(f"XGBoost classifier predicts positive close probability of {xgb_prob*100:.1f}%")
        
        tech_breakdown = tech_score_dict.get('breakdown', {})
        if tech_breakdown.get('ema') == 5:
            reasons.append("Perfect bullish alignment of moving averages (9 > 21 > 50 > 200)")
        elif tech_breakdown.get('ema') == 3:
            reasons.append("Short-term EMAs aligned bullishly (Price > 9 > 21)")
            
        rsi_val = tech_ind.get('rsi', 50)
        if 40 <= rsi_val <= 60:
            reasons.append(f"RSI is in a healthy momentum zone ({rsi_val:.1f})")
            
        if tech_breakdown.get('macd') == 4:
            reasons.append("MACD histogram shows accelerating bullish momentum")
            
        vol_20ma = tech_ind.get('volume_20ma', 1.0)
        if vol_20ma > 0:
            vol_ratio = tech_ind.get('volume', 0) / vol_20ma
            if vol_ratio >= 1.5:
                reasons.append(f"Strong volume surge ({vol_ratio:.1f}x of 20MA)")
            
        if pattern_dict.get('patterns_found'):
            found_pats = ", ".join(pattern_dict['patterns_found'])
            reasons.append(f"Candlestick patterns detected: {found_pats}")
            
        if decayed_news_raw >= 70:
            reasons.append("Highly positive news sentiment detected")
            if news_raw >= 70 and decayed_news_raw < news_raw:
                reasons.append("Note: Sentiment partially decayed over time")
        elif decayed_news_raw <= 30:
            reasons.append("Negative news sentiment detected")
            
        if pcr > 1.2:
            reasons.append(f"High market Put-Call Ratio ({pcr:.2f}) indicates bullish options build-up")

        reasons.extend(global_reasons)

        # Determine trade category
        trade_category = "SKIP"
        if symbol_news.get('catalyst_strength') == "STRONG" and kronos_result.get('kronos_direction') == "UP" and pattern_dict.get('strength') == "STRONG" and xgb_prob >= 0.60:
            trade_category = "HIGH_RISK_HIGH_REWARD"
        elif total_score >= 60 and kronos_result.get('kronos_direction') == "UP" and xgb_prob >= 0.55:
            trade_category = "INTRADAY"
        elif total_score >= 55 and xgb_prob >= 0.52:
            trade_category = "SWING"

        # Entry/target/SL calculations (using ATR)
        try:
            atr = tech_ind.get('atr', 0)
        except Exception:
            atr = 0
        entry = kronos_result.get('current_price', 0)
        if trade_category == "INTRADAY":
            target = entry + 2 * atr
            stop = entry - atr
        elif trade_category == "HIGH_RISK_HIGH_REWARD":
            target = entry * 1.10
            stop = entry * 0.97
        elif trade_category == "SWING":
            target = entry * 1.20
            stop = entry * 0.93
        else:
            target = stop = None

        return {
            "symbol": symbol,
            "component_scores": {
                "kronos": round(kronos_score, 2),
                "xgboost": round(xgb_score, 2),
                "technical": round(technical_score, 2),
                "news": round(news_score, 2),
                "fo": round(fo_score, 2),
                "patterns": round(pattern_score, 2),
            },
            "xgb_probability": round(xgb_prob * 100, 1),
            "total_score": round(total_score, 1),
            "trade_category": trade_category,
            "entry": entry,
            "target": target,
            "stop_loss": stop,
            "conflict_tag": conflict_tag,
            "explainable_reasons": reasons,
            "technical_indicators": tech_ind,  # Pass indicators along for Risk Engine check
        }


    def rank_stocks(self, scored_stocks: list) -> dict:
        """Sort by total_score and split into buckets with diversification rules."""
        sorted_stocks = sorted(scored_stocks, key=lambda x: x['total_score'], reverse=True)
        intraday = []
        high_risk = []
        swing = []
        sectors_used = set()
        
        for stock in sorted_stocks:
            cat = stock['trade_category']
            sector = stock['symbol'].split('.')[0]
            if sector in sectors_used:
                continue
                
            if cat == "INTRADAY" and len(intraday) < 3:
                intraday.append(stock)
                sectors_used.add(sector)
            elif cat == "HIGH_RISK_HIGH_REWARD" and len(high_risk) < 2:
                high_risk.append(stock)
                sectors_used.add(sector)
            elif cat == "SWING" and len(swing) < 3:
                swing.append(stock)
                sectors_used.add(sector)
                
        # Fallback disabled per user request: if no stock qualifies, return empty lists to prioritize accuracy.
        
        return {
            "intraday_picks": intraday,
            "high_risk_picks": high_risk,
            "swing_picks": swing,
        }
