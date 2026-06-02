import logging
import os
from datetime import datetime, timedelta

LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output', 'whatsapp_log.txt'))

# Cooldown tracking
_last_alert_times = {}
COOLDOWN_PERIOD = timedelta(minutes=5)

def send_whatsapp_message(message: str) -> None:
    """Standard daily summary alert."""
    _write_log(f"[INFO] {message}")

def send_priority_alert(symbol: str, message: str, priority: str = "NORMAL") -> bool:
    """
    Sends WhatsApp alert with priority checks and rate-limiting cooldowns per symbol.
    Returns True if alert was sent, False if rate-limited.
    """
    now = datetime.now()
    
    # Check cooldown only for non-critical alerts
    if priority != "CRITICAL":
        last_sent = _last_alert_times.get(symbol)
        if last_sent and (now - last_sent) < COOLDOWN_PERIOD:
            logging.info(f"Alert for {symbol} suppressed due to active cooldown.")
            return False
            
    _last_alert_times[symbol] = now
    alert_text = f"[{priority}] {message}"
    _write_log(alert_text)
    return True

def _write_log(text: str) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] {text}\n"
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(entry)
    logging.info(f"WhatsApp placeholder log updated: {LOG_FILE}")

