import os
import sqlite3
import logging
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("trade_logger")

DB_PATH = "data/trading_journal.db"

def init_db(db_path=DB_PATH):
    """Initialize the SQLite database and create the trades table if it doesn't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            target REAL NOT NULL,
            shares INTEGER NOT NULL,
            allocated_capital REAL NOT NULL,
            trade_category TEXT NOT NULL,
            regime TEXT NOT NULL,
            total_score REAL NOT NULL,
            xgb_probability REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            exit_date TEXT,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            logged_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {db_path}")

def log_new_trades(picks: dict, regime_info: dict, db_path=DB_PATH):
    """Log newly recommended picks as PENDING trades in the journal."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    regime = regime_info.get("regime", "UNKNOWN")
    logged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_date = datetime.now().strftime("%Y-%m-%d")
    
    logged_count = 0
    # Categories: intraday_picks, swing_picks, high_risk_picks
    for category_key, stock_list in picks.items():
        category_name = category_key.replace("_picks", "").upper()
        for stock in stock_list:
            symbol = stock.get("symbol")
            entry_price = stock.get("entry", 0.0)
            stop_loss = stock.get("stop_loss", 0.0)
            target = stock.get("target", 0.0)
            total_score = stock.get("total_score", 0.0)
            xgb_probability = stock.get("xgb_probability", 0.0)
            
            # Risk sizing details
            risk_mgmt = stock.get("risk_management", {})
            shares = risk_mgmt.get("shares", 0)
            allocated_capital = risk_mgmt.get("allocated_capital", 0.0)
            
            # Check if this trade is already logged for today to prevent duplicates
            cursor.execute(
                "SELECT id FROM trades WHERE symbol = ? AND entry_date = ? AND trade_category = ?",
                (symbol, entry_date, category_name)
            )
            if cursor.fetchone():
                logger.debug(f"Trade already logged for {symbol} on {entry_date}")
                continue
                
            cursor.execute("""
                INSERT INTO trades (
                    symbol, entry_date, entry_price, stop_loss, target,
                    shares, allocated_capital, trade_category, regime,
                    total_score, xgb_probability, status, logged_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """, (
                symbol, entry_date, entry_price, stop_loss, target,
                shares, allocated_capital, category_name, regime,
                total_score, xgb_probability, logged_at
            ))
            logger.info(f"Logged PENDING {category_name} trade for {symbol} at entry {entry_price}")
            logged_count += 1
            
    conn.commit()
    conn.close()
    if logged_count > 0:
        logger.info(f"Successfully logged {logged_count} new trades to {db_path}")

def update_pending_trades(db_path=DB_PATH):
    """
    Query all pending trades and update their status using subsequent historical prices.
    Checks if SL or Target was hit, or if the trade reached 5-day expiration.
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, symbol, entry_date, entry_price, stop_loss, target, shares, trade_category
        FROM trades 
        WHERE status = 'PENDING'
    """)
    pending = cursor.fetchall()
    
    if not pending:
        logger.info("No pending trades to update in database.")
        conn.close()
        return

    logger.info(f"Updating {len(pending)} pending trades...")
    
    for row in pending:
        trade_id, symbol, entry_date_str, entry_price, stop_loss, target, shares, category = row
        
        try:
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Invalid entry_date format: {entry_date_str} for trade ID {trade_id}")
            continue

        # Check up to 10 calendar days later to get at least 5 business days
        end_date = entry_date + timedelta(days=12)
        start_fetch = entry_date + timedelta(days=1)  # start fetching from the day after entry
        
        # Download historical data from yfinance starting after entry date
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_fetch.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            
            if df.empty:
                logger.warning(f"No price data available for {symbol} after {entry_date_str} yet.")
                continue
                
            # Filter and take exactly the first 5 trading days after entry
            sub_df = df.head(5)
            
            resolved = False
            status = "PENDING"
            exit_price = None
            exit_date = None
            
            for idx, date_ts in enumerate(sub_df.index):
                row_data = sub_df.iloc[idx]
                high = float(row_data["High"])
                low = float(row_data["Low"])
                close = float(row_data["Close"])
                date_str = date_ts.strftime("%Y-%m-%d")
                
                # Check for stop loss and target hits
                # If both are hit on the same day, conservatively assume stopped out
                if low <= stop_loss and high >= target:
                    status = "HIT_SL"
                    exit_price = stop_loss
                    exit_date = date_str
                    resolved = True
                    break
                elif low <= stop_loss:
                    status = "HIT_SL"
                    exit_price = stop_loss
                    exit_date = date_str
                    resolved = True
                    break
                elif high >= target:
                    status = "HIT_TARGET"
                    exit_price = target
                    exit_date = date_str
                    resolved = True
                    break
                
                # If we've reached the 5th business day and it hasn't hit SL or Target, expire the trade
                if idx == len(sub_df) - 1:
                    status = "EXPIRED"
                    exit_price = close
                    exit_date = date_str
                    resolved = True
                    break
            
            if resolved:
                pnl = (exit_price - entry_price) * shares
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                
                # Update in DB
                cursor.execute("""
                    UPDATE trades
                    SET status = ?, exit_date = ?, exit_price = ?, pnl = ?, pnl_pct = ?
                    WHERE id = ?
                """, (status, exit_date, exit_price, pnl, pnl_pct, trade_id))
                logger.info(f"resolved trade ID {trade_id} ({symbol}): {status} on {exit_date} (PnL: {pnl:+.2f} INR)")
                
        except Exception as e:
            logger.error(f"Error updating pending trade ID {trade_id} ({symbol}): {e}")

    conn.commit()
    conn.close()
    logger.info("Pending trades update complete.")

def print_performance_summary(db_path=DB_PATH):
    """Print the journal performance stats."""
    if not os.path.exists(db_path):
        print("No trading journal found.")
        return
        
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM trades", conn)
    conn.close()
    
    if df.empty:
        print("Trading journal is empty.")
        return
        
    resolved = df[df["status"] != "PENDING"]
    pending = df[df["status"] == "PENDING"]
    
    print("\n" + "="*80)
    print("                      TRADWALA KRONOS PERFORMANCE SUMMARY")
    print("="*80)
    print(f"Total Logged Recommendations : {len(df)}")
    print(f"Pending Trades               : {len(pending)}")
    print(f"Resolved Trades              : {len(resolved)}")
    
    if not resolved.empty:
        wins = resolved[resolved["status"] == "HIT_TARGET"]
        losses = resolved[resolved["status"] == "HIT_SL"]
        expired = resolved[resolved["status"] == "EXPIRED"]
        
        # Expired counts as win or loss based on PnL
        expired_wins = expired[expired["pnl"] > 0]
        expired_losses = expired[expired["pnl"] <= 0]
        
        total_wins = len(wins) + len(expired_wins)
        total_losses = len(losses) + len(expired_losses)
        win_rate = (total_wins / len(resolved)) * 100 if len(resolved) > 0 else 0.0
        
        gross_profit = resolved[resolved["pnl"] > 0]["pnl"].sum()
        gross_loss = resolved[resolved["pnl"] < 0]["pnl"].sum()
        total_pnl = resolved["pnl"].sum()
        profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else float("inf")
        
        print(f"Win Rate                     : {win_rate:.1f}% ({total_wins} Wins / {total_losses} Losses)")
        print(f"  - Hit Target Target        : {len(wins)}")
        print(f"  - Hit Stop Loss            : {len(losses)}")
        print(f"  - Expired (Profitable)     : {len(expired_wins)}")
        print(f"  - Expired (Loss/Neutral)   : {len(expired_losses)}")
        print(f"Total Cumulative PnL         : {total_pnl:+.2f} INR")
        print(f"Gross Profit                 : {gross_profit:.2f} INR")
        print(f"Gross Loss                   : {abs(gross_loss):.2f} INR")
        print(f"Profit Factor                : {profit_factor:.2f}")
        print(f"Average Return per Trade     : {resolved['pnl_pct'].mean():+.2f}%")
        
        print("\nBreakdown by Category:")
        cat_stats = resolved.groupby("trade_category").agg(
            Count=("id", "count"),
            AvgPnLPct=("pnl_pct", "mean"),
            TotalPnL=("pnl", "sum")
        )
        print(cat_stats.to_string())
        
        print("\nBreakdown by Market Regime:")
        regime_stats = resolved.groupby("regime").agg(
            Count=("id", "count"),
            AvgPnLPct=("pnl_pct", "mean"),
            TotalPnL=("pnl", "sum")
        )
        print(regime_stats.to_string())
    print("="*80 + "\n")


def print_confidence_calibration_summary(db_path=DB_PATH, bucket_size=10):
    """Print a simple calibration snapshot for stored XGBoost probabilities.
    This is a lightweight feedback loop that shows whether higher probabilities
    are actually corresponding to better outcomes.
    """
    if not os.path.exists(db_path):
        print("No trading journal found for calibration summary.")
        return

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM trades WHERE status != 'PENDING'", conn)
    conn.close()

    if df.empty or "xgb_probability" not in df.columns:
        print("No resolved trades with probability data found.")
        return

    df = df.copy()
    df["win"] = df["pnl"] > 0

    # Bucket probabilities into 10-point bands by default.
    def bucket_prob(prob):
        try:
            prob = float(prob)
        except Exception:
            return "unknown"
        start = int(prob // bucket_size) * bucket_size
        end = min(start + bucket_size, 100)
        return f"{start:02d}-{end:02d}%"

    df["prob_bucket"] = df["xgb_probability"].apply(bucket_prob)
    grouped = df.groupby("prob_bucket", dropna=False).agg(
        Trades=("id", "count"),
        WinRate=("win", "mean"),
        AvgPnL=("pnl", "mean"),
        AvgPnLPct=("pnl_pct", "mean"),
    ).reset_index()

    # Sort buckets numerically where possible.
    def bucket_sort_key(label):
        if label == "unknown":
            return 999
        try:
            return int(label.split("-")[0])
        except Exception:
            return 998

    grouped = grouped.sort_values(by="prob_bucket", key=lambda s: s.map(bucket_sort_key))

    print("\n" + "-" * 80)
    print("                    XGBOOST CONFIDENCE CALIBRATION SNAPSHOT")
    print("-" * 80)
    print(grouped.to_string(index=False, formatters={
        "WinRate": lambda x: f"{x*100:.1f}%",
        "AvgPnL": lambda x: f"{x:+.2f}",
        "AvgPnLPct": lambda x: f"{x:+.2f}%",
    }))
    print("-" * 80 + "\n")
