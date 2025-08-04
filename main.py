import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

# ========== BTC RSI EMAIL ALERT BOT ========== #
# Enhanced with:
# - EMA trend filters
# - Dynamic swing target logic
# - Estimated time-to-target calculation

# === Environment Variables ===
your_email = os.getenv("EMAIL_ADDRESS")
your_app_password = os.getenv("APP_PASSWORD")
recipient = os.getenv("RECIPIENT_EMAIL")

def send_rsi_alert(signal_type, price, rsi_value, ema9, ema21, target_price=None, estimated_time=None):
    subject = f"📈 BTC RSI Alert: {signal_type.upper()}"
    header = "📌 BTC ALERT SYSTEM – SIGNAL GENERATED"
    body = f"""
{header}

🔔 RSI Signal: {signal_type}
💰 BTC Price: ${price:,.2f}
📊 RSI Value: {rsi_value:.2f}
📉 EMA (9): ${ema9:,.2f}
📈 EMA (21): ${ema21:,.2f}
🕒 Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}
"""

    if signal_type.upper() == "BUY" and target_price:
        body += f"🎯 Target Sell Price: ${target_price:,.2f} (Recent High)\n"
    elif signal_type.upper() == "SELL" and target_price:
        body += f"🎯 Target Buy Price: ${target_price:,.2f} (Recent Low)\n"

    if estimated_time:
        body += f"⏱️ Est. Time to Target: {estimated_time:.1f} intervals (15m each)\n"

    msg = MIMEMultipart()
    msg['From'] = your_email
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(your_email, your_app_password)
        server.sendmail(your_email, recipient, msg.as_string())
        server.quit()
        print(f"✅ Email alert sent: {signal_type.upper()} at ${price:.2f}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def estimate_time_to_target(df, price, target_price):
    if price == 0 or target_price == 0:
        return None
    price_diff = abs(target_price - price)
    recent_volatility = df['Close'].diff().abs().rolling(window=12).mean().iloc[-1]  # 3hr volatility
    if recent_volatility == 0 or pd.isna(recent_volatility):
        return None
    intervals_needed = price_diff / recent_volatility
    return intervals_needed

def run_bot():
    print(f"🔄 Checking BTC at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    df = yf.download("BTC-USD", interval="15m", period="7d")
    df.dropna(inplace=True)

    # RSI Calculation
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # EMA Calculation
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()

    # Pattern
    df['Pattern'] = np.where(df['RSI'] < 30, 'Oversold',
                     np.where(df['RSI'] > 70, 'Overbought', None))

    latest = df.iloc[-1]
    price = float(latest['Close'])
    rsi_value = float(latest['RSI'])
    ema_short = float(latest['EMA9'])
    ema_long = float(latest['EMA21'])
    pattern = str(latest['Pattern'])

    recent_high = df['High'].rolling(window=24).max().iloc[-1]
    recent_low = df['Low'].rolling(window=24).min().iloc[-1]

    # Estimate how long to hit target
    target = None
    eta = None

    if pattern == 'Oversold':
        target = recent_high
        eta = estimate_time_to_target(df, price, target)
        send_rsi_alert("BUY", price, rsi_value, ema_short, ema_long, target_price=target, estimated_time=eta)

    elif pattern == 'Overbought':
        target = recent_low
        eta = estimate_time_to_target(df, price, target)
        send_rsi_alert("SELL", price, rsi_value, ema_short, ema_long, target_price=target, estimated_time=eta)

    else:
        send_rsi_alert("NO SIGNAL", price, rsi_value, ema_short, ema_long)

# Run the bot
run_bot()
