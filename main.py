import argparse
import logging
import os
import sys
from datetime import datetime



# Project imports
from data.fetcher import fetch_price_data
from data.news_scraper import scrape_news
from kronos.predictor import KronosStockPredictor as KronosPredictor
from analysis.indicators import IndicatorEngine
from analysis.news_analyzer import NewsAnalyzer
from analysis.fo_analyzer import FOAnalyzer
from analysis.scoring_engine import ScoringEngine
from analysis.regime_filter import RegimeFilter
from analysis.risk_manager import RiskManager
from output.report_builder import render_report
from output.whatsapp_sender import send_whatsapp_message

# Optional email placeholder
def send_email_placeholder(subject: str, body: str):
    """Placeholder email sender – writes to a log file."""
    log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'output', 'email_log.txt'))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] SUBJECT: {subject}\n{body}\n\n")
    logging.info(f"Email placeholder log updated: {log_path}")


def run_pipeline(limit=None):
    """Execute the full data‑fetch → prediction → scoring → output pipeline."""
    logging.info("Starting KronosIndia pipeline")

    # 0️⃣ Update previously pending trades and print performance summary
    try:
        from data.trade_logger import (
            update_pending_trades,
            log_new_trades,
            print_performance_summary,
            print_confidence_calibration_summary,
        )
        update_pending_trades()
        print_performance_summary()
        print_confidence_calibration_summary()
    except Exception as e:
        logging.error(f"Failed to update trading journal: {e}")

    # 1️⃣ Fetch raw market data for the watchlist (returns dict of {symbol: DataFrame})
    if limit is not None:
        from config import NSE_WATCHLIST
        watchlist = NSE_WATCHLIST[:limit]
        logging.info(f"Test run: limiting watchlist to first {limit} symbols: {watchlist}")
        price_df = fetch_price_data(symbols=watchlist)
    else:
        price_df = fetch_price_data()

    # 2️⃣ Fetch news articles and perform sentiment analysis
    news_data = scrape_news()
    news_analyzer = NewsAnalyzer()
    news_result = news_analyzer.analyze(news_data, list(price_df.keys()))

    # 3️⃣ Fetch F&O data signals
    fo_analyzer = FOAnalyzer()
    fo_result = fo_analyzer.get_nifty_signals()
    ban_list = fo_analyzer.get_ban_list()

    # 3.2️⃣ Determine market regime
    regime_filter = RegimeFilter()
    regime_info = regime_filter.get_market_regime(fo_result)

    # 3.5️⃣ Pre-fetch TradingView indicators (Browser task)
    indicator_engine = IndicatorEngine()
    logging.info("Pre-fetching TradingView analysis for all symbols...")
    indicator_engine.prefetch_tradingview_analysis(list(price_df.keys()))

    # 3.8️⃣ Fetch global indicators and evaluate impact
    try:
        from data.fetcher import fetch_global_indicators
        from analysis.global_impact import GlobalImpactEngine
        global_data = fetch_global_indicators()
        global_engine = GlobalImpactEngine()
        global_modifiers = global_engine.calculate_biases(global_data)
        logging.info(f"Global macro biases computed: {global_modifiers.get('reasons', [])}")
    except Exception as e:
        logging.error(f"Failed to compute global impact: {e}")
        global_modifiers = None

    # 4️⃣ Load Kronos model and get predictions
    predictor = KronosPredictor()
    kronos_results = predictor.predict(price_df)

    # 5️⃣ Initialise scoring engine and score each symbol
    scoring_engine = ScoringEngine(indicator_engine, news_analyzer, fo_analyzer)
    scored = []
    for symbol in price_df.keys():
        kronos_res = kronos_results.get(symbol, {})
        df_symbol = price_df[symbol]
        stock_score = scoring_engine.score_stock(
            symbol=symbol,
            kronos_result=kronos_res,
            df=df_symbol,
            news_result=news_result,
            fo_result=fo_result,
            ban_list=ban_list,
            regime_info=regime_info,
            news_data=news_data,
            global_modifiers=global_modifiers,
        )
        if stock_score:
            scored.append(stock_score)

    # 5.5️⃣ Filter stocks based on regime rules
    filtered_scored = regime_filter.apply_regime_filtering(scored, regime_info)

    # 6️⃣ Rank and pick stocks
    picks = scoring_engine.rank_stocks(filtered_scored)

    # 6.2️⃣ Calculate Sector Momentum
    try:
        from analysis.sector_momentum import SectorMomentumEngine
        sector_engine = SectorMomentumEngine()
        sector_momentum = sector_engine.calculate_sector_momentum(scored)
    except Exception as e:
        logging.error(f"Failed to calculate sector momentum: {e}")
        sector_momentum = {"sectors": [], "top_sector": "None"}

    # 6.5️⃣ Apply Risk Management & Position Sizing
    from config import (
        RISK_ACCOUNT_EQUITY,
        RISK_PER_TRADE_PCT,
        RISK_MAX_ALLOCATION_PCT,
        RISK_MAX_SECTOR_EXPOSURE
    )
    risk_manager = RiskManager(
        account_equity=RISK_ACCOUNT_EQUITY,
        risk_per_trade_pct=RISK_PER_TRADE_PCT,
        max_trade_allocation_pct=RISK_MAX_ALLOCATION_PCT,
        max_sector_exposure=RISK_MAX_SECTOR_EXPOSURE
    )
    final_picks = risk_manager.allocate_portfolio(picks)

    # 6.6️⃣ Log new trades in the database journal
    try:
        log_new_trades(final_picks, regime_info)
    except Exception as e:
        logging.error(f"Failed to log new recommendations to journal: {e}")

    # 7️⃣ Generate HTML report
    report_path = render_report(final_picks)

    # 8️⃣ Write dashboard data JSON for Flask UI
    import json
    dashboard_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'output', 'dashboard_data.json'))
    os.makedirs(os.path.dirname(dashboard_path), exist_ok=True)
    
    output_data = {
        "regime_info": regime_info,
        "picks": final_picks,
        "sector_momentum": sector_momentum,
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    logging.info(f"Dashboard data written to {dashboard_path}")

    # 9️⃣ Send WhatsApp placeholder message
    message = f"KronosIndia daily picks generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Report: {report_path}"
    send_whatsapp_message(message)

    # 🔟 Send email placeholder (optional channel)
    send_email_placeholder("KronosIndia Daily Picks", message)

    logging.info("Pipeline completed successfully")
    return picks, report_path


def main():
    parser = argparse.ArgumentParser(description="KronosIndia orchestrator")
    parser.add_argument("--once", action="store_true", help="Run pipeline once and exit (default is scheduled daily)")
    parser.add_argument("--limit", type=int, default=None, help="Limit watchlist to first N stocks for testing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logging.info("Running pipeline immediately (scheduling disabled)")
    run_pipeline(limit=args.limit)

if __name__ == "__main__":
    main()
