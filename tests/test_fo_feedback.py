import unittest
from unittest.mock import MagicMock

from analysis.fo_analyzer import FOAnalyzer
from data.fo_fetcher import FOFetcher


class TestFOFeedback(unittest.TestCase):

    def test_calculate_pcr_supports_upstox_shape(self):
        fetcher = FOFetcher.__new__(FOFetcher)
        chain = {
            "records": {
                "data": [
                    {"CE": {"openInterest": 100}, "PE": {"openInterest": 250}},
                    {"CE": {"openInterest": 200}, "PE": {"openInterest": 150}},
                ]
            }
        }

        pcr = FOFetcher.calculate_pcr(fetcher, chain)

        self.assertAlmostEqual(pcr, 400 / 300, places=6)

    def test_calculate_pcr_returns_none_when_chain_has_no_calls(self):
        fetcher = FOFetcher.__new__(FOFetcher)
        chain = {
            "records": {
                "data": [
                    {"CE": {"openInterest": 0}, "PE": {"openInterest": 100}},
                    {"CE": {"openInterest": 0}, "PE": {"openInterest": 50}},
                ]
            }
        }

        pcr = FOFetcher.calculate_pcr(fetcher, chain)

        self.assertIsNone(pcr)

    def test_nifty_signals_falls_back_to_neutral_pcr_when_invalid(self):
        analyzer = FOAnalyzer.__new__(FOAnalyzer)
        analyzer.fetcher = MagicMock()
        analyzer.fetcher.get_option_chain.return_value = {"records": {"data": []}}
        analyzer.fetcher.calculate_pcr.return_value = None
        analyzer.fetcher.calculate_max_pain.return_value = 0
        analyzer.fetcher.get_highest_oi_strikes.return_value = {}

        signals = FOAnalyzer.get_nifty_signals(analyzer)

        self.assertEqual(signals["nifty_pcr"], 1.0)
        self.assertFalse(signals["nifty_pcr_valid"])
        self.assertIsNone(signals["nifty_pcr_raw"])


if __name__ == "__main__":
    unittest.main()
