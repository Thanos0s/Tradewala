import asyncio
import random
import logging
from datetime import datetime
from typing import Dict, List, Callable
from analysis.microstructure import MicrostructureEngine
from config import NSE_WATCHLIST

logger = logging.getLogger("LiveWorker")

class LiveDataWorker:
    """
    Manages live market feed (real/simulated), runs real-time microstructure calculations,
    and broadcasts updates to WebSocket subscribers.
    """

    def __init__(self, imbalance_threshold: float = 0.2):
        self.subscribers: List[Callable] = []
        self.micro_engine = MicrostructureEngine(imbalance_threshold=imbalance_threshold)
        self.running = False
        self.symbols = NSE_WATCHLIST[:10]  # Focus live monitoring on top 10 tickers
        self.history: Dict[str, List[dict]] = {sym: [] for sym in self.symbols}
        self.market_depth_cache: Dict[str, dict] = {}
        
        # Initialize baseline data
        for sym in self.symbols:
            self.market_depth_cache[sym] = self._generate_mock_depth(sym, 100.0)

    def subscribe(self, callback: Callable):
        """Register a callback for live updates."""
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """Remove a registered callback."""
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    async def broadcast(self, payload: dict):
        """Broadcast payload to all active WebSocket connections."""
        for cb in self.subscribers:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as e:
                logger.error(f"Error broadcasting to subscriber: {e}")

    def _generate_mock_depth(self, symbol: str, price: float) -> dict:
        """Helper to generate mock L2 order book depth."""
        spread = random.uniform(0.05, 0.20)
        best_bid = price - (spread / 2)
        best_ask = price + (spread / 2)
        
        buy_qty = random.randint(1000, 5000)
        sell_qty = random.randint(1000, 5000)
        
        return {
            "buy": [{"price": round(best_bid, 2), "quantity": buy_qty}],
            "sell": [{"price": round(best_ask, 2), "quantity": sell_qty}]
        }

    async def start(self):
        """Start the live market data worker loop."""
        self.running = True
        logger.info("Starting Live Market Data Worker...")
        asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the live market data worker loop."""
        self.running = False
        logger.info("Live Market Data Worker stopped.")

    async def _run_loop(self):
        """Continuous simulation/real-time tracking loop."""
        # Simulated live prices mapping
        prices = {sym: random.uniform(200.0, 3000.0) for sym in self.symbols}
        vwap = {sym: prices[sym] for sym in self.symbols}
        ticks_count = {sym: 0 for sym in self.symbols}
        
        # Track 1-minute historical prices for spike detection
        avg_volume_1min = {sym: 2000.0 for sym in self.symbols}
        last_minute_prices = {sym: prices[sym] for sym in self.symbols}
        
        while self.running:
            try:
                # Pick a random stock to simulate a new tick update
                symbol = random.choice(self.symbols)
                price = prices[symbol]
                
                # Tick change simulation
                change = random.uniform(-0.005, 0.005)
                # Inject occasional smart-money spikes for testing
                if random.random() < 0.05:
                    change = random.uniform(0.015, 0.03)  # 1.5% to 3% spike
                
                new_price = round(price * (1 + change), 2)
                prices[symbol] = new_price
                
                tick_vol = random.randint(500, 6000)
                ticks_count[symbol] += 1
                
                # Update VWAP
                vwap[symbol] = round(((vwap[symbol] * (ticks_count[symbol] - 1)) + new_price) / ticks_count[symbol], 2)
                
                # Mock order depth
                depth = self._generate_mock_depth(symbol, new_price)
                depth_metrics = self.micro_engine.analyze_market_depth(depth)
                
                # VWAP Deviation
                vwap_dev = self.micro_engine.calculate_vwap_deviation(new_price, vwap[symbol])
                
                # Calculate 1-min change & Spike Detection
                price_change_1min = ((new_price - last_minute_prices[symbol]) / last_minute_prices[symbol]) * 100.0
                delivery_rising = random.choice([True, False])  # mock delivery flag
                
                spike_triggered = self.micro_engine.detect_spike_event(
                    price_change_1min=price_change_1min,
                    volume_1min=float(tick_vol),
                    avg_volume_1min=avg_volume_1min[symbol],
                    bid_ask_imbalance=depth_metrics["orderbook_imbalance"],
                    delivery_percent_rising=delivery_rising
                )

                if spike_triggered:
                    try:
                        from output.whatsapp_sender import send_priority_alert
                        send_priority_alert(
                            symbol=symbol,
                            message=f"Institutional spike triggered in {symbol}! Price: {new_price}, Vol Ratio: {tick_vol/max(1, avg_volume_1min[symbol]):.1f}x",
                            priority="HIGH"
                        )
                    except Exception as alert_err:
                        logger.error(f"Failed to send priority alert: {alert_err}")
                
                # Update 1-minute reference price
                if ticks_count[symbol] % 10 == 0:
                    last_minute_prices[symbol] = new_price
                    avg_volume_1min[symbol] = (avg_volume_1min[symbol] * 0.9) + (tick_vol * 0.1)

                payload = {
                    "symbol": symbol,
                    "price": new_price,
                    "vwap": vwap[symbol],
                    "vwap_deviation_pct": round(vwap_dev, 4),
                    "bid_ask_spread_pct": depth_metrics["bid_ask_spread_pct"],
                    "orderbook_imbalance": depth_metrics["orderbook_imbalance"],
                    "best_bid": depth_metrics["best_bid"],
                    "best_ask": depth_metrics["best_ask"],
                    "volume": tick_vol,
                    "spike_triggered": spike_triggered,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                }
                
                # Store history
                self.history[symbol].append(payload)
                if len(self.history[symbol]) > 50:
                    self.history[symbol].pop(0)
                    
                await self.broadcast(payload)
                
            except Exception as e:
                logger.error(f"Error in LiveWorker loop: {e}")
                
            await asyncio.sleep(0.5)  # Tick frequency: every 500ms
