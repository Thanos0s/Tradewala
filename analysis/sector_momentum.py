import logging
from analysis.risk_manager import SECTOR_MAP

logger = logging.getLogger(__name__)

class SectorMomentumEngine:
    """
    Groups scored stocks by sector and calculates aggregate sector momentum
    to identify industry breakouts.
    """

    def __init__(self):
        logger.info("SectorMomentumEngine initialized")

    def calculate_sector_momentum(self, scored_stocks: list) -> dict:
        """
        Groups stock list by sector and returns momentum ratings,
        triggering high strength if >= 3 stocks in same sector are bullish.
        """
        sectors = {}
        for stock in scored_stocks:
            symbol = stock["symbol"]
            clean_sym = symbol.split(".")[0]
            sector = SECTOR_MAP.get(clean_sym, "Others")
            
            if sector not in sectors:
                sectors[sector] = {
                    "stocks": [],
                    "total_score": 0.0,
                    "bullish_count": 0
                }
                
            score = stock.get("total_score", 0.0)
            sectors[sector]["stocks"].append(stock)
            sectors[sector]["total_score"] += score
            if score >= 55.0:
                sectors[sector]["bullish_count"] += 1

        sector_summary = []
        for sector, data in sectors.items():
            num_stocks = len(data["stocks"])
            if num_stocks == 0:
                continue
                
            avg_score = round(data["total_score"] / num_stocks, 1)
            bullish_count = data["bullish_count"]
            
            # Momentum classification
            if bullish_count >= 3:
                momentum_rating = "HIGH"
                momentum_val = 80 + min(20, bullish_count * 5)
            elif bullish_count >= 1:
                momentum_rating = "MODERATE"
                momentum_val = 50 + (bullish_count * 10)
            else:
                momentum_rating = "LOW"
                momentum_val = max(10, int(avg_score * 0.5))

            # Leaders: Sort stocks by score descending
            sorted_stocks = sorted(data["stocks"], key=lambda x: x.get("total_score", 0), reverse=True)
            leaders = [s["symbol"].split(".")[0] for s in sorted_stocks[:3]]

            sector_summary.append({
                "sector": sector,
                "avg_score": avg_score,
                "bullish_count": bullish_count,
                "momentum": momentum_val,
                "momentum_rating": momentum_rating,
                "leaders": leaders
            })

        # Sort sectors by momentum value descending
        sector_summary = sorted(sector_summary, key=lambda x: x["momentum"], reverse=True)
        
        logger.info(f"SectorMomentumEngine computed data for {len(sector_summary)} sectors.")
        return {
            "sectors": sector_summary,
            "top_sector": sector_summary[0]["sector"] if sector_summary else "None"
        }
