import unittest

from kronos.predictor import KronosStockPredictor


class TestKronosPredictor(unittest.TestCase):

    def test_fallback_only_init_skips_model_loading(self):
        predictor = KronosStockPredictor(load_model=False)

        self.assertTrue(predictor.use_fallback)
        self.assertIsNone(predictor.predictor_obj)


if __name__ == "__main__":
    unittest.main()
