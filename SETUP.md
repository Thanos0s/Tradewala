# KronosIndia Setup & Architecture Guide

KronosIndia is a **100% local, offline, AI-powered stock analysis system** designed for Indian equity markets (NSE/BSE). It leverages a custom neural network for price forecasting, a local large language model (LLM) for news sentiment analysis, and headful/headless browser sessions to pull real-time data directly from public pages without requiring paid API keys.

---

## 🏗️ System Architecture

```mermaid
graph TD
    %% Scrapers / Data Sources
    subgraph Data Layer (Local Browser/APIs)
        DS1[Yahoo Finance API]
        DS2[NSE India Page]
        DS3[BSE India Page]
        DS4[Financial News Sites]
    end

    %% Fetchers
    subgraph Fetcher Pipeline
        F1[DataFetcher / yfinance] -->|Historical Prices| DS1
        F2[NSEBrowserFetcher] -->|Live Quotes & Option Chain| DS2
        F3[BSEBrowserFetcher] -->|Corporate Announcements| DS3
        F4[NewsBrowserFetcher] -->|MoneyControl & ET Markets| DS4
    end

    %% Analytics & Models
    subgraph Local Inference & Analytics
        P1[Kronos Predictor] -->|50% Weight| KM[Kronos Neural Net / EMA Fallback]
        I1[Indicator Engine] -->|18% Weight| TA[pandas_ta / TradingView Scraper]
        N1[News Analyzer] -->|15% Weight| OL[Ollama LLM / Keyword Fallback]
        F5[F&O Analyzer] -->|12% Weight| FO[PCR & Futures Buildup]
        C1[Pattern Engine] -->|5% Weight| CP[Candlestick Pattern Matching]
    end

    F1 --> P1
    F1 --> I1
    F1 --> C1
    F2 --> F5
    F3 --> N1
    F4 --> N1

    %% Orchestrator & Scoring
    Orchestrator[main.py Orchestrator]
    Score[ScoringEngine]

    P1 --> Score
    I1 --> Score
    N1 --> Score
    F5 --> Score
    C1 --> Score
    Score --> Orchestrator

    %% Output
    subgraph Output Deliverables
        Orchestrator -->|Renders| Out1[HTML Reports]
        Orchestrator -->|Serializes| Out2[dashboard_data.json]
        Orchestrator -->|Logs| Out3[WhatsApp/Email Logs]
        Out2 -->|Serves| Out4[Flask Web Dashboard]
    end
    
    style DS1 fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#fff
    style DS2 fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#fff
    style DS3 fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#fff
    style DS4 fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#fff
    style KM fill:#d35400,stroke:#e67e22,stroke-width:2px,color:#fff
    style OL fill:#d35400,stroke:#e67e22,stroke-width:2px,color:#fff
    style Score fill:#27ae60,stroke:#2ecc71,stroke-width:2px,color:#fff
    style Out4 fill:#8e44ad,stroke:#9b59b6,stroke-width:2px,color:#fff
```

---

## 🛠️ One-Time Environment Setup

### 1. Prerequisite Installations
Ensure you have the following installed on your machine:
- **Python 3.8 to 3.11** (Python 3.12+ might have minor library compatibility issues with older neural network packages).
- **Git** (for cloning the forecasting repository).

### 2. Auto-Configuration Script
The easiest way to initialize a new machine is to run our auto-setup wizard, which handles dependencies, browser configuration, repo cloning, and env setup automatically:
Run this from the repository root after cloning `https://github.com/Thanos0s/Tradewala.git`:
```bash
python setup_new_machine.py
```

### 3. Manual Step-by-Step Setup
If you prefer setting up manually, run the following steps:

#### Step A: Install Python Packages
```bash
pip install -r requirements.txt
```
The repo now includes a local `pandas_ta.py` compatibility layer, so you do not need to install the external `pandas-ta` package on Lightsail.

#### Step B: Install Playwright Browsers
To enable our browser automation layers for bypasses and scraping:
```bash
python -m playwright install chromium
```

#### Step C: Clone the Kronos Forecasting Model
```bash
git clone https://github.com/shiyu-coder/Kronos.git Kronos-repo
```

> Note: the GitHub repo root contains `main.py`, `analysis/`, `data/`, and `output/` directly. There is no `kronos_india/` subfolder after cloning `Tradewala`.
> If the files are missing on your server, run `git pull` in the repo root before setup.

---

## ⚙️ Environment Variables (`.env`)

A default `.env` is created automatically. The system requires or accepts the following keys:

| Key | Description | Default / Recommended |
|---|---|---|
| `OLLAMA_BASE_URL` | Local API endpoint for Ollama LLM | `http://localhost:11434` |
| `OLLAMA_MODEL` | LLM used for sentiment classification | `meta/llama-4-maverick-17b-128e-instruct` |
| `OLLAMA_TIMEOUT` | Seconds allowed before falling back | `120` |
| `OLLAMA_API_KEY` | Optional API Key for cloud providers (bypasses local check) | *(Keep blank for local Ollama)* |
| `TWILIO_ACCOUNT_SID` | Optional SID for sending live WhatsApps | *(Keep blank to log alerts locally)* |
| `TWILIO_AUTH_TOKEN` | Optional Twilio authorization token | *(Keep blank to log alerts locally)* |
| `WHATSAPP_FROM` | Twilio sandbox number | `whatsapp:+14155238886` |
| `WHATSAPP_TO` | Target phone number for WhatsApp alerts | `whatsapp:+91XXXXXXXXXX` |

---

## 🔄 Resiliency & Fallback Matrix

KronosIndia is built with a **graceful degradation hierarchy**. If a local database, model, or browser fails, the script recovers and falls back dynamically to prevent process crashes.

| Component | Primary Driver | Fallback Mechanism | Result on Failure |
|---|---|---|---|
| **Price Predictor** | Neural Network (`NeoQuasar/Kronos-small`) | Heuristic EMA (5-day vs 20-day EMA comparison) | Predicts trend with `mode: FALLBACK_EMA`. Performance drops, but scoring finishes. |
| **Price Data** | `yfinance` Batch Download | `yfinance` Individual Ticker Scrape | Missing tickers are downloaded separately; persistent failures are skipped safely. |
| **Option Chain** | `NSEBrowserFetcher` (Playwright) | `requests` (Cookies + HTTP Referer header session warmup) | Falls back to static HTTP queries. If NSE blocks headers, option chain drops to `{}`. |
| **NSE Ban List** | `NSEBrowserFetcher` (Playwright) | HTTP API `/api/fo-mktlots` ➔ Archives CSV | Scrapes archival CSV `fo_secban.csv` from NSE archives. |
| **News Sentiment** | `NewsBrowserFetcher` (Playwright) | Static `aiohttp` web parsing | Scrapes standard static HTML feeds. |
| **AI News Scoring** | `Ollama` LLM local analysis | Rule-based positive/negative keyword scanning | Sentiment score remains functional via local lexicon analysis. |
| **Technical Signals** | `TradingViewBrowserFetcher` (Playwright) | `tradingview_ta` library (with HTTP headers) | Queries TV widget statically. Fallback returns `NEUTRAL` if TV rate-limits. |
| **WhatsApp Alerts** | Twilio REST API request | Local file writer (`output/whatsapp_log.txt`) | Appends message content to a readable text log file locally. |

---

## 📁 Codebase Directory Structure

```text
kronos_india/
│
├── main.py                    # Master orchestrator/scheduler pipeline
├── config.py                  # Stock Watchlist, scoring weights, timeouts
├── setup_new_machine.py       # Setup wizard
├── requirements.txt           # Package specifications
│
├── kronos/                    # --- 1. FORECASTING MODEL PACKAGE ---
│   ├── predictor.py           # Wraps Kronos-small weights & handles EMA fallbacks
│   ├── finetune_nse.py        # Fine-tuning templates
│   └── models/                # Local checkpoint directory
│
├── data/                      # --- 2. DATA ACQUISITION PACKAGE ---
│   ├── browser_fetcher.py     # Playwright engines (NSE, TradingView, BSE, News)
│   ├── fetcher.py             # Historical OHLCV download & caching
│   ├── fo_fetcher.py          # Option chain, PCR, F&O ban, futures activity
│   ├── news_scraper.py        # Combines browser scrapers with static fallback scrapers
│   └── cache/                 # Local data storage (.parquet files)
│
├── analysis/                  # --- 3. ANALYTICAL LAYER ---
│   ├── indicators.py          # Technical indicator math (pandas_ta) & TradingView data
│   ├── news_analyzer.py       # Coordinates Ollama local sentiment processing
│   ├── fo_analyzer.py         # Evaluates derivatives data
│   └── scoring_engine.py      # Weights components & generates the final 100-point rank
│
└── output/                    # --- 4. PRESENTATION & DELIVERABLES ---
    ├── dashboard.py           # Web Dashboard server (Flask-based)
    ├── report_builder.py      # Generates modern HTML files
    ├── whatsapp_sender.py     # Communicates picks to Twilio API or local files
    ├── reports/               # HTML report archives
    └── static/                # Dashboard/Report CSS stylesheets
```

---

## 🚀 Running the System

### 1. Run the Analysis Orchestrator
Running the orchestrator fetches the latest price, news, and derivative figures, scores all 81 watchlist stocks, and saves the ranking dataset:
```bash
python main.py
```
*Outputs generated:*
- `output/reports/report_YYYYMMDD.html` (Interactive premium HTML sheet)
- `output/dashboard_data.json` (Serialized dataset consumed by the Flask server)
- Updates `output/email_log.txt` and `output/whatsapp_log.txt`

### 2. Start the Live Web Dashboard
Boot up the premium dark-themed web server locally:
```bash
python -m output.dashboard
```
Open your browser and navigate to:
```text
http://127.0.0.1:5000
```
This displays color-coded tables categorized by Swing picks, Intraday opportunities, and High-Risk opportunities.
