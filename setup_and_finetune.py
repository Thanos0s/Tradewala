import os
import logging
from pathlib import Path

# This script is intended to be run ONCE to download Indian market data and fine‑tune the Kronos model
# using the Superpowers repository (cloned under plugins/superpowers).
# It assumes the Superpowers package provides a CLI entry point or Python API.

# ---------------------------------------------------------------------------
# 1️⃣ Locate the Superpowers package
SUPERPOWERS_ROOT = Path(__file__).resolve().parent / "plugins" / "superpowers"
if not SUPERPOWERS_ROOT.is_dir():
    raise FileNotFoundError(f"Superpowers directory not found at {SUPERPOWERS_ROOT}")

# Add Superpowers to sys.path so we can import its modules
import sys
sys.path.append(str(SUPERPOWERS_ROOT))

# Import hypothetical fine‑tuning utilities (the actual API may differ)
try:
    from superpowers.fine_tune import fine_tune_kronos
    superpowers_available = True
except ImportError as e:
    logging.warning("Superpowers fine‑tuning module not found – skipping Kronos model fine-tuning.")
    superpowers_available = False

# ---------------------------------------------------------------------------
# 2️⃣ Prepare Indian market dataset
# For simplicity we reuse the existing data fetchers to build a CSV that Superpowers can consume.
import pandas as pd
from data.fetcher import fetch_price_data
from data.news_scraper import scrape_news
from data.fo_fetcher import FOFetcher
from analysis.xgboost_model import train_xgboost_model

logging.info("Fetching market data for fine‑tuning and XGBoost model training...")
price_dict = fetch_price_data()
news_data = scrape_news()
fo_fetcher = FOFetcher()
fo_ban_list = fo_fetcher.get_fo_ban_list()

# 2.5️⃣ Train XGBoost classification model
try:
    train_xgboost_model(price_dict)
    print("XGBoost classifier model trained successfully!")
except Exception as e:
    logging.error(f"Failed to train XGBoost model: {e}")

# Combine dict of DataFrames into a single DataFrame – the exact format depends on Superpowers expectations.
combined_path = Path(__file__).resolve().parent / "data" / "fine_tune_dataset.csv"
try:
    df_combined = pd.concat(price_dict.values(), ignore_index=True)
    df_combined.to_csv(combined_path, index=False)
    logging.info(f"Saved fine‑tune dataset to {combined_path}")
except Exception as e:
    logging.error(f"Failed to save combined CSV: {e}")

# ---------------------------------------------------------------------------
# 3️⃣ Run fine‑tuning
if superpowers_available:
    from config import KRONOS_FINETUNED_PATH, KRONOS_MODEL_NAME
    output_dir = Path(__file__).resolve().parent / KRONOS_FINETUNED_PATH
    os.makedirs(output_dir, exist_ok=True)

    logging.info("Starting fine‑tuning with Superpowers…")
    try:
        finetune_result = fine_tune_kronos(
            model_name=KRONOS_MODEL_NAME,
            dataset_path=str(combined_path),
            output_dir=str(output_dir),
            epochs=3,
            learning_rate=5e-5,
            batch_size=16,
        )
        logging.info(f"Fine‑tuning completed. Result: {finetune_result}")
        print("Fine‑tuning finished. Updated model saved to", output_dir)
    except Exception as e:
        logging.error(f"Superpowers fine-tuning execution failed: {e}")
else:
    logging.info("Superpowers fine-tuning skipped (not available). Setup complete.")

