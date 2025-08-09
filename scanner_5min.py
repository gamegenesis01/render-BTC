from utils import (
    utc_now, ts_str, fetch, indicators_5m, indicators_1h,
    make_signal, send_email, append_signal_log
)

def run():
    now = utc_now()
    print(f"🔄 5m Scan @ {ts_str(now)}")

    # Fetch data (5m and 1h)
    df5  = fetch("5m",  "60d")
    df1h = fetch("60m", "730d")

    df5  = indicators_5m(df5)
    df1h = indicators_1h(df1h)

    (signal, reason, price, target, stop,
     rsi5, ema9, ema21, vwap, atr5, hourly_bull, hourly_bear, rsi1h) = make_signal(df5, df1h)

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

🧭 1h Trend: {"📈 Bullish" if hourly_bull else "📉 Bearish" if hourly_bear else "➖ Flat"}  |  RSI(1h): {rsi1h:.1f}
📝 Reason: {reason}

🎯 Target: ${target:,.2f}
🛑 Stop:   ${stop:,.2f}
"""
        send_email(subject, body)
        append_signal_log(now, signal, price, target, stop, rsi5, ema9, ema21, vwap, atr5, hourly_bull, hourly_bear, rsi1h, reason)
    else:
        print("No signal.")

if __name__ == "__main__":
    run()
