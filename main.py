import os
import smtplib
import numpy as np
import pandas as pd
import yfinance as yf
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===================== CONFIG =====================
EMAIL = os.getenv("EMAIL_ADDRESS")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECIPIENT = os.getenv("RECIPIENT_EMAIL")

SYMBOL = "BTC-USD"
LOG_PATH = Path(os.getenv("SIGNAL_LOG", "signals_log.csv"))

# 5m signal params
RSI_LEN_5 = 14
EMA_FAST_5 = 9
EMA_SLOW_5 = 21
ATR_LEN_5 = 14
SWING_LOOKBACK_5 = 48           # ~4 hours of 5m bars
ATR_TP_MULT = 1.5               # target = 1.5x ATR
ATR_SL_MULT = 1.0               # stop   = 1.0x ATR
VWAP_TOL = 0.2                  # allow entries +/- 0.2*ATR around VWAP

# 1h context params
RSI_LEN_1H = 14
EMA_FAST_1H = 20
EMA_SLOW_1H = 50

# ===================== UTIL =====================
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def ts_str(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S %Z")

def send_email(subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.sendmail(EMAIL, RECIPIENT, msg.as_string())
        server.quit()
        print(f"✅ Email sent: {subject}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def fetch(interval: str, period: str) -> pd.DataFrame:
    # Quiet the auto_adjust warning explicitly
    df = yf.download(SYMBOL, interval=interval, period=period, auto_adjust=False)
    df.dropna(inplace=True)
    return df

def compute_rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_atr(df: pd.DataFrame, length: int) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1
    ).max(axis=1)
    return tr.ewm(span=length, adjust=False).mean()

def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    # Intraday VWAP resets daily (UTC)
    idx = df.index
    utc_dates = (pd.to_datetime(idx, utc=True).date
                 if getattr(idx, "tz", None) is None else idx.tz_convert("UTC").date)
    utc_dates = pd.Series(utc_dates, index=df.index)

    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_pv = (tp * df["Volume"]).groupby(utc_dates).cumsum()
    cum_v  = df["Volume"].groupby(utc_dates).cumsum().replace(0, np.nan)
    df["VWAP"] = cum_pv / cum_v
    return df

def indicators_5m(df5: pd.DataFrame) -> pd.DataFrame:
    df5["RSI"] = compute_rsi(df5["Close"], RSI_LEN_5)
    df5["EMA9"]  = df5["Close"].ewm(span=EMA_FAST_5, adjust=False).mean()
    df5["EMA21"] = df5["Close"].ewm(span=EMA_SLOW_5, adjust=False).mean()
    df5["ATR"]   = compute_atr(df5, ATR_LEN_5)
    df5 = add_vwap(df5)
    df5["SwingHigh"] = df5["High"].rolling(SWING_LOOKBACK_5).max()
    df5["SwingLow"]  = df5["Low"].rolling(SWING_LOOKBACK_5).min()
    return df5

def indicators_1h(df1h: pd.DataFrame) -> pd.DataFrame:
    df1h["RSI"] = compute_rsi(df1h["Close"], RSI_LEN_1H)
    df1h["EMA_FAST"] = df1h["Close"].ewm(span=EMA_FAST_1H, adjust=False).mean()
    df1h["EMA_SLOW"] = df1h["Close"].ewm(span=EMA_SLOW_1H, adjust=False).mean()
    return df1h

# ===================== SIGNALS =====================
def make_signal(df5: pd.DataFrame, df1h: pd.DataFrame):
    """
    Return:
      (signal, reason, price, target, stop,
       rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h)
    """
    # indices for latest/previous 5m bars
    i  = -1
    ip = -2 if len(df5) > 1 else -1

    # === Scalars from columns (no 1-element Series) ===
    price      = float(df5['Close'].iloc[i])
    rsi5       = float(df5['RSI'].iloc[i])
    ema9       = float(df5['EMA9'].iloc[i])
    ema21      = float(df5['EMA21'].iloc[i])
    vwap       = float(df5['VWAP'].iloc[i])
    atr        = float(df5['ATR'].iloc[i])
    swing_high = float(df5['SwingHigh'].iloc[i])
    swing_low  = float(df5['SwingLow'].iloc[i])

    ema_fast_1h = float(df1h['EMA_FAST'].iloc[i])
    ema_slow_1h = float(df1h['EMA_SLOW'].iloc[i])
    rsi1h       = float(df1h['RSI'].iloc[i])

    # Context flags
    hourly_bull = ema_fast_1h > ema_slow_1h
    hourly_bear = ema_fast_1h < ema_slow_1h

    bullish_5 = ema9 > ema21
    bearish_5 = ema9 < ema21

    prev_close = float(df5['Close'].iloc[ip])
    tick_up    = price > prev_close
    tick_down  = price < prev_close

    # VWAP proximity
    vwap_ok_buy  = (price >= vwap - VWAP_TOL * atr)
    vwap_ok_sell = (price <= vwap + VWAP_TOL * atr)

    # BUY: RSI<30 + (1h uptrend or 1h RSI>50) + 5m momentum/tick-up + VWAP band
    if (rsi5 < 30) and (hourly_bull or rsi1h > 50) and (bullish_5 or ema9 >= ema21) and vwap_ok_buy and tick_up:
        target = max(swing_high, price + ATR_TP_MULT * atr)
        stop   = price - ATR_SL_MULT * atr
        reason = "RSI5<30 + 1h uptrend + tick-up + near VWAP"
        return ("BUY", reason, price, target, stop, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h)

    # SELL: RSI>70 + (1h downtrend or 1h RSI<50) + 5m momentum/tick-down + VWAP band
    if (rsi5 > 70) and (hourly_bear or rsi1h < 50) and (bearish_5 or ema9 <= ema21) and vwap_ok_sell and tick_down:
        target = min(swing_low, price - ATR_TP_MULT * atr)
        stop   = price + ATR_SL_MULT * atr
        reason = "RSI5>70 + 1h downtrend + tick-down + near VWAP"
        return ("SELL", reason, price, target, stop, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h)

    # No trade
    reason = f"No confluence. 1h trend={'Bull' if hourly_bull else 'Bear' if hourly_bear else 'Flat'}, RSI5={rsi5:.2f}"
    return ("NO SIGNAL", reason, price, None, None, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h)

# ===================== LOGGING & DIGEST =====================
def append_signal_log(ts_utc: datetime, signal: str, price: float, target, stop,
                      rsi5, ema9, ema21, vwap, atr5, hourly_bull, hourly_bear, rsi1h, reason: str):
    row = {
        "time_utc": ts_utc.isoformat(),
        "signal": signal,
        "price": price,
        "target": target,
        "stop": stop,
        "rsi5": rsi5,
        "ema9": ema9,
        "ema21": ema21,
        "vwap": vwap,
        "atr5": atr5,
        "hourly_trend": "bull" if hourly_bull else "bear" if hourly_bear else "flat",
        "rsi1h": rsi1h,
        "reason": reason
    }
    if LOG_PATH.exists():
        df = pd.read_csv(LOG_PATH)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(LOG_PATH, index=False)

def hourly_digest(now_utc: datetime) -> str | None:
    if not LOG_PATH.exists():
        return None
    df = pd.read_csv(LOG_PATH)
    if df.empty:
        return None
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    window_start = now_utc - timedelta(hours=1)
    recent = df[df["time_utc"] >= window_start]
    trades = recent[recent["signal"].isin(["BUY", "SELL"])]
    if trades.empty:
        return f"""📣 BTC Hourly Update

No BUY/SELL alerts in the last hour.

🕒 Window: {ts_str(window_start)} → {ts_str(now_utc)}
"""
    lines = []
    for _, r in trades.iterrows():
        t = pd.to_datetime(r["time_utc"]).strftime("%H:%M:%S")
        lines.append(
            f"- {t} UTC | {r['signal']} @ ${float(r['price']):,.2f} → "
            f"Target ${float(r['target']):,.2f} | Stop ${float(r['stop']):,.2f} | "
            f"1h {r['hourly_trend']} | RSI5 {float(r['rsi5']):.1f}"
        )
    return f"""📣 BTC Hourly Update

Total signals: {len(trades)}

""" + "\n".join(lines) + f"""

🕒 Window: {ts_str(window_start)} → {ts_str(now_utc)}
"""

# ===================== MAIN =====================
def run():
    now = utc_now()
    print(f"🔄 Scan @ {ts_str(now)}")

    # Fetch data
    df5  = fetch("5m",  "60d")   # up to 60d of 5m bars
    df1h = fetch("60m", "730d")  # long history for context

    # Indicators
    df5  = indicators_5m(df5)
    df1h = indicators_1h(df1h)

    # Signal
    (signal, reason, price, target, stop,
     rsi5, ema9, ema21, vwap, atr5, hourly_bull, hourly_bear, rsi1h) = make_signal(df5, df1h)

    trend = "📈 Bullish" if hourly_bull else "📉 Bearish" if hourly_bear else "➖ Flat"

    # Immediate alert on BUY/SELL
    if signal in ["BUY", "SELL"]:
        subject = f"BTC 5m Alert: {signal}"
        body = f"""
📈 BTC Day-Trade Alert: {signal}

===============================
📌 Signal time: {ts_str(now)}
📌 Timeframe: 5m (with 1h context)
===============================

💰 Price: ${price:,.2f}
📊 RSI(5m,14): {rsi5:.2f}
📉 EMA(5m,9):  ${ema9:,.2f}
📈 EMA(5m,21): ${ema21:,.2f}
📐 VWAP: ${vwap:,.2f}
🌊 ATR(5m,14): ${atr5:,.2f}

🧭 1h Trend: {trend}  |  RSI(1h): {rsi1h:.1f}
📝 Reason: {reason}

🎯 Target: ${target:,.2f}
🛑 Stop:   ${stop:,.2f}
"""
        send_email(subject, body)
        append_signal_log(now, signal, price, target, stop, rsi5, ema9, ema21, vwap, atr5, hourly_bull, hourly_bear, rsi1h, reason)
    else:
        print("No signal.")

    # Hourly digest at :00
    if now.minute == 0:
        body = hourly_digest(now)
        if body:
            send_email("BTC Hourly Update", body)

if __name__ == "__main__":
    run()
