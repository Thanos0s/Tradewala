import os
import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict

# ── Kronos repo ──────────────────────────────────────────────────────────────
# Assumes the repo is cloned at <project_root>/Kronos-repo
_REPO_PATH = Path(__file__).resolve().parents[1] / "Kronos-repo"

_kronos_available = False
Kronos = None
KronosTokenizer = None
KronosPredictor = None

if _REPO_PATH.exists():
    sys.path.insert(0, str(_REPO_PATH))
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor
        _kronos_available = True
        logging.info(f"✅ Kronos classes imported from {_REPO_PATH}")
    except Exception as e:
        logging.error(f"Failed to import Kronos model classes: {e}")
else:
    logging.warning(
        f"Kronos repo NOT found at {_REPO_PATH}. "
        "Clone with: git clone https://github.com/shiyu-coder/Kronos Kronos-repo"
    )

# ── Config ────────────────────────────────────────────────────────────────────
try:
    from config import (
        KRONOS_MODEL_NAME,
        KRONOS_TOKENIZER_NAME,
        KRONOS_FINETUNED_PATH,
        KRONOS_LOOKBACK,
        KRONOS_PRED_LEN,
        KRONOS_MAX_CONTEXT,
    )
except ImportError:
    KRONOS_MODEL_NAME      = "NeoQuasar/Kronos-small"
    KRONOS_TOKENIZER_NAME  = "NeoQuasar/Kronos-Tokenizer-base"
    KRONOS_FINETUNED_PATH  = ""
    KRONOS_LOOKBACK        = 400
    KRONOS_PRED_LEN        = 5
    KRONOS_MAX_CONTEXT     = 512

try:
    import torch
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    _DEVICE = "cpu"


class KronosStockPredictor:
    """
    Wraps the Kronos foundation model for NSE stock price forecasting.

    Priority:
      1. Real Kronos model (shiyu-coder/Kronos repo + NeoQuasar HF weights)
      2. Heuristic EMA fallback (if repo or weights unavailable)
    """

    MODEL_NAME      = KRONOS_MODEL_NAME      # "NeoQuasar/Kronos-small"
    TOKENIZER_NAME  = KRONOS_TOKENIZER_NAME  # "NeoQuasar/Kronos-Tokenizer-base"
    FINETUNED_PATH  = KRONOS_FINETUNED_PATH  # local fine-tuned path (optional)

    def __init__(self, load_model: bool = True):
        self.use_fallback  = True
        self.predictor_obj = None
        if not load_model:
            logging.info("Kronos predictor initialized in fallback-only mode.")
            return

        if not _kronos_available:
            logging.warning("Kronos classes not available — using EMA heuristic fallback.")
            return

        try:
            # Prefer local fine-tuned checkpoint; fall back to HF Hub
            tokenizer_path = (
                self.FINETUNED_PATH
                if os.path.isdir(str(self.FINETUNED_PATH))
                else self.TOKENIZER_NAME
            )
            model_path = (
                self.FINETUNED_PATH
                if os.path.isdir(str(self.FINETUNED_PATH))
                else self.MODEL_NAME
            )

            logging.info(f"Loading Kronos tokenizer from: {tokenizer_path}")
            tokenizer = KronosTokenizer.from_pretrained(tokenizer_path)

            logging.info(f"Loading Kronos model from: {model_path}")
            model = Kronos.from_pretrained(model_path)

            self.predictor_obj = KronosPredictor(
                model,
                tokenizer,
                max_context=KRONOS_MAX_CONTEXT,
            )
            self.use_fallback = False
            logging.info(
                f"🚀 Kronos model loaded successfully on {_DEVICE} — "
                "REAL AI predictions active."
            )

        except Exception as exc:
            logging.error(f"Kronos model load failed: {exc}")
            logging.warning("Falling back to EMA heuristic predictor.")
            self.use_fallback = True

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _prepare_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Select last KRONOS_LOOKBACK rows and ensure required OHLCV columns.
        Kronos expects: open, high, low, close  (volume / amount optional).
        """
        col_map = {}
        for col in df.columns:
            lc = col.lower()
            if lc in ("open", "high", "low", "close", "volume", "amount"):
                col_map[col] = lc

        prepared = df.rename(columns=col_map).copy()

        # Fill optional columns with zeros if absent
        for opt in ("volume", "amount"):
            if opt not in prepared.columns:
                prepared[opt] = 0.0

        required = ["open", "high", "low", "close", "volume", "amount"]
        available = [c for c in required if c in prepared.columns]
        prepared = prepared[available]
        
        # Drop rows where critical price columns have NaN
        critical_cols = [c for c in ["open", "high", "low", "close"] if c in prepared.columns]
        prepared = prepared.dropna(subset=critical_cols)
        
        prepared = prepared.tail(KRONOS_LOOKBACK).reset_index(drop=True)
        return prepared

    def _get_timestamps(self, df: pd.DataFrame, ohlcv: pd.DataFrame):
        """Extract x_timestamp and build y_timestamp (next KRONOS_PRED_LEN business days)."""
        # Try to get timestamps from original df
        ts_col = None
        for c in df.columns:
            if c.lower() in ("timestamp", "timestamps", "date", "datetime", "time"):
                ts_col = c
                break

        n = len(ohlcv)
        if ts_col is not None:
            x_ts = pd.to_datetime(df[ts_col]).iloc[-n:].reset_index(drop=True)
        else:
            # Build synthetic daily timestamps ending today
            end = pd.Timestamp.today().normalize()
            x_ts = pd.Series(pd.bdate_range(end=end, periods=n))

        last_ts = x_ts.iloc[-1]
        y_ts = pd.Series(pd.bdate_range(start=last_ts + pd.Timedelta(days=1), periods=KRONOS_PRED_LEN))
        return x_ts, y_ts

    # ── EMA fallback ─────────────────────────────────────────────────────────

    def _fallback_predict(self, symbol: str, df: pd.DataFrame) -> dict:
        close = df["close"] if "close" in df.columns else df[df.columns[-1]]
        current_close = float(close.iloc[-1])
        ma5  = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean())

        if ma5 > ma20:
            change_pct = round(1.2 + (ma5 / ma20 - 1) * 5, 2)   # amplify signal slightly
            direction  = "UP"
        else:
            change_pct = round(-0.8 - (ma20 / ma5 - 1) * 3, 2)
            direction  = "DOWN"

        change_pct = max(-5.0, min(5.0, change_pct))             # cap ±5 %

        return {
            "symbol":                  symbol,
            "current_price":           current_close,
            "predicted_tomorrow":      round(current_close * (1 + change_pct / 100), 2),
            "predicted_5day":          round(current_close * (1 + change_pct * 3 / 100), 2),
            "predicted_change_pct":    change_pct,
            "predicted_5day_change_pct": change_pct * 3,
            "kronos_direction":        direction,
            "kronos_confidence":       15.0,
            "raw_forecast":            None,
            "mode":                    "FALLBACK_EMA",
        }

    # ── Real Kronos prediction ────────────────────────────────────────────────

    def _kronos_predict(self, symbol: str, df: pd.DataFrame) -> dict:
        ohlcv   = self._prepare_ohlcv(df)
        x_ts, y_ts = self._get_timestamps(df, ohlcv)
        current_close = float(ohlcv["close"].iloc[-1])

        pred_df = self.predictor_obj.predict(
            df          = ohlcv,
            x_timestamp = x_ts,
            y_timestamp = y_ts,
            pred_len    = KRONOS_PRED_LEN,
            T           = 1.0,
            top_p       = 0.9,
            sample_count= 1,
        )

        pred_close      = pred_df["close"].values
        predicted_tmrw  = float(pred_close[0])
        predicted_5day  = float(pred_close[-1])
        change_pct      = round((predicted_tmrw - current_close) / current_close * 100, 4)
        change_5pct     = round((predicted_5day  - current_close) / current_close * 100, 4)
        direction       = "UP" if change_pct > 0 else ("DOWN" if change_pct < 0 else "FLAT")

        # Confidence: derived from magnitude of predicted move (capped at 95)
        confidence = min(95.0, 40.0 + abs(change_pct) * 10)

        return {
            "symbol":                  symbol,
            "current_price":           current_close,
            "predicted_tomorrow":      round(predicted_tmrw, 2),
            "predicted_5day":          round(predicted_5day, 2),
            "predicted_change_pct":    change_pct,
            "predicted_5day_change_pct": change_5pct,
            "kronos_direction":        direction,
            "kronos_confidence":       round(confidence, 1),
            "raw_forecast":            pred_df,
            "mode":                    "KRONOS_AI",
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def predict_stock(self, symbol: str, df: pd.DataFrame) -> dict:
        try:
            if self.use_fallback:
                return self._fallback_predict(symbol, df)
            return self._kronos_predict(symbol, df)
        except Exception as exc:
            logging.error(f"[{symbol}] Kronos prediction error: {exc} — using EMA fallback.")
            return self._fallback_predict(symbol, df)

    def predict_batch_stocks(self, stock_data: Dict[str, pd.DataFrame]) -> dict:
        """
        Runs Kronos in batch mode (predict_batch) for efficiency when
        the real model is available, otherwise falls back per-stock.
        """
        if self.use_fallback or not stock_data:
            return {sym: self.predict_stock(sym, df) for sym, df in stock_data.items()}

        # ── Batch path ────────────────────────────────────────────────────────
        try:
            df_list, x_ts_list, y_ts_list, symbols = [], [], [], []
            for sym, df in stock_data.items():
                ohlcv  = self._prepare_ohlcv(df)
                x_ts, y_ts = self._get_timestamps(df, ohlcv)
                df_list.append(ohlcv)
                x_ts_list.append(x_ts)
                y_ts_list.append(y_ts)
                symbols.append(sym)

            # Kronos batch requires equal lookback lengths; pad/trim to min
            min_len = min(len(d) for d in df_list)
            df_list   = [d.tail(min_len).reset_index(drop=True) for d in df_list]
            x_ts_list = [ts.iloc[-min_len:].reset_index(drop=True) for ts in x_ts_list]

            pred_list = self.predictor_obj.predict_batch(
                df_list         = df_list,
                x_timestamp_list= x_ts_list,
                y_timestamp_list= y_ts_list,
                pred_len        = KRONOS_PRED_LEN,
                T               = 1.0,
                top_p           = 0.9,
                sample_count    = 1,
                verbose         = False,
            )

            results = {}
            for sym, raw_df, ohlcv in zip(symbols, pred_list, df_list):
                current_close  = float(ohlcv["close"].iloc[-1])
                pred_close     = raw_df["close"].values
                predicted_tmrw = float(pred_close[0])
                predicted_5day = float(pred_close[-1])
                change_pct     = round((predicted_tmrw - current_close) / current_close * 100, 4)
                change_5pct    = round((predicted_5day  - current_close) / current_close * 100, 4)
                direction      = "UP" if change_pct > 0 else ("DOWN" if change_pct < 0 else "FLAT")
                confidence     = min(95.0, 40.0 + abs(change_pct) * 10)

                results[sym] = {
                    "symbol":                  sym,
                    "current_price":           current_close,
                    "predicted_tomorrow":      round(predicted_tmrw, 2),
                    "predicted_5day":          round(predicted_5day, 2),
                    "predicted_change_pct":    change_pct,
                    "predicted_5day_change_pct": change_5pct,
                    "kronos_direction":        direction,
                    "kronos_confidence":       round(confidence, 1),
                    "raw_forecast":            raw_df,
                    "mode":                    "KRONOS_AI_BATCH",
                }
            logging.info(f"✅ Kronos batch prediction completed for {len(results)} stocks.")
            return results

        except Exception as exc:
            logging.error(f"Kronos batch prediction failed: {exc} — falling back per-stock.")
            return {sym: self.predict_stock(sym, df) for sym, df in stock_data.items()}

    # Alias so main.py / orchestrator can call either name
    def predict(self, stock_data: Dict[str, pd.DataFrame]) -> dict:
        return self.predict_batch_stocks(stock_data)

    # ── Scoring ───────────────────────────────────────────────────────────────

    def score_kronos_prediction(self, prediction: dict) -> float:
        """
        Map predicted_change_pct → score out of 40 pts (weight in scoring engine).
        """
        pct = prediction.get("predicted_change_pct", 0)
        if pct >= 3:
            base = 40
        elif pct >= 2:
            base = 32
        elif pct >= 1:
            base = 24
        elif pct >= 0.5:
            base = 16
        elif pct >= 0:
            base = 8
        else:
            base = 0     # bearish — score 0 for the kronos component

        # If the real AI model is running, apply a small confidence boost
        mode = prediction.get("mode", "FALLBACK_EMA")
        if "KRONOS_AI" in mode:
            conf = prediction.get("kronos_confidence", 40) / 100.0
            base = base * (0.7 + 0.3 * conf)   # scale between 70% and 100% of base

        return round(float(base), 2)
