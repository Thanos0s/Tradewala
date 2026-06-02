import unittest
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.news_analyzer import NewsAnalyzer

class TestNewsAnalyzerFilter(unittest.TestCase):
    def setUp(self):
        self.analyzer = NewsAnalyzer()

    def test_filter_credible_news(self):
        now = datetime.now(timezone.utc)
        news_data = [
            # Fresh & Credible
            {
                "headline": "TCS earnings rise",
                "summary": "TCS reports stellar Q4",
                "timestamp": now.isoformat(),
                "source": "Moneycontrol"
            },
            # Stale article (>24 hours)
            {
                "headline": "Reliance hits record high",
                "summary": "Reliance shares rally",
                "timestamp": (now - timedelta(hours=26)).isoformat(),
                "source": "NSE"
            },
            # Fresh but not from highly trusted source
            {
                "headline": "Infosys expands team",
                "summary": "Infosys hires 1000 grads",
                "timestamp": now.isoformat(),
                "source": "Random Blog"
            }
        ]
        
        filtered = self.analyzer.filter_credible_news(news_data)
        self.assertEqual(len(filtered), 2)
        
        # Check credibility boost (Moneycontrol gets 1.2, Random Blog gets 1.0)
        tcs_article = [a for a in filtered if "TCS" in a["headline"]][0]
        infy_article = [a for a in filtered if "Infosys" in a["headline"]][0]
        
        self.assertEqual(tcs_article["credibility_multiplier"], 1.2)
        self.assertEqual(infy_article["credibility_multiplier"], 1.0)

    def test_analyze_bypass_trigger(self):
        # Mocks news with only TCS mentioned
        now = datetime.now(timezone.utc)
        news_data = [
            {
                "headline": "TCS hits record high",
                "summary": "TCS shares surge",
                "timestamp": now.isoformat(),
                "source": "NSE"
            }
        ]
        
        watchlist = ["TCS.NS", "INFY.NS", "RELIANCE.NS"]
        # Since we bypass LLM in testing (no live server check here or defaults to keyword fallback),
        # analyze will run keyword engine on triggered (TCS.NS) and bypass INFY/RELIANCE
        results = self.analyzer.analyze(news_data, watchlist)
        
        self.assertIn("TCS.NS", results)
        self.assertIn("INFY.NS", results)
        self.assertIn("RELIANCE.NS", results)
        
        # INFY and RELIANCE should be exactly neutral (50) and bypassed
        self.assertEqual(results["INFY.NS"]["sentiment_score"], 50)
        self.assertEqual(results["RELIANCE.NS"]["sentiment_score"], 50)
        self.assertEqual(results["INFY.NS"]["catalyst_strength"], "NONE")

if __name__ == "__main__":
    unittest.main()
