# KronosIndia

KronosIndia is a local, offline-first stock analysis pipeline for Indian markets. It combines price history, news, F&O context, technical indicators, a local Kronos predictor, XGBoost scoring, regime filtering, and ATR-based risk sizing to produce ranked trade ideas and a dashboard-ready output set.

## What It Does

- Pulls market data from `yfinance`, browser-based scrapers, and optional Upstox integrations.
- Runs local analytics with `pandas_ta`, XGBoost, and the Kronos PyTorch predictor.
- Applies regime-aware scoring for trending, sideways, and volatile markets.
- Uses a feedback loop to update trade outcomes in SQLite before the next scan.
- Exports HTML reports, JSON dashboard data, and alert logs for the local UI.

## Main Entry Points

- `main.py` orchestrates the full pipeline.
- `output/dashboard.py` serves the local Flask dashboard on `http://127.0.0.1:5000`.
- `setup_new_machine.py` bootstraps a fresh machine.
- `SETUP.md` covers installation and environment configuration.
- `kronos_architecture_guide.md` explains the system design in detail.

## Pipeline Overview

1. Update the trade journal and resolve pending trades.
2. Fetch prices, news, F&O signals, and global context.
3. Run the Kronos predictor, XGBoost classifier, and indicator engine.
4. Apply regime filtering and scoring.
5. Size positions with the risk engine and allocate the portfolio.
6. Render HTML reports, write dashboard JSON, and send alerts.

## Quick Start

```bash
python setup_new_machine.py
python main.py
python -m output.dashboard
```

For a lighter validation run:

```bash
python main.py --limit 5
```

## Output Files

- `output/reports/report_YYYYMMDD.html`
- `output/dashboard_data.json`
- `data/trading_journal.db`
- `output/whatsapp_log.txt`
- `output/email_log.txt`

## Documentation

- [Architecture Guide](./kronos_architecture_guide.md)
- [Setup Guide](./SETUP.md)
