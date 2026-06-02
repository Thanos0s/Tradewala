import logging

logger = logging.getLogger("GlobalImpact")

class GlobalImpactEngine:
    """
    Evaluates global market indexes and macro factors to dynamically calculate 
    thematic biases and score modifiers for domestic sectors.
    """

    def __init__(self):
        pass

    def calculate_biases(self, global_indicators: dict) -> dict:
        """
        Maps global indicators to specific domestic sector biases.
        Returns:
            {
                "sector_modifiers": {"IT": float, "Chemicals": float, "Gold": float},
                "general_modifier": float,
                "reasons": list[str]
            }
        """
        sector_modifiers = {"IT": 0.0, "Chemicals": 0.0, "Gold": 0.0}
        general_modifier = 0.0
        reasons = []

        if not global_indicators:
            return {
                "sector_modifiers": sector_modifiers,
                "general_modifier": general_modifier,
                "reasons": ["No global market indicator data available."]
            }

        # 1. Nasdaq -> Indian IT Sector
        nasdaq = global_indicators.get("nasdaq", {})
        nasdaq_ret = nasdaq.get("return_1d", 0.0)
        if nasdaq_ret > 0.5:
            sector_modifiers["IT"] = 5.0
            reasons.append(f"Nasdaq closed strong ({nasdaq_ret:+.2f}%) - Positive IT sector bias added.")
        elif nasdaq_ret < -0.5:
            sector_modifiers["IT"] = -5.0
            reasons.append(f"Nasdaq closed weak ({nasdaq_ret:+.2f}%) - Negative IT sector bias applied.")

        # 2. Shanghai Composite -> Indian Specialty Chemicals
        # Often a weaker Chinese market indicates chemical factory output reductions, favoring Indian competitors.
        shanghai = global_indicators.get("shanghai", {})
        shanghai_ret = shanghai.get("return_1d", 0.0)
        if shanghai_ret < -0.5:
            sector_modifiers["Chemicals"] = 4.0
            reasons.append(f"China Shanghai Index weak ({shanghai_ret:+.2f}%) - Competitor breakout potential for Indian Specialty Chemicals.")

        # 3. Gold Futures -> Gold ETFs
        gold = global_indicators.get("gold", {})
        gold_ret = gold.get("return_1d", 0.0)
        if gold_ret > 0.5:
            sector_modifiers["Gold"] = 6.0
            reasons.append(f"Gold Futures surged ({gold_ret:+.2f}%) - Boosted defensive Gold ETF bias.")

        # 4. US Dollar Index (DXY) -> Emerging Market Pressure
        dxy = global_indicators.get("dxy", {})
        dxy_ret = dxy.get("return_1d", 0.0)
        if dxy_ret > 0.3:
            general_modifier = -3.0
            reasons.append(f"US Dollar Index strengthened ({dxy_ret:+.2f}%) - Increased capital outflow pressure on emerging markets.")
        elif dxy_ret < -0.3:
            general_modifier = 3.0
            reasons.append(f"US Dollar Index weakened ({dxy_ret:+.2f}%) - Relief rally support for emerging markets.")

        return {
            "sector_modifiers": sector_modifiers,
            "general_modifier": general_modifier,
            "reasons": reasons
        }
