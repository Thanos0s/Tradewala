import unittest
import pandas as pd
from unittest.mock import MagicMock
from analysis.indicators import IndicatorEngine
from analysis.news_analyzer import NewsAnalyzer
from analysis.scoring_engine import ScoringEngine

class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.indicator_engine = IndicatorEngine()
        self.news_analyzer = NewsAnalyzer(MagicMock())
        self.fo_analyzer = MagicMock()
        self.scoring_engine = ScoringEngine(
            self.indicator_engine,
            self.news_analyzer,
            self.fo_analyzer
        )

    def test_indicator_computation(self):
        # Create a mock dataframe of 50 rows
        dates = pd.date_range(start="2026-01-01", periods=50)
        df = pd.DataFrame({
            "open": [100.0 + i for i in range(50)],
            "high": [102.0 + i for i in range(50)],
            "low": [98.0 + i for i in range(50)],
            "close": [101.0 + i for i in range(50)],
            "volume": [1000 + i for i in range(50)],
            "timestamps": dates
        })
        
        indicators = self.indicator_engine.compute_all_indicators(df)
        self.assertIn("ema9", indicators)
        self.assertIn("rsi", indicators)
        self.assertIn("macd", indicators)

    def test_detect_kline_patterns(self):
        dates = pd.date_range(start="2026-01-01", periods=5)
        df = pd.DataFrame({
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1000, 1100, 1200, 1300, 1500],
            "timestamps": dates
        })
        patterns = self.indicator_engine.detect_kline_patterns(df)
        self.assertIn("score", patterns)
        self.assertIn("patterns_found", patterns)

    def test_score_stock(self):
        dates = pd.date_range(start="2026-01-01", periods=50)
        df = pd.DataFrame({
            "open": [100.0] * 50,
            "high": [102.0] * 50,
            "low": [98.0] * 50,
            "close": [101.0] * 50,
            "volume": [1000] * 50,
            "timestamps": dates
        })
        kronos_result = {
            "predicted_change_pct": 1.5,
            "kronos_direction": "UP",
            "current_price": 101.0
        }
        news_result = {
            "RELIANCE.NS": {
                "sentiment_score": 75,
                "catalyst_strength": "MODERATE"
            }
        }
        fo_result = {
            "nifty_pcr": 1.1
        }
        
        score_dict = self.scoring_engine.score_stock(
            symbol="RELIANCE.NS",
            kronos_result=kronos_result,
            df=df,
            news_result=news_result,
            fo_result=fo_result,
            ban_list=[]
        )
        self.assertIsNotNone(score_dict)
        self.assertEqual(score_dict["symbol"], "RELIANCE.NS")
        self.assertIn("total_score", score_dict)
        self.assertIn("trade_category", score_dict)

if __name__ == "__main__":
    unittest.main()
