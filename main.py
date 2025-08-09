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
SWING_LOOKBACK_5 = 48           # 4 hours of 5m bars
ATR_TP_MULT = 1.5               # target = 1.5x ATR
ATR_SL_MULT = 1.0               # stop   = 1.0x ATR
VWAP_TOL = 0.2                  # allow entries +/- 0.2*ATR around VWAP

# 1h context params
RSI_LEN_1H = 14
EMA_FAST_1H = 20
EMA_SLOW_1H = 50

# ===================== UTIL =====================
def utc_now():
    return datetime.now(timezone.utc)

def fmt_ts(ts: datetime):
    return ts.strftime("%Y-%m-%d %H:%M:%S %Z")

def send_email(subject, body):
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

def fetch(interval: str, period: str):
    df = yf.download(SYMBOL, interval=interval, period=period)
    df.dropna(inplace=True)
    return df

def compute_rsi(series: pd.Series, length: int):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_atr(df: pd.DataFrame, length: int):
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1
    ).max(axis=1)
    return tr.ewm(span=length, adjust=False).mean()

def add_vwap(df: pd.DataFrame):
    # Intraday VWAP resets daily (UTC)
    idx = df.index
    if getattr(idx, "tz", None) is None:
        utc_dates = pd.to_datetime(idx).tz_localize("UTC").date
    else:
        utc_dates = idx.tz_convert("UTC").date
    utc_dates = pd.Series(utc_dates, index=df.index)

    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_pv = (tp * df["Volume"]).groupby(utc_dates).cumsum()
    cum_v  = df["Volume"].groupby(utc_dates).cumsum().replace(0, np.nan)
    df["VWAP"] = cum_pv / cum_v
    return df

def compute_indicators_5m(df5: pd.DataFrame) -> pd.DataFrame:
    df5["RSI"] = compute_rsi(df5["Close"], RSI_LEN_5)
    df5["EMA9"]  = df5["Close"].ewm(span=EMA_FAST_5, adjust=False).mean()
    df5["EMA21"] = df5["Close"].ewm(span=EMA_SLOW_5, adjust=False).mean()
    df5["ATR"]   = compute_atr(df5, ATR_LEN_5)
    df5 = add_vwap(df5)
    df5["SwingHigh"] = df5["High"].rolling(SWING_LOOKBACK_5).max()
    df5["SwingLow"]  = df5["Low"].rolling(SWING_LOOKBACK_5).min()
    return df5

def compute_indicators_1h(df1h: pd.DataFrame) -> pd.DataFrame:
    df1h["RSI"] = compute_rsi(df1h["Close"], RSI_LEN_1H)
    df1h["EMA_FAST"] = df1h["Close"].ewm(span=EMA_FAST_1H, adjust=False).mean()
    df1h["EMA_SLOW"] = df1h["Close"].ewm(span=EMA_SLOW_1H, adjust=False).mean()
    return df1h

# ===================== SIGNALS =====================
def signal_from_5m(df5: pd.DataFrame, df1h: pd.DataFrame):
    # Latest bars
    r5  = df5.iloc[-1]
    r5p = df5.iloc[-2] if len(df5) > 1 else r5
    r1h = df1h.iloc[-1]

    price = float(r5["Close"])
    rsi5  = float(r5["RSI"])
    ema9  = float(r5["EMA9"])
    ema21 = float(r5["EMA21"])
    vwap  = float(r5["VWAP"])
    atr   = float(r5["ATR"])
    swing_high = float(r5["SwingHigh"])
    swing_low  = float(r5["SwingLow"])

    # 1h context
    ema_fast_1h = float(r1h["EMA_FAST"])
    ema_slow_1h = float(r1h["EMA_SLOW"])
    rsi1h = float(r1h["RSI"])
    hourly_bull = ema_fast_1h > ema_slow_1h
    hourly_bear = ema_fast_1h < ema_slow_1h

    # 5m momentum & confirmation
    bullish_5 = ema9 > ema21
    bearish_5 = ema9 < ema21
    tick_up   = price > float(r5p["Close"])
    tick_down = price < float(r5p["Close"])

    # VWAP proximity
    vwap_ok_buy  = (price >= vwap - VWAP_TOL * atr)
    vwap_ok_sell = (price <= vwap + VWAP_TOL * atr)

    # BUY: Align with 1h bullish, 5m confluence, RSI<30, confirmation tick-up
    if (rsi5 < 30) and (hourly_bull or (rsi1h > 50)) and (bullish_5 or ema9 >= ema21) and vwap_ok_buy and tick_up:
        target = max(swing_high, price + ATR_TP_MULT * atr)
        stop   = price - ATR_SL_MULT * atr
        reason = "RSI5<30 + 1h uptrend + tick-up + near VWAP"
        return "BUY", reason, price, target, stop, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h

    # SELL: Align with 1h bearish, 5m confluence, RSI>70, confirmation tick-down
    if (rsi5 > 70) and (hourly_bear or (rsi1h < 50)) and (bearish_5 or ema9 <= ema21) and vwap_ok_sell and tick_down:
        target = min(swing_low, price - ATR_TP_MULT * atr)
        stop   = price + ATR_SL_MULT * atr
        reason = "RSI5>70 + 1h downtrend + tick-down + near VWAP"
        return "SELL", reason, price, target, stop, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h

    # No trade
    reason = f"No confluence. 1h trend={'Bull' if hourly_bull else 'Bear' if hourly_bear else 'Flat'}, RSI5={rsi5:.2f}"
    return "NO SIGNAL", reason, price, None, None, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h

# ===================== LOGGING & DIGEST =====================
def append_signal_log(ts_utc: datetime, signal, price, target, stop, rsi5, ema9, ema21, vwap, atr, hourly_bull, hourly_bear, rsi1h, reason):
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
        "atr5": atr,
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

def send_hourly_digest(now_utc: datetime):
    # Only send at top of hour
    if now_utc.minute != 0:
        return
    if not LOG_PATH.exists():
        return

    df = pd.read_csv(LOG_PATH)
    if df.empty:
        return
    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True)
    one_hour_ago = now_utc - timedelta(hours=1)
    recent = df[df["time_utc"] >= one_hour_ago]

    trades = recent[recent["signal"].isin(["BUY", "SELL"])]
    if trades.empty:
        # Still send a heartbeat/update if you want; otherwise skip
        body = f"""📣 BTC Hourly Update

No BUY/SELL alerts in the last hour.

🕒 Window: {fmt_ts(one_hour_ago)} → {fmt_ts(now_utc)}
"""
        send_email("BTC Hourly Update: No trades", body)
        return

    # Build summary
    lines = []
    for _, r in trades.iterrows():
        t = r["time_utc"]
        lines.append(
            f"- {pd.to_datetime(t).strftime('%H:%M:%S')} UTC | {r['signal']} @ ${float(r['price']):,.2f} → "
            f"Target ${float(r['target']):,.2f} | Stop ${float(r['stop']):,.2f} | 1h {r['hourly_trend']} | RSI5 {float(r['rsi5']):.1f}"
        )
    body = f"""📣 BTC Hourly Update

Total signals: {len(trades)}

""" + "\n".join(lines) + f"""

🕒 Window: {fmt_ts(one_hour_ago)} → {fmt_ts(now_utc)}
"""
    send_email("BTC Hourly Update: Summary of last hour", body)

# ===================== MAIN =====================
def run():
    now = utc_now()
    print(f"🔄 Scan @ {fmt_ts(now)}")

    # Fetch data
    df5  = fetch("5m",  "60d")   # yfinance supports up to 60d for 5m bars
    df1h = fetch("60m", "730d")  # long history for smoother context

    # Indicators
    df5  = compute_indicators_5m(df5)
    df1h = compute_indicators_1h(df1h)

    # Signal
    (signal, reason, price, target, stop,
     rsi5, ema9, ema21, vwap, atr5, hourly_bull, hourly_bear, rsi1h) = signal_from_5m(df5, df1h)

    trend = "📈 Bullish" if hourly_bull else "📉 Bearish" if hourly_bear else "➖ Flat"

    # Immediate alert on BUY/SELL
    if signal in ["BUY", "SELL"]:
        subject = f"BTC 5m Alert: {signal}"
        body = f"""
📈 BTC Day-Trade Alert: {signal}

===============================
📌 Signal time: {fmt_ts(now)}
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
        # Optional: still log “no signal” lines if you want full trace
        pass

    # Hourly digest at :00
    send_hourly_digest(now)

if __name__ == "__main__":
    run()
