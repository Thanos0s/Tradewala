from flask import Flask, render_template, jsonify
import os
import json
import logging

app = Flask(__name__)

# Determine path to dashboard JSON data
DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output', 'dashboard_data.json'))

def load_data():
    if not os.path.exists(DATA_PATH):
        logging.warning(f"Dashboard data file not found at {DATA_PATH}")
        return {
            "regime_info": {"regime": "UNKNOWN", "reason": "No data file", "vix": 15.0, "pcr": 1.0, "nifty_trend": "NEUTRAL"},
            "picks": {"intraday_picks": [], "high_risk_picks": [], "swing_picks": []}
        }
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # Backward compatibility check
            if isinstance(data, dict) and "intraday_picks" in data and "picks" not in data:
                return {
                    "regime_info": {"regime": "UNKNOWN", "reason": "Old format", "vix": 15.0, "pcr": 1.0, "nifty_trend": "NEUTRAL"},
                    "picks": data
                }
            return data
        except Exception as e:
            logging.error(f"Error loading dashboard data: {e}")
            return {
                "regime_info": {"regime": "ERROR", "reason": str(e), "vix": 15.0, "pcr": 1.0, "nifty_trend": "NEUTRAL"},
                "picks": {"intraday_picks": [], "high_risk_picks": [], "swing_picks": []}
            }

@app.route('/')
def index():
    data = load_data()
    return render_template('dashboard.html', regime=data.get("regime_info", {}), picks=data.get("picks", {}))

@app.route('/api/data')
def api_data():
    return jsonify(load_data())

if __name__ == '__main__':
    # Run on localhost:5000, enable debug for auto-reload during development
    app.run(host='127.0.0.1', port=5000, debug=True)
