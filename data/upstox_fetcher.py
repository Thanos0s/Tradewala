import os
import requests
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class UpstoxFetcher:
    """
    Official Upstox API v2 Fetcher for Option Chain and Market Data.
    Provides authenticated, reliable access to NIFTY and BANKNIFTY data.
    """

    # Map symbols to Upstox instrument keys
    SYMBOL_MAP = {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
        "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT"
    }

    def __init__(self):
        load_dotenv()
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        self.api_key = os.getenv("UPSTOX_API_KEY")
        self.api_secret = os.getenv("UPSTOX_API_SECRET")
        
        if not self.access_token:
            logging.warning("UpstoxFetcher: UPSTOX_ACCESS_TOKEN is missing in .env. Upstox API will not be used.")
        else:
            logging.info("UpstoxFetcher: Initialized successfully with access token.")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "accept": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }

    def get_expiries(self, instrument_key: str) -> List[str]:
        """Fetch and return sorted list of unique expiry dates for the instrument."""
        if not self.access_token:
            return []
        
        url = f"https://api.upstox.com/v2/option/contract?instrument_key={instrument_key}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=10)
            if resp.status_code == 401:
                logging.error("UpstoxFetcher: Access token is expired or unauthorized (401).")
                return []
                
            resp.raise_for_status()
            contracts = resp.json().get("data", [])
            
            # Extract unique expiry dates and sort them ascending
            expiries = sorted(list(set(c.get("expiry") for c in contracts if c.get("expiry"))))
            return expiries
        except Exception as e:
            logging.error(f"UpstoxFetcher: Error fetching contracts/expiries: {e}")
            return []

    def get_option_chain(self, symbol: str) -> Optional[Dict]:
        """
        Fetch option chain for a given symbol and map it to NSE-like format
        for backward compatibility.
        """
        symbol_upper = symbol.upper()
        if symbol_upper not in self.SYMBOL_MAP:
            logging.warning(f"UpstoxFetcher: Symbol {symbol_upper} not supported by Upstox mapping. Falling back.")
            return None

        if not self.access_token:
            logging.warning("UpstoxFetcher: No access token available. Falling back.")
            return None

        instrument_key = self.SYMBOL_MAP[symbol_upper]
        
        # 1. Fetch available expiries
        logging.info(f"UpstoxFetcher: Getting expiries for {symbol_upper} ({instrument_key})...")
        expiries = self.get_expiries(instrument_key)
        if not expiries:
            logging.warning(f"UpstoxFetcher: No expiries found for {symbol_upper}. Falling back.")
            return None

        nearest_expiry = expiries[0]
        logging.info(f"UpstoxFetcher: Nearest expiry is {nearest_expiry}")

        # 2. Fetch Option Chain for nearest expiry
        chain_url = f"https://api.upstox.com/v2/option/chain?instrument_key={instrument_key}&expiry_date={nearest_expiry}"
        try:
            resp = requests.get(chain_url, headers=self._get_headers(), timeout=10)
            resp.raise_for_status()
            
            chain_data = resp.json()
            raw_items = chain_data.get("data", [])
            logging.info(f"UpstoxFetcher: Fetched {len(raw_items)} option strikes for {symbol_upper}.")
            
            # 3. Map Upstox structure to NSE structure
            # NSE structure format:
            # {
            #   "records": {
            #     "data": [
            #       {
            #         "strikePrice": 22000,
            #         "expiryDate": "02-Jun-2026",
            #         "CE": { "strikePrice": 22000, "openInterest": 100, "lastPrice": 150.0, ... },
            #         "PE": { ... }
            #       }
            #     ],
            #     "expiryDates": ["02-Jun-2026", ...]
            #   }
            # }
            nse_data_list = []
            for item in raw_items:
                strike_price = item.get("strike_price", 0)
                call_opt = item.get("call_options")
                put_opt = item.get("put_options")
                
                ce_data = {}
                if call_opt:
                    market_data = call_opt.get("market_data", {})
                    option_greeks = call_opt.get("option_greeks", {})
                    ce_data = {
                        "strikePrice": int(strike_price),
                        "openInterest": int(market_data.get("oi", 0)),
                        "lastPrice": float(market_data.get("ltp", 0.0)),
                        "change": float(market_data.get("change", 0.0)),
                        "pchange": float(market_data.get("p_change", 0.0)),
                        "totalTradedVolume": int(market_data.get("volume", 0)),
                        "impliedVolatility": float(option_greeks.get("iv", 0.0) if option_greeks else 0.0),
                    }
                    
                pe_data = {}
                if put_opt:
                    market_data = put_opt.get("market_data", {})
                    option_greeks = put_opt.get("option_greeks", {})
                    pe_data = {
                        "strikePrice": int(strike_price),
                        "openInterest": int(market_data.get("oi", 0)),
                        "lastPrice": float(market_data.get("ltp", 0.0)),
                        "change": float(market_data.get("change", 0.0)),
                        "pchange": float(market_data.get("p_change", 0.0)),
                        "totalTradedVolume": int(market_data.get("volume", 0)),
                        "impliedVolatility": float(option_greeks.get("iv", 0.0) if option_greeks else 0.0),
                    }
                    
                nse_data_list.append({
                    "strikePrice": int(strike_price),
                    "expiryDate": nearest_expiry,
                    "CE": ce_data,
                    "PE": pe_data
                })
                
            # Reformat expiry dates list for compatibility
            mapped_chain = {
                "records": {
                    "data": nse_data_list,
                    "expiryDates": expiries
                }
            }
            return mapped_chain
            
        except Exception as e:
            logging.error(f"UpstoxFetcher: Error fetching/parsing option chain: {e}")
            return None
