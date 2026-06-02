import os
import logging
import json
import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

# Model storage path
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kronos", "models"))
MODEL_PATH = os.path.join(MODEL_DIR, "xgb_classifier.json")

# Define the exact features used by the XGBoost model
FEATURE_COLUMNS = [
    "rsi",
    "macd_hist",
    "volume_ratio",
    "ema_ratio_9_21",
    "ema_ratio_21_50",
    "ema_ratio_50_200",
    "close_ema200_ratio",
    "returns_1d",
    "returns_3d",
    "returns_5d",
    "volatility_atr_ratio"
]

def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical features for the entire dataframe history.
    Ensures exact alignment and cleaning.
    """
    df_feat = df.copy()
    
    # Ensure numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df_feat.columns:
            df_feat[col] = pd.to_numeric(df_feat[col], errors='coerce')
    df_feat.dropna(subset=["open", "high", "low", "close"], inplace=True)
    
    if len(df_feat) < 200:
        return pd.DataFrame()
        
    try:
        # 1. EMAs
        df_feat['ema9'] = ta.ema(df_feat['close'], length=9)
        df_feat['ema21'] = ta.ema(df_feat['close'], length=21)
        df_feat['ema50'] = ta.ema(df_feat['close'], length=50)
        df_feat['ema200'] = ta.ema(df_feat['close'], length=200)
        
        # 2. RSI
        df_feat['rsi'] = ta.rsi(df_feat['close'], length=14)
        
        # 3. MACD
        macd = ta.macd(df_feat['close'], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            hist_cols = [c for c in macd.columns if c.startswith('MACDh_')]
            if hist_cols:
                df_feat['macd_hist'] = macd[hist_cols[0]]
            else:
                df_feat['macd_hist'] = 0.0
        else:
            df_feat['macd_hist'] = 0.0
            
        # 4. Volume Ratio
        df_feat['volume_20ma'] = df_feat['volume'].rolling(20).mean()
        df_feat['volume_ratio'] = df_feat['volume'] / (df_feat['volume_20ma'] + 1e-8)
        
        # 5. Volatility (ATR ratio)
        df_feat['atr'] = ta.atr(df_feat['high'], df_feat['low'], df_feat['close'], length=14)
        df_feat['volatility_atr_ratio'] = df_feat['atr'] / (df_feat['close'] + 1e-8)
        
        # 6. Ratios & Spreads
        df_feat['ema_ratio_9_21'] = df_feat['ema9'] / (df_feat['ema21'] + 1e-8)
        df_feat['ema_ratio_21_50'] = df_feat['ema21'] / (df_feat['ema50'] + 1e-8)
        df_feat['ema_ratio_50_200'] = df_feat['ema50'] / (df_feat['ema200'] + 1e-8)
        df_feat['close_ema200_ratio'] = df_feat['close'] / (df_feat['ema200'] + 1e-8)
        
        # 7. Momentum returns
        df_feat['returns_1d'] = df_feat['close'].pct_change(1)
        df_feat['returns_3d'] = df_feat['close'].pct_change(3)
        df_feat['returns_5d'] = df_feat['close'].pct_change(5)
        
        # Fill optional NaN values with defaults
        df_feat['rsi'] = df_feat['rsi'].fillna(50.0)
        df_feat['macd_hist'] = df_feat['macd_hist'].fillna(0.0)
        df_feat['volume_ratio'] = df_feat['volume_ratio'].fillna(1.0)
        df_feat['volatility_atr_ratio'] = df_feat['volatility_atr_ratio'].fillna(0.02)
        df_feat['ema_ratio_9_21'] = df_feat['ema_ratio_9_21'].fillna(1.0)
        df_feat['ema_ratio_21_50'] = df_feat['ema_ratio_21_50'].fillna(1.0)
        df_feat['ema_ratio_50_200'] = df_feat['ema_ratio_50_200'].fillna(1.0)
        df_feat['close_ema200_ratio'] = df_feat['close_ema200_ratio'].fillna(1.0)
        df_feat['returns_1d'] = df_feat['returns_1d'].fillna(0.0)
        df_feat['returns_3d'] = df_feat['returns_3d'].fillna(0.0)
        df_feat['returns_5d'] = df_feat['returns_5d'].fillna(0.0)
        
        return df_feat[FEATURE_COLUMNS + ["close"]]
        
    except Exception as e:
        logger.error(f"Error preparing features for XGBoost: {e}")
        return pd.DataFrame()

def train_xgboost_model(stock_data: dict):
    """Combine historical price datasets, prepare binary classification targets, and train XGBoost."""
    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
    except ImportError:
        logger.error("XGBoost or scikit-learn not available. Skipping training.")
        return
        
    logger.info("Starting training of XGBoost model...")
    all_dfs = []
    
    for symbol, df in stock_data.items():
        df_prep = prepare_features(df)
        if df_prep.empty or len(df_prep) < 100:
            continue
            
        # Target: 1 if close price in 5 days is higher than current close, else 0
        df_prep['target'] = (df_prep['close'].shift(-5) > df_prep['close']).astype(int)
        # Drop the last 5 rows since they won't have valid future targets
        df_prep = df_prep.iloc[:-5]
        all_dfs.append(df_prep)
        
    if not all_dfs:
        logger.error("No valid stock data found to train XGBoost!")
        return
        
    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df.dropna(subset=['target'], inplace=True)
    
    X = combined_df[FEATURE_COLUMNS]
    y = combined_df['target']
    
    if len(X) < 1000:
        logger.warning(f"Very small dataset size ({len(X)}) for XGBoost training. Performance may be poor.")
        
    # Split to check performance
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = xgb.XGBClassifier(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss"
    )
    
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    accuracy = model.score(X_test, y_test)
    logger.info(f"XGBoost Classifier trained. Test Set Accuracy: {accuracy:.2%}")
    
    # Save the model
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save_model(MODEL_PATH)
    logger.info(f"XGBoost model saved successfully to: {MODEL_PATH}")

class XGBoostPredictor:
    """Loads the pre-trained XGBoost model and calculates trade probability score."""
    
    def __init__(self):
        self.model = None
        self.is_loaded = False
        
        try:
            import xgboost as xgb
            if os.path.exists(MODEL_PATH):
                self.model = xgb.XGBClassifier()
                self.model.load_model(MODEL_PATH)
                self.is_loaded = True
                logger.info("🚀 XGBoost model loaded successfully. Real probabilities active.")
            else:
                logger.warning(f"XGBoost model file not found at {MODEL_PATH}. Run setup_and_finetune.py first.")
        except Exception as e:
            logger.error(f"Failed to load XGBoost model: {e}")
            
    def predict_probability(self, df: pd.DataFrame) -> float:
        """Predict the probability (0.0 to 1.0) of a positive 5-day return.
        Falls back to neutral 0.50 if model is not loaded.
        """
        if not self.is_loaded or self.model is None:
            return 0.50
            
        try:
            df_feat = prepare_features(df)
            if df_feat.empty:
                return 0.50
                
            # Extract latest row as features
            latest_row = df_feat[FEATURE_COLUMNS].iloc[-1:]
            probs = self.model.predict_proba(latest_row)
            # Return probability of class 1 (bullish outcome)
            return float(probs[0][1])
        except Exception as e:
            logger.error(f"XGBoost prediction error: {e}")
            return 0.50
