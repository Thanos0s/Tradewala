import os
import argparse
import logging
import math
import pandas as pd
import numpy as np
from datetime import datetime
from data.fetcher import fetch_price_data
from analysis.indicators import IndicatorEngine
from analysis.scoring_engine import ScoringEngine
from analysis.regime_filter import RegimeFilter
from config import NSE_WATCHLIST

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("Backtester")

class Backtester:
    def __init__(self, symbols: list, days: int = 100):
        self.symbols = symbols
        self.days = days
        self.indicator_engine = IndicatorEngine(allow_live_fetch=False) # Skip TV live fetch for speed
        
        # ScoringEngine requires analyzers (we pass placeholders/Mocks since we bypass news scraping)
        self.scoring_engine = ScoringEngine(self.indicator_engine, None, None)
        self.regime_filter = RegimeFilter()
        self.price_data = {}

    def load_data(self):
        """Pre-load price historical data for all symbols."""
        logger.info(f"Loading historical price data for {len(self.symbols)} symbols...")
        # Fetch data (will load from Parquet cache or download if missing)
        self.price_data = fetch_price_data(self.symbols, period="1y")
        logger.info(f"Loaded price data for {len(self.price_data)} symbols.")

    def run(self):
        """Run simulation over the historical period."""
        if not self.price_data:
            self.load_data()

        logger.info(f"Starting historical backtest for last {self.days} days...")
        
        # Gather all unique dates across all symbols
        all_dates = set()
        for df in self.price_data.values():
            if not df.empty and "timestamps" in df.columns:
                all_dates.update(df["timestamps"].tolist())
                
        sorted_dates = sorted(list(all_dates))
        if len(sorted_dates) < self.days + 10:
            self.days = len(sorted_dates) - 15
            logger.warning(f"Not enough historical dates; reducing backtest duration to {self.days} days.")
            
        test_dates = sorted_dates[-self.days-5:-5] # leave last 5 days for trade resolution

        trades = []
        
        # Step day-by-day
        for idx, today in enumerate(test_dates):
            date_str = today.strftime("%Y-%m-%d") if isinstance(today, datetime) else str(today)[:10]
            logger.info(f"Processing day: {date_str} ({idx+1}/{len(test_dates)})")
            
            # Construct historical market data state up to 'today'
            price_state = {}
            for sym, df in self.price_data.items():
                # Slice dataframe up to today
                df_sub = df[df["timestamps"] <= today].copy()
                if len(df_sub) >= 50: # need enough candles for indicators
                    price_state[sym] = df_sub

            if not price_state:
                continue

            # Mock F&O signals for the day (neutral PCR 1.0)
            fo_result = {"nifty_pcr": 1.0, "nifty_pcr_valid": True}
            regime_info = self.regime_filter.get_market_regime(fo_result)
            
            # Mock news result (neutral 50 sentiment for all)
            news_result = {sym: {"sentiment_score": 50, "catalyst_strength": "NONE", "relevant_headlines": []} for sym in price_state.keys()}
            
            scored_stocks = []
            
            # Score each stock historically
            for sym, df_sub in price_state.items():
                # Generate heuristic predictor prediction (mock Kronos AI)
                last_row = df_sub.iloc[-1]
                close = df_sub["close"]
                ma5 = float(close.tail(5).mean())
                ma20 = float(close.tail(20).mean())
                
                # Heuristic predictor matching predictor.py
                if ma5 > ma20:
                    change_pct = round(1.2 + (ma5 / ma20 - 1) * 5, 2)
                    direction = "UP"
                else:
                    change_pct = round(-0.8 - (ma20 / ma5 - 1) * 3, 2)
                    direction = "DOWN"
                change_pct = max(-5.0, min(5.0, change_pct))
                
                kronos_res = {
                    "symbol": sym,
                    "current_price": float(last_row["close"]),
                    "predicted_change_pct": change_pct,
                    "kronos_direction": direction,
                    "mode": "FALLBACK_EMA"
                }
                
                try:
                    # Score
                    res = self.scoring_engine.score_stock(
                        symbol=sym,
                        kronos_result=kronos_res,
                        df=df_sub,
                        news_result=news_result,
                        fo_result=fo_result,
                        ban_list=[],
                        regime_info=regime_info,
                        news_data=[]
                    )
                    if res:
                        # In backtester simulation, we lack real-time news spikes (always neutral 50) and 
                        # run in fallback EMA mode (scaling down Kronos weights by 0.6x). 
                        # We relax thresholds to test the simulation execution, target/SL hit rates, and compounding logic.
                        ts = res.get("total_score", 0)
                        xp = res.get("xgb_probability", 50.0) / 100.0
                        direction = kronos_res.get("kronos_direction")
                        
                        if ts >= 45 and xp >= 0.50:
                            atr = res.get("technical_indicators", {}).get("atr", 0)
                            entry = res.get("entry", 0)
                            if direction == "UP" and xp >= 0.53:
                                res["trade_category"] = "INTRADAY"
                                res["target"] = entry + 2 * atr
                                res["stop_loss"] = entry - atr
                            else:
                                res["trade_category"] = "SWING"
                                res["target"] = entry * 1.20
                                res["stop_loss"] = entry * 0.93
                            scored_stocks.append(res)
                except Exception as e:
                    pass

            if not scored_stocks:
                continue

            # Filter with regime overrides
            filtered_scored = self.regime_filter.apply_regime_filtering(scored_stocks, regime_info)
            picks = self.scoring_engine.rank_stocks(filtered_scored)
            
            # Simulate trade entries and track performance over forward 5 days
            for cat in ["swing_picks", "intraday_picks"]:
                for pick in picks.get(cat, []):
                    symbol = pick["symbol"]
                    entry_price = pick["entry"]
                    target = pick["target"]
                    stop_loss = pick["stop_loss"]
                    
                    # Look forward in the main dataframe to resolve outcome
                    df_full = self.price_data[symbol]
                    df_forward = df_full[df_full["timestamps"] > today].head(5).copy()
                    
                    if df_forward.empty:
                        continue
                        
                    outcome = "EXPIRED"
                    exit_price = df_forward.iloc[-1]["close"]
                    exit_date = df_forward.iloc[-1]["timestamps"]
                    
                    # Check day-by-day if target/SL is hit
                    for f_idx, f_row in df_forward.iterrows():
                        high = f_row["high"]
                        low = f_row["low"]
                        
                        # In simple backtesting, check stop loss first (risk-conservative)
                        if low <= stop_loss:
                            outcome = "STOP_LOSS"
                            exit_price = stop_loss
                            exit_date = f_row["timestamps"]
                            break
                        elif high >= target:
                            outcome = "TARGET"
                            exit_price = target
                            exit_date = f_row["timestamps"]
                            break

                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    trades.append({
                        "symbol": symbol,
                        "date": date_str,
                        "category": cat,
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl_pct": pnl_pct,
                        "outcome": outcome
                    })

        self._print_stats(trades)

    def _print_stats(self, trades: list):
        """Aggregate results and print metrics."""
        print("\n" + "="*80)
        print("                   KRONOS INDIA BACKTEST PERFORMANCE REPORT")
        print("="*80)
        
        total_trades = len(trades)
        print(f"Total Simulated Trades : {total_trades}")
        if total_trades == 0:
            print("No qualifying trades were triggered.")
            return

        df_t = pd.DataFrame(trades)
        wins = df_t[df_t["pnl_pct"] > 0]
        losses = df_t[df_t["pnl_pct"] <= 0]
        
        win_rate = (len(wins) / total_trades) * 100
        avg_ret = df_t["pnl_pct"].mean()
        
        print(f"Win Rate               : {win_rate:.1f}% ({len(wins)} Wins / {len(losses)} Losses)")
        print(f"Average PnL %          : {avg_ret:+.2f}%")
        print(f"Target Hit Rate        : {(len(df_t[df_t['outcome'] == 'TARGET']) / total_trades) * 100:.1f}%")
        print(f"Stop Loss Hit Rate     : {(len(df_t[df_t['outcome'] == 'STOP_LOSS']) / total_trades) * 100:.1f}%")
        
        # Cumulative compounding curve
        cum_ret = 1.0
        for p in df_t["pnl_pct"]:
            cum_ret *= (1 + (p / 100.0))
        compounded_total = (cum_ret - 1.0) * 100
        print(f"Compounded Total PnL   : {compounded_total:+.2f}%")
        
        print("\nBreakdown by Category:")
        cat_stats = df_t.groupby("category")["pnl_pct"].agg(["count", "mean", "min", "max"])
        print(cat_stats.to_string())
        
        print("\nBreakdown by Outcome:")
        outcome_stats = df_t.groupby("outcome")["pnl_pct"].agg(["count", "mean"])
        print(outcome_stats.to_string())
        print("="*80 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kronos India Backtester")
    parser.add_argument("--days", type=int, default=30, help="Number of historical days to test")
    parser.add_argument("--limit", type=int, default=5, help="Number of stocks to evaluate from watchlist")
    args = parser.parse_args()

    # Limit symbols for testing speed
    symbols_to_test = NSE_WATCHLIST[:args.limit]
    backtester = Backtester(symbols_to_test, days=args.days)
    backtester.run()
