import logging
import pandas as pd
import numpy as np

logger = logging.getLogger("Microstructure")

class MicrostructureEngine:
    """
    ⚡ Microstructure Analysis & Event-Driven Spike Engine
    Detects institutional / smart money moves, filters retail noise, and computes order book metrics.
    """

    def __init__(self, imbalance_threshold: float = 0.2):
        self.imbalance_threshold = imbalance_threshold

    def calculate_vwap_deviation(self, price: float, vwap: float) -> float:
        """Calculate percentage deviation of price from VWAP."""
        if not vwap or vwap == 0:
            return 0.0
        return ((price - vwap) / vwap) * 100.0

    def calculate_bid_ask_spread(self, best_bid: float, best_ask: float) -> float:
        """Calculate best bid-ask spread percentage relative to mid price."""
        if not best_bid or not best_ask:
            return 0.0
        mid = (best_bid + best_ask) / 2.0
        if mid == 0:
            return 0.0
        return ((best_ask - best_bid) / mid) * 100.0

    def calculate_orderbook_imbalance(self, total_bid_qty: float, total_ask_qty: float) -> float:
        """
        Calculate bid-ask order book imbalance.
        Range: -1.0 (pure ask side dominance) to +1.0 (pure bid side dominance).
        """
        denominator = total_bid_qty + total_ask_qty
        if denominator == 0:
            return 0.0
        return (total_bid_qty - total_ask_qty) / denominator

    def detect_spike_event(
        self,
        price_change_1min: float,
        volume_1min: float,
        avg_volume_1min: float,
        bid_ask_imbalance: float,
        delivery_percent_rising: bool
    ) -> bool:
        """
        ⚡ Event-Driven Spike Engine Trigger.
        Filters retail noise and operator traps to flag institutional order flows.
        """
        is_price_spike = price_change_1min >= 1.2
        is_volume_spike = volume_1min > 2.5 * avg_volume_1min
        is_imbalance_valid = bid_ask_imbalance > self.imbalance_threshold
        
        is_triggered = (
            is_price_spike and
            is_volume_spike and
            is_imbalance_valid and
            delivery_percent_rising
        )
        
        if is_triggered:
            logger.info(
                f"🔥 institutional event triggered! "
                f"Change: {price_change_1min:.2f}%, Vol ratio: {volume_1min/max(1, avg_volume_1min):.1f}x, "
                f"Imbalance: {bid_ask_imbalance:.2f}"
            )
            
        return is_triggered

    def analyze_market_depth(self, market_depth: dict) -> dict:
        """
        Extract metrics from raw market depth / L2 order book payload.
        Expects: { "buy": [{"price": p, "quantity": q}], "sell": [...] } or similar.
        """
        try:
            buy_orders = market_depth.get("buy", []) or market_depth.get("buy_depth", [])
            sell_orders = market_depth.get("sell", []) or market_depth.get("sell_depth", [])
            
            total_bid_qty = sum(item.get("quantity", item.get("quantity", 0)) for item in buy_orders)
            total_ask_qty = sum(item.get("quantity", item.get("quantity", 0)) for item in sell_orders)
            
            best_bid = buy_orders[0].get("price", 0.0) if buy_orders else 0.0
            best_ask = sell_orders[0].get("price", 0.0) if sell_orders else 0.0
            
            spread = self.calculate_bid_ask_spread(best_bid, best_ask)
            imbalance = self.calculate_orderbook_imbalance(total_bid_qty, total_ask_qty)
            
            return {
                "total_bid_quantity": total_bid_qty,
                "total_ask_quantity": total_ask_qty,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_ask_spread_pct": round(spread, 4),
                "orderbook_imbalance": round(imbalance, 4),
                "imbalance_threshold": self.imbalance_threshold
            }
        except Exception as e:
            logger.error(f"Error analyzing market depth: {e}")
            return {
                "total_bid_quantity": 0,
                "total_ask_quantity": 0,
                "best_bid": 0.0,
                "best_ask": 0.0,
                "bid_ask_spread_pct": 0.0,
                "orderbook_imbalance": 0.0,
                "imbalance_threshold": self.imbalance_threshold
            }
