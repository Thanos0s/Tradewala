import logging
import math
from config import RISK_MAX_RSI, RISK_MIN_VOLUME, RISK_MIN_VOLUME_20MA_RATIO

logger = logging.getLogger(__name__)

# Sector definitions for active watchlisted stocks
SECTOR_MAP = {
    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT", 
    "NAUKRI": "IT", "PERSISTENT": "IT", "LTIM": "IT", "OFSS": "IT", "DIXON": "IT",
    # Banking / Financials
    "HDFCBANK": "Financials", "ICICIBANK": "Financials", "SBIN": "Financials", 
    "KOTAKBANK": "Financials", "AXISBANK": "Financials", "INDUSINDBK": "Financials", 
    "BANKBARODA": "Financials", "PNB": "Financials", "CANBK": "Financials", 
    "FEDERALBNK": "Financials", "IDFCFIRSTB": "Financials", "BANDHANBNK": "Financials", 
    "AUBANK": "Financials", "BAJFINANCE": "Financials", "BAJAJFINSV": "Financials", "PAYTM": "Financials",
    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG", 
    "COLPAL": "FMCG", "MARICO": "FMCG", "GODREJCP": "FMCG", "DABUR": "FMCG", "PAGEIND": "FMCG",
    # Auto
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "HEROMOTOCO": "Auto", "EICHERMOT": "Auto", 
    "M&M": "Auto", "BALKRISIND": "Auto",
    # Pharma
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "DIVISLAB": "Pharma", "CIPLA": "Pharma", 
    "APOLLOHOSP": "Pharma", "LUPIN": "Pharma", "TORNTPHARM": "Pharma", "ALKEM": "Pharma",
    # Energy / Commodities
    "RELIANCE": "Energy", "NTPC": "Energy", "POWERGRID": "Energy", "BPCL": "Energy", 
    "ONGC": "Energy", "TATAPOWER": "Energy", "COALINDIA": "Energy",
    # Metals / Materials
    "JSWSTEEL": "Metals", "TATASTEEL": "Metals", "HINDALCO": "Metals", 
    "ULTRACEMCO": "Metals", "GRASIM": "Metals", "SHREECEM": "Metals", "ASTRAL": "Metals", "SUPREMEIND": "Metals",
}

class RiskManager:
    """Calculates position sizing, limits sector exposure, and manages portfolio risk."""
    
    def __init__(self, account_equity: float = 100000.0, risk_per_trade_pct: float = 1.5, max_trade_allocation_pct: float = 20.0, max_sector_exposure: int = 2):
        self.account_equity = account_equity
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_trade_allocation_pct = max_trade_allocation_pct  # Max cap on capital per trade
        self.max_sector_exposure = max_sector_exposure          # Max stocks allowed in same sector
        logger.info(f"RiskManager initialized (Equity: ₹{account_equity:,}, Risk/Trade: {risk_per_trade_pct}%)")

    def calculate_position_size(self, entry: float, stop_loss: float) -> dict:
        """Calculate position sizing using the Fixed-Fractional Risk sizing rule.
        Risk Budget = Equity * Risk%
        Loss/Share = Entry - StopLoss
        Shares = Risk Budget / Loss/Share
        """
        if not entry or not stop_loss or entry <= stop_loss:
            return {"shares": 0, "allocated_capital": 0.0, "pct_of_account": 0.0, "risk_amount": 0.0}
            
        try:
            risk_budget = self.account_equity * (self.risk_per_trade_pct / 100.0)
            loss_per_share = entry - stop_loss
            
            # 1. Shares to buy based on risk
            shares = math.floor(risk_budget / loss_per_share)
            allocated_capital = shares * entry
            
            # 2. Hard Cap check (Max % allocation of portfolio size per trade)
            max_allowed_capital = self.account_equity * (self.max_trade_allocation_pct / 100.0)
            if allocated_capital > max_allowed_capital:
                shares = math.floor(max_allowed_capital / entry)
                allocated_capital = shares * entry
                
            # Recalculate values
            risk_amount = shares * loss_per_share
            pct_of_account = (allocated_capital / self.account_equity) * 100.0
            
            return {
                "shares": int(shares),
                "allocated_capital": round(allocated_capital, 2),
                "pct_of_account": round(pct_of_account, 2),
                "risk_amount": round(risk_amount, 2)
            }
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return {"shares": 0, "allocated_capital": 0.0, "pct_of_account": 0.0, "risk_amount": 0.0}

    def allocate_portfolio(self, ranked_picks: dict) -> dict:
        """Apply sector limits, max total counts, and compute position sizing for final daily picks."""
        final_picks = {
            "intraday_picks": [],
            "high_risk_picks": [],
            "swing_picks": []
        }
        
        sectors_count = {}
        total_allocated = 0.0
        
        # Flatten all picks with category tag to process them in priority order (high score first)
        flat_picks = []
        for cat in ["intraday_picks", "high_risk_picks", "swing_picks"]:
            for stock in ranked_picks.get(cat, []):
                # Ensure we tag the category
                stock["origin_category"] = cat
                flat_picks.append(stock)
                
        # Sort by total score descending
        flat_picks = sorted(flat_picks, key=lambda x: x.get("total_score", 0), reverse=True)
        
        # Apply risk management constraints
        for stock in flat_picks:
            symbol = stock["symbol"]
            
            # Risk Engine pre-rejection rules
            indicators = stock.get("technical_indicators", {})
            price = stock.get("entry", 0.0)
            
            # 1. Overbought check
            rsi = indicators.get("rsi", 50.0)
            if rsi > RISK_MAX_RSI:
                logger.warning(f"RiskManager: Rejecting {symbol} - Overbought (RSI = {rsi:.1f} > {RISK_MAX_RSI})")
                continue
                
            # 2. Overextended check
            bb_upper = indicators.get("bb_upper")
            if bb_upper and price > bb_upper:
                logger.warning(f"RiskManager: Rejecting {symbol} - Overextended (Price {price:.2f} > BB Upper {bb_upper:.2f})")
                continue
                
            # 3. Volume/Liquidity check
            vol = indicators.get("volume", 100000.0)
            vol_20ma = indicators.get("volume_20ma", 100000.0)
            
            if vol < RISK_MIN_VOLUME:
                logger.warning(f"RiskManager: Rejecting {symbol} - Low Liquidity / Operator risk (Volume {vol} < absolute min {RISK_MIN_VOLUME})")
                continue
                
            if vol_20ma and vol < vol_20ma * RISK_MIN_VOLUME_20MA_RATIO:
                logger.warning(f"RiskManager: Rejecting {symbol} - Low Liquidity (Volume {vol} is less than {RISK_MIN_VOLUME_20MA_RATIO * 100}% of 20MA {vol_20ma})")
                continue
            
            clean_sym = symbol.split(".")[0]
            sector = SECTOR_MAP.get(clean_sym, "Others")
            
            # Sector Capping Constraint
            if sectors_count.get(sector, 0) >= self.max_sector_exposure:
                logger.info(f"RiskManager: Sector capping reached for '{sector}' (Excludes {symbol})")
                continue
                
            # Position sizing
            entry = stock.get("entry")
            stop = stock.get("stop_loss")
            
            if entry and stop:
                size_info = self.calculate_position_size(entry, stop)
                if size_info["shares"] == 0:
                    logger.warning(f"RiskManager: Position sizing computed 0 shares for {symbol}. Skipping.")
                    continue
                    
                stock["risk_management"] = size_info
                
                # Check if total allocation fits within account limit
                # We allow overlapping capital since it's just recommendations, but log it
                total_allocated += size_info["allocated_capital"]
            else:
                stock["risk_management"] = {
                    "shares": 0,
                    "allocated_capital": 0.0,
                    "pct_of_account": 0.0,
                    "risk_amount": 0.0
                }
            
            if "technical_indicators" in stock:
                del stock["technical_indicators"]

            # Allocate to output
            cat_key = stock["origin_category"]
            final_picks[cat_key].append(stock)
            
            # Increment sector count
            sectors_count[sector] = sectors_count.get(sector, 0) + 1
            
        # Log allocation report
        logger.info(f"RiskManager allocation done. Total virtual capital recommended: ₹{total_allocated:,.2f}")
        return final_picks
