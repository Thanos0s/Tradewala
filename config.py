import os
from dotenv import load_dotenv

load_dotenv()

# --- STOCK UNIVERSE ---
NSE_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "LT.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
    "SUNPHARMA.NS", "WIPRO.NS", "HCLTECH.NS", "BAJFINANCE.NS", "NTPC.NS",
    "ADANIPORTS.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
    "TECHM.NS", "DRREDDY.NS", "DIVISLAB.NS", "CIPLA.NS", "GRASIM.NS",
    "EICHERMOT.NS", "BAJAJFINSV.NS", "BPCL.NS", "COALINDIA.NS", "TATAMOTORS.BO",
    "TATACONSUM.NS", "HEROMOTOCO.NS", "APOLLOHOSP.NS", "BRITANNIA.NS",
    "JSWSTEEL.NS", "ONGC.NS", "TATASTEEL.NS", "HINDALCO.NS", "M&M.NS",
    "ADANIENT.NS", "SHREECEM.NS", "INDUSINDBK.NS", "TATAPOWER.NS",
    "IRCTC.NS", "PIDILITIND.NS", "HAVELLS.NS", "POLYCAB.NS", "NAUKRI.NS",
    "OFSS.NS", "PERSISTENT.NS", "LTIM.BO", "ZOMATO.BO", "PAYTM.NS",
    "DMART.NS", "COLPAL.NS", "MARICO.NS", "GODREJCP.NS", "DABUR.NS",
    "BALKRISIND.NS", "CUMMINSIND.NS", "SOLARINDS.NS", "ASTRAL.NS",
    "SUPREMEIND.NS", "LUPIN.NS", "TORNTPHARM.NS", "ALKEM.NS",
    "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "FEDERALBNK.NS",
    "IDFCFIRSTB.NS", "BANDHANBNK.NS", "AUBANK.NS", "PAGEIND.NS",
    "WHIRLPOOL.NS", "DIXON.NS", "AMBER.NS",
]

THEMATIC_STOCK_WATCHLIST = [
    # Defence & aerospace
    "HAL.NS", "BEL.NS", "BDL.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
    "GRSE.NS", "DATAPATTNS.NS", "ASTRAMICRO.NS", "BEML.NS",
    "PARASDEF.NS", "ZENTEC.NS", "MIDHANI.NS", "MTARTECH.NS",
    "APOLLOMICRO.NS", "BFUTILITIE.NS", "CYIENTDLM.NS", "UNIMECH.NS",

    # Power, renewables & green infrastructure
    "SUZLON.NS", "INOXWIND.NS", "IREDA.NS", "NHPC.NS", "SJVN.NS",
    "TORNTPOWER.NS", "CESC.NS", "RPOWER.NS", "JPPOWER.NS",
    "GREENPOWER.NS", "ADANIGREEN.NS", "ADANIENSOL.NS", "JSWENERGY.NS",
    "TATAPOWER.NS", "KEC.NS", "KPITTECH.NS", "SOLARINDS.NS",

    # Railways & infrastructure
    "IRFC.NS", "RVNL.NS", "RAILTEL.NS", "IRCON.NS", "TITAGARH.NS",
    "TEXRAIL.NS", "NBCC.NS", "HUDCO.NS", "NCC.NS", "PNCINFRA.NS",
    "KNRCON.NS", "HGINFRA.NS", "GPPL.NS", "CONCOR.NS",

    # Specialty chemicals & materials
    "CLEAN.NS", "FINEORG.NS", "NAVINFLUOR.NS", "FLUOROCHEM.NS",
    "NOCIL.NS", "DEEPAKNTR.NS", "AAVAS.NS", "TATACHEM.NS",
    "ATUL.NS", "SUDARSCHEM.NS", "VINATIORGA.NS", "ROSSARI.NS",
    "HIMADRI.NS", "NSLNISP.NS",

    # Pharma & healthcare beyond Nifty 50
    "AUROPHARMA.NS", "GLENMARK.NS", "IPCALAB.NS", "NATCOPHAR.NS",
    "JBCHEPHARM.NS", "PFIZER.NS", "SANOFI.NS", "ABBOTINDIA.NS",
    "THYROCARE.NS", "METROPOLIS.NS", "LALPATHLAB.NS", "RAINBOW.NS",
    "KIMS.NS", "YATHARTH.NS",

    # IT midcap & emerging tech
    "MPHASIS.NS", "BIRLASOFT.NS", "RATEGAIN.NS", "INTELLECT.NS",
    "TANLA.NS", "LATENTVIEW.NS", "MASTEK.NS", "HAPPSTMNDS.NS",
    "NEWGEN.NS", "TATAELXSI.NS", "CYIENT.NS", "ZENSAR.NS",
    "COFORGE.NS",

    # Banking, fintech & NBFC
    "CREDITACC.NS", "MUTHOOTFIN.NS", "MANAPPURAM.NS", "CHOLAFIN.NS",
    "LTFH.NS", "POONAWALLA.NS", "JIOFIN.NS", "ICICIGI.NS",
    "ICICIPRULI.NS", "HDFCLIFE.NS", "SBILIFE.NS", "ANGELONE.NS",
    "BSE.NS", "CDSL.NS",

    # Auto & EV ecosystem
    "TVSMOTOR.NS", "BAJAJ-AUTO.NS", "MOTHERSON.NS", "BOSCHLTD.NS",
    "MINDAIND.NS", "ENDURANCE.NS", "AMARAJABAT.NS", "EXIDEIND.NS",
    "OLECTRA.NS", "GREENPANEL.NS", "PRICOL.NS",

    # Real estate & housing
    "DLF.NS", "GODREJPROP.NS", "PHOENIXLTD.NS", "OBEROIRLTY.NS",
    "PRESTIGE.NS", "SOBHA.NS", "HOMEFIRST.NS", "CANFINHOME.NS",
    "AAVAS.NS",
]

ETF_WATCHLIST = [
    "CPSEETF.NS", "MOM100.NS", "GOLDBEES.NS", "SILVERBEES.NS",
    "SETFNIF50.NS", "ICICIB22.NS", "MIDCAP150.NS", "NIFTYIETF.NS",
    "PHARMABEES.NS", "BANKBEES.NS", "PSUBNKBEES.NS", "CONSUMBEES.NS",
    "INFRABEES.NS", "NIFTYBEES.NS", "MAFANG.NS", "GROWWEV.NS",
    "INDIAGOLD.NS", "SILVERETF.NS", "MOM500.NS", "NEXT50.NS",
    "DEFENCEETF.NS", "RAILEIETF.NS",
]


def _unique_symbols(symbols):
    return list(dict.fromkeys(symbols))


# Stocks are used by the normal equity pipeline. ETFs stay separate so MTF scans
# can include them without confusing stock-only risk or sector logic.
NSE_WATCHLIST = _unique_symbols(NSE_WATCHLIST + THEMATIC_STOCK_WATCHLIST)
MTF_WATCHLIST = _unique_symbols(NSE_WATCHLIST + ETF_WATCHLIST)
ALL_SCAN_WATCHLIST = MTF_WATCHLIST

# Nifty 50 symbols (without .NS) for F&O analysis
NIFTY50_SYMBOLS = [s.replace('.NS', '') for s in NSE_WATCHLIST[:50]]

# --- KRONOS SETTINGS ---
KRONOS_MODEL_NAME = "NeoQuasar/Kronos-small"
KRONOS_TOKENIZER_NAME = "NeoQuasar/Kronos-Tokenizer-base"
KRONOS_FINETUNED_PATH = "./kronos/models/kronos_nse_finetuned/"
KRONOS_LOOKBACK = 400
KRONOS_PRED_LEN = 5
KRONOS_MAX_CONTEXT = 512

# --- SCORING WEIGHTS (must sum to 100) ---
SCORING_WEIGHTS = {
    "kronos_forecast": 40,      # Real Kronos AI neural network
    "xgboost_forecast": 15,     # XGBoost probability classifier
    "technical_indicators": 15,
    "news_sentiment": 15,       # Ollama AI or keyword fallback
    "fo_signals": 10,
    "kline_patterns": 5,
}

MIN_CONFIDENCE_SCORE = 60       # Standardized score threshold for qualified trade categories

# --- RISK MANAGEMENT ---
RISK_ACCOUNT_EQUITY = 100000.0      # Virtual trading equity in INR
RISK_PER_TRADE_PCT = 1.5           # Max risk budget percentage per trade (e.g. 1.5% of equity)
RISK_MAX_ALLOCATION_PCT = 20.0     # Max capital allocated to a single trade (prevents overallocating on tight stops)
RISK_MAX_SECTOR_EXPOSURE = 2       # Max stocks from the same sector in daily picks

# --- SCHEDULE ---
RUN_TIME_IST = "08:45"

# --- WHATSAPP ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_FROM = os.getenv("WHATSAPP_FROM", "whatsapp:+14155238886")
WHATSAPP_TO = os.getenv("WHATSAPP_TO")

# --- DATA CACHE ---
CACHE_DIR = "./data/cache"
CACHE_EXPIRY_MINUTES = 30

# --- TIMEZONE ---
IST_TIMEZONE = "Asia/Kolkata"

# --- AWS BEDROCK SETTINGS ---
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_BEDROCK_MODEL = os.getenv("AWS_BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")
AWS_BEDROCK_API_KEY = os.getenv("AWS_BEDROCK_API_KEY")

# --- OLLAMA SETTINGS ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "meta/llama-4-maverick-17b-128e-instruct")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))  # seconds per request
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

# --- ADAPTIVE SCORING WEIGHTS (must sum to 100) ---
ADAPTIVE_SCORING_WEIGHTS = {
    "TRENDING": {
        "kronos_forecast": 45,
        "xgboost_forecast": 15,
        "technical_indicators": 20,
        "news_sentiment": 10,
        "fo_signals": 5,
        "kline_patterns": 5,
    },
    "SIDEWAYS": {
        "kronos_forecast": 30,
        "xgboost_forecast": 15,
        "technical_indicators": 15,
        "news_sentiment": 25,
        "fo_signals": 10,
        "kline_patterns": 5,
    },
    "VOLATILE": {
        "kronos_forecast": 25,
        "xgboost_forecast": 20,
        "technical_indicators": 10,
        "news_sentiment": 25,
        "fo_signals": 15,
        "kline_patterns": 5,
    }
}

# --- RISK ENGINE PARAMS ---
RISK_MAX_RSI = 80.0
RISK_MIN_VOLUME = 10000.0
RISK_MIN_VOLUME_20MA_RATIO = 0.1

# --- TIME DECAY MODEL PARAMS ---
NEWS_DECAY_HALFLIFE_HOURS = 6.0