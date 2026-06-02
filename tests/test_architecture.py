import unittest
import pandas as pd
import numpy as np
from analysis.regime_filter import RegimeFilter
from analysis.risk_manager import RiskManager
from analysis.xgboost_model import XGBoostPredictor, prepare_features

class TestArchitectureComponents(unittest.TestCase):

    def test_regime_filter_classification(self):
        filter_engine = RegimeFilter()
        
        # Test case 1: Bullish PCR and neutral VIX
        bull_regime = filter_engine.get_market_regime({"nifty_pcr": 1.1})
        self.assertIn("regime", bull_regime)
        self.assertIn(bull_regime["regime"], ["BULL_MARKET", "SIDEWAYS"])  # depending on fetched VIX/Nifty trend

        # Test case 2: Bearish PCR
        bear_regime = filter_engine.get_market_regime({"nifty_pcr": 0.6})
        self.assertEqual(bear_regime["regime"], "BEAR_MARKET")
        self.assertEqual(bear_regime["action_rule"], "INCREASE_CONFIDENCE_THRESHOLD")

    def test_regime_filtering_rules(self):
        filter_engine = RegimeFilter()
        scored_stocks = [
            {"symbol": "TCS.NS", "total_score": 75, "trade_category": "INTRADAY"},
            {"symbol": "INFY.NS", "total_score": 55, "trade_category": "SWING"},
            {"symbol": "RELIANCE.NS", "total_score": 58, "trade_category": "HIGH_RISK_HIGH_REWARD"}
        ]
        
        # Volatile Regime filters out Swing and High Risk
        filtered = filter_engine.apply_regime_filtering(scored_stocks, {"regime": "VOLATILE", "action_rule": "RESTRICT_SWING_AND_HIGH_RISK"})
        # Only TCS.NS (Intraday with score >= 65) should remain
        symbols = [s["symbol"] for s in filtered]
        self.assertIn("TCS.NS", symbols)
        self.assertNotIn("INFY.NS", symbols)
        self.assertNotIn("RELIANCE.NS", symbols)

    def test_risk_manager_position_sizing(self):
        # 100,000 Equity, 1.5% Risk = 1,500 Risk Budget
        # Entry 100, Stop 95 -> Loss per share = 5
        # Position size = 1500 / 5 = 300 shares
        # Capital required = 300 * 100 = 30,000 (which is 30% of portfolio)
        # Cap is 20% of account = 20,000 max capital.
        # Adjusted shares = 200 shares.
        
        manager = RiskManager(account_equity=100000.0, risk_per_trade_pct=1.5, max_trade_allocation_pct=20.0)
        size_info = manager.calculate_position_size(entry=100.0, stop_loss=95.0)
        
        self.assertEqual(size_info["shares"], 200)
        self.assertEqual(size_info["allocated_capital"], 20000.0)
        self.assertEqual(size_info["pct_of_account"], 20.0)
        self.assertEqual(size_info["risk_amount"], 1000.0)  # 200 shares * 5 loss

    def test_risk_manager_sector_diversification(self):
        manager = RiskManager(account_equity=100000.0, max_sector_exposure=1)
        
        # TCS and INFY are both IT. With max_sector_exposure=1, only one should be allocated.
        ranked_picks = {
            "intraday_picks": [
                {"symbol": "TCS.NS", "total_score": 80, "entry": 3000.0, "stop_loss": 2900.0},
                {"symbol": "INFY.NS", "total_score": 75, "entry": 1500.0, "stop_loss": 1450.0}
            ],
            "high_risk_picks": [],
            "swing_picks": []
        }
        
        allocated = manager.allocate_portfolio(ranked_picks)
        # Only TCS should make it to final picks since it has a higher score
        self.assertEqual(len(allocated["intraday_picks"]), 1)
        self.assertEqual(allocated["intraday_picks"][0]["symbol"], "TCS.NS")

    def test_xgboost_features_preparation(self):
        # Create a dummy DataFrame with OHLCV data
        dates = pd.date_range(start="2023-01-01", periods=250, freq="D")
        np.random.seed(42)
        df = pd.DataFrame({
            "open": np.random.rand(250) * 100 + 100,
            "high": np.random.rand(250) * 100 + 105,
            "low": np.random.rand(250) * 100 + 95,
            "close": np.random.rand(250) * 100 + 100,
            "volume": np.random.randint(1000, 100000, size=250)
        }, index=dates)
        
        prepared = prepare_features(df)
        self.assertFalse(prepared.empty)
        self.assertIn("rsi", prepared.columns)
        self.assertIn("macd_hist", prepared.columns)
        self.assertIn("ema_ratio_9_21", prepared.columns)

if __name__ == "__main__":
    unittest.main()
