import logging
from data.fo_fetcher import FOFetcher

class FOAnalyzer:
    """Wraps FOFetcher to produce concise signals for scoring engine."""

    def __init__(self):
        self.fetcher = FOFetcher()
        logging.info("FOAnalyzer initialized")

    def get_nifty_signals(self):
        """Fetch Nifty option chain and compute PCR, max pain, highest OI strikes."""
        chain = self.fetcher.get_option_chain(symbol="NIFTY")
        pcr = self.fetcher.calculate_pcr(chain)
        raw_pcr = pcr
        pcr_valid = pcr is not None
        if not pcr_valid:
            logging.warning("Nifty PCR unavailable or invalid. Falling back to neutral PCR=1.0 for regime/scoring.")
            pcr = 1.0
        max_pain = self.fetcher.calculate_max_pain(chain)
        oi_strikes = self.fetcher.get_highest_oi_strikes(chain)
        return {
            "nifty_pcr": pcr,
            "nifty_pcr_raw": raw_pcr,
            "nifty_pcr_valid": pcr_valid,
            "nifty_max_pain": max_pain,
            "nifty_resistance_ce": oi_strikes.get("ce_resistance"),
            "nifty_support_pe": oi_strikes.get("pe_support"),
            "nifty_ce_oi": oi_strikes.get("ce_oi"),
            "nifty_pe_oi": oi_strikes.get("pe_oi"),
        }

    def get_banknifty_signals(self):
        """Fetch BankNifty option chain and compute PCR."""
        chain = self.fetcher.get_banknifty_option_chain() if hasattr(self.fetcher, 'get_banknifty_option_chain') else self.fetcher.get_option_chain(symbol="BANKNIFTY")
        pcr = self.fetcher.calculate_pcr(chain)
        pcr_valid = pcr is not None
        if not pcr_valid:
            pcr = 1.0
        return {"banknifty_pcr": pcr, "banknifty_pcr_valid": pcr_valid}

    def get_futures_activity(self, symbols):
        """Return futures activity classification for given symbols."""
        return self.fetcher.get_stock_futures_activity(symbols)

    def get_ban_list(self):
        """Return today's F&O ban list."""
        return self.fetcher.get_fo_ban_list()
