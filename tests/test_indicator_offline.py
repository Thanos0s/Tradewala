import unittest

from analysis.indicators import IndicatorEngine


class TestIndicatorOfflineMode(unittest.TestCase):

    def test_offline_mode_returns_neutral_tradingview_analysis(self):
        engine = IndicatorEngine(allow_live_fetch=False)

        analysis = engine.get_tradingview_analysis("RELIANCE.NS")

        self.assertEqual(analysis["1d"]["summary"]["RECOMMENDATION"], "NEUTRAL")
        self.assertEqual(analysis["15m"]["summary"]["RECOMMENDATION"], "NEUTRAL")


if __name__ == "__main__":
    unittest.main()
