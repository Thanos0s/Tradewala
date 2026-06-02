from __future__ import annotations

import numpy as np
import pandas as pd


def _as_series(values) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.copy()
    return pd.Series(values)


def ema(close, length: int = 9):
    close = _as_series(close)
    return close.ewm(span=length, adjust=False).mean()


def rsi(close, length: int = 14):
    close = _as_series(close)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50.0)


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    close = _as_series(close)
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {
            f"MACD_{fast}_{slow}_{signal}": macd_line,
            f"MACDs_{fast}_{slow}_{signal}": signal_line,
            f"MACDh_{fast}_{slow}_{signal}": hist,
        }
    )


def stochrsi(close, length: int = 14, rsi_length: int = 14, k: int = 3, d: int = 3):
    close = _as_series(close)
    rsi_series = rsi(close, length=rsi_length)
    min_rsi = rsi_series.rolling(length, min_periods=length).min()
    max_rsi = rsi_series.rolling(length, min_periods=length).max()
    denom = (max_rsi - min_rsi).replace(0, np.nan)
    stoch = (rsi_series - min_rsi) / denom * 100
    stoch_k = stoch.rolling(k, min_periods=1).mean()
    stoch_d = stoch_k.rolling(d, min_periods=1).mean()
    return pd.DataFrame({f"STOCHRSIk_{length}_{rsi_length}_{k}_{d}": stoch_k, f"STOCHRSId_{length}_{rsi_length}_{k}_{d}": stoch_d})


def _true_range(high, low, close):
    high = _as_series(high)
    low = _as_series(low)
    close = _as_series(close)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high, low, close, length: int = 14):
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def adx(high, low, close, length: int = 14):
    high = _as_series(high)
    low = _as_series(low)
    close = _as_series(close)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = _true_range(high, low, close)
    atr_val = tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_val.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_val.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    return pd.DataFrame(
        {
            f"ADX_{length}": adx_val.fillna(0.0),
            f"DMP_{length}": plus_di.fillna(0.0),
            f"DMN_{length}": minus_di.fillna(0.0),
        }
    )


def bbands(close, length: int = 20, std: float = 2.0):
    close = _as_series(close)
    mid = close.rolling(length, min_periods=length).mean()
    dev = close.rolling(length, min_periods=length).std(ddof=0)
    upper = mid + std * dev
    lower = mid - std * dev
    bandwidth = (upper - lower) / mid.replace(0, np.nan)
    percent_b = (close - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame(
        {
            f"BBL_{length}_{float(std)}": lower,
            f"BBM_{length}_{float(std)}": mid,
            f"BBU_{length}_{float(std)}": upper,
            f"BBB_{length}_{float(std)}": bandwidth,
            f"BBP_{length}_{float(std)}": percent_b,
        }
    )


def obv(close, volume):
    close = _as_series(close)
    volume = _as_series(volume).fillna(0.0)
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum().fillna(0.0)


def vwap(high, low, close, volume):
    high = _as_series(high)
    low = _as_series(low)
    close = _as_series(close)
    volume = _as_series(volume).fillna(0.0)
    typical_price = (high + low + close) / 3.0
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (typical_price * volume).cumsum() / cum_vol


def supertrend(high, low, close, length: int = 10, multiplier: float = 3.0):
    high = _as_series(high)
    low = _as_series(low)
    close = _as_series(close)
    atr_val = atr(high, low, close, length=length)
    hl2 = (high + low) / 2.0
    upperband = hl2 + multiplier * atr_val
    lowerband = hl2 - multiplier * atr_val

    final_upper = upperband.copy()
    final_lower = lowerband.copy()
    for i in range(1, len(close)):
        if close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = min(upperband.iloc[i], final_upper.iloc[i - 1])
        else:
            final_upper.iloc[i] = upperband.iloc[i]

        if close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = max(lowerband.iloc[i], final_lower.iloc[i - 1])
        else:
            final_lower.iloc[i] = lowerband.iloc[i]

    supertrend_line = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=float)
    for i in range(len(close)):
        if i == 0:
            supertrend_line.iloc[i] = final_lower.iloc[i]
            direction.iloc[i] = 1
            continue
        prev_line = supertrend_line.iloc[i - 1]
        if close.iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        supertrend_line.iloc[i] = final_lower.iloc[i] if direction.iloc[i] > 0 else final_upper.iloc[i]
        if pd.isna(prev_line):
            supertrend_line.iloc[i] = final_lower.iloc[i] if direction.iloc[i] > 0 else final_upper.iloc[i]

    return pd.DataFrame(
        {
            f"SUPERT_{length}_{float(multiplier)}": supertrend_line,
            f"SUPERTd_{length}_{float(multiplier)}": direction,
        }
    )


def mfi(high, low, close, volume, length: int = 14):
    high = _as_series(high)
    low = _as_series(low)
    close = _as_series(close)
    volume = _as_series(volume).fillna(0.0)
    tp = (high + low + close) / 3.0
    raw_mf = tp * volume
    delta_tp = tp.diff()
    positive_mf = raw_mf.where(delta_tp > 0, 0.0)
    negative_mf = raw_mf.where(delta_tp < 0, 0.0).abs()
    pos_sum = positive_mf.rolling(length, min_periods=length).sum()
    neg_sum = negative_mf.rolling(length, min_periods=length).sum()
    money_ratio = pos_sum / neg_sum.replace(0, np.nan)
    mfi_val = 100 - (100 / (1 + money_ratio))
    return mfi_val.fillna(50.0)


def roc(close, length: int = 12):
    close = _as_series(close)
    return close.pct_change(periods=length) * 100.0


def kc(high, low, close, length: int = 10, scalar: float = 2.0):
    high = _as_series(high)
    low = _as_series(low)
    close = _as_series(close)
    tp = (high + low + close) / 3.0
    middle = tp.ewm(span=length, adjust=False).mean()
    band_atr = atr(high, low, close, length=length)
    upper = middle + scalar * band_atr
    lower = middle - scalar * band_atr
    return pd.DataFrame(
        {
            f"KCU_{length}_{float(scalar)}": upper,
            f"KCM_{length}_{float(scalar)}": middle,
            f"KCL_{length}_{float(scalar)}": lower,
        }
    )
