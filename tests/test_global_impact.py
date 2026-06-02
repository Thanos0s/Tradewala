import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analysis.global_impact import GlobalImpactEngine

class TestGlobalImpactEngine(unittest.TestCase):
    def setUp(self):
        self.engine = GlobalImpactEngine()

    def test_calculate_biases_empty(self):
        res = self.engine.calculate_biases({})
        self.assertEqual(res["sector_modifiers"]["IT"], 0.0)
        self.assertEqual(res["general_modifier"], 0.0)
        self.assertIn("No global market indicator data available.", res["reasons"])

    def test_calculate_biases_bullish_it(self):
        indicators = {
            "nasdaq": {"current": 16000.0, "return_1d": 0.8},
            "shanghai": {"current": 3000.0, "return_1d": 0.1},
            "gold": {"current": 2000.0, "return_1d": 0.0},
            "dxy": {"current": 104.0, "return_1d": 0.0}
        }
        res = self.engine.calculate_biases(indicators)
        self.assertEqual(res["sector_modifiers"]["IT"], 5.0)
        self.assertEqual(res["sector_modifiers"]["Chemicals"], 0.0)
        self.assertEqual(res["general_modifier"], 0.0)

    def test_calculate_biases_bearish_it_and_china_chemicals(self):
        indicators = {
            "nasdaq": {"current": 16000.0, "return_1d": -0.7},
            "shanghai": {"current": 3000.0, "return_1d": -1.2},
            "gold": {"current": 2000.0, "return_1d": 0.6},
            "dxy": {"current": 104.0, "return_1d": 0.4}
        }
        res = self.engine.calculate_biases(indicators)
        self.assertEqual(res["sector_modifiers"]["IT"], -5.0)
        self.assertEqual(res["sector_modifiers"]["Chemicals"], 4.0)
        self.assertEqual(res["sector_modifiers"]["Gold"], 6.0)
        self.assertEqual(res["general_modifier"], -3.0)

if __name__ == "__main__":
    unittest.main()
