import unittest
import sys
import os

# Set sys.path to include the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.microstructure import MicrostructureEngine

class TestMicrostructureEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MicrostructureEngine(imbalance_threshold=0.2)

    def test_calculate_vwap_deviation(self):
        # 101 price, 100 vwap -> 1.0% deviation
        dev = self.engine.calculate_vwap_deviation(101.0, 100.0)
        self.assertAlmostEqual(dev, 1.0)
        
        # Zero protection
        self.assertEqual(self.engine.calculate_vwap_deviation(100.0, 0.0), 0.0)

    def test_calculate_bid_ask_spread(self):
        # Bid = 99, Ask = 101, Mid = 100 -> 2% spread
        spread = self.engine.calculate_bid_ask_spread(99.0, 101.0)
        self.assertAlmostEqual(spread, 2.0)

    def test_calculate_orderbook_imbalance(self):
        # Bids = 300, Asks = 100 -> (300 - 100) / 400 = 0.50
        imbalance = self.engine.calculate_orderbook_imbalance(300, 100)
        self.assertAlmostEqual(imbalance, 0.5)

    def test_detect_spike_event(self):
        # All criteria met -> Triggered
        triggered = self.engine.detect_spike_event(
            price_change_1min=1.3,
            volume_1min=3000,
            avg_volume_1min=1000,
            bid_ask_imbalance=0.4,
            delivery_percent_rising=True
        )
        self.assertTrue(triggered)

        # Price change < 1.2% -> NOT Triggered
        triggered = self.engine.detect_spike_event(
            price_change_1min=1.1,
            volume_1min=3000,
            avg_volume_1min=1000,
            bid_ask_imbalance=0.4,
            delivery_percent_rising=True
        )
        self.assertFalse(triggered)

    def test_analyze_market_depth(self):
        market_depth = {
            "buy": [
                {"price": 150.0, "quantity": 100},
                {"price": 149.5, "quantity": 200}
            ],
            "sell": [
                {"price": 151.0, "quantity": 50},
                {"price": 151.5, "quantity": 100}
            ]
        }
        res = self.engine.analyze_market_depth(market_depth)
        self.assertEqual(res["total_bid_quantity"], 300)
        self.assertEqual(res["total_ask_quantity"], 150)
        self.assertEqual(res["best_bid"], 150.0)
        self.assertEqual(res["best_ask"], 151.0)
        self.assertAlmostEqual(res["orderbook_imbalance"], 0.3333, places=2)

if __name__ == "__main__":
    unittest.main()
