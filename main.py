import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

# ========== BTC RSI EMAIL ALERT BOT ========== #
# Deployed via Render Cron Job
# Sends RSI-based trading alerts to your email every 15 minutes
# Now includes dynamic price targets, EMA trend detection, and improved formatting

# === Environment Variables ===
your_email = os.getenv("EMAIL_ADDRESS")
your_app_password = os.getenv("APP_PASSWORD")
recipient = os.getenv("RECIPIENT_EMAIL")

def send_rsi_alert(signal_type, price, rsi_value, ema_short, ema_long, trend_direction, target_price=None):
    subject = f"📈 BTC RSI Alert: {signal_type.upper()}"

    body = f"""
📈 BTC RSI Alert: {signal_type.upper()}

===============================
📌 BTC TECHNICAL ALERT – 15m
===============================

🔔 RSI Signal: {signal_type}  
💰 BTC Price: ${price:,.2f}  
📊 RSI Value: {rsi_value:.2f}  
📉 EMA (9): ${ema_short:,.2f}  
📈 EMA (21): ${ema_long:,.2f}  
📊 Trend: {trend_direction}  
🕒 Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
"""

    if signal_type.upper() == "BUY" and target_price:
        body += f"\n🎯 Target Sell Price: ${target_price:,.2f} (based on recent swing high)"
    elif signal_type.upper() == "SELL" and target_price:
        body += f"\n🎯 Target Buy Price: ${target_price:,.2f} (based on recent swing low)"

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

def run_bot():
    print(f"🔄 Checking BTC at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    df = yf.download("BTC-USD", interval="15m", period="7d")
    df.dropna(inplace=True)

    # Calculate RSI
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Calculate EMA
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()

    # Determine pattern
    df['Pattern'] = np.where(df['RSI'] < 30, 'Oversold',
                     np.where(df['RSI'] > 70, 'Overbought', None))

    # Get latest signal
    latest = df.iloc[[-1]]
    pattern = str(latest['Pattern'].values[0])
    price = float(latest['Close'].values[0])
    rsi_value = float(latest['RSI'].values[0])
    ema_short = float(latest['EMA9'].values[0])
    ema_long = float(latest['EMA21'].values[0])

    # Determine trend
    if ema_short > ema_long:
        trend_direction = "📈 Bullish (Short-term momentum up)"
    elif ema_short < ema_long:
        trend_direction = "📉 Bearish (Short-term momentum down)"
    else:
        trend_direction = "➖ Neutral"

    # Calculate recent swing targets
    recent_high = df['High'].rolling(window=24).max().iloc[-1]
    recent_low = df['Low'].rolling(window=24).min().iloc[-1]

    # Send alert
    if pattern == 'Oversold':
        send_rsi_alert("BUY", price, rsi_value, ema_short, ema_long, trend_direction, target_price=recent_high)
    elif pattern == 'Overbought':
        send_rsi_alert("SELL", price, rsi_value, ema_short, ema_long, trend_direction, target_price=recent_low)
    else:
        send_rsi_alert("NO SIGNAL", price, rsi_value, ema_short, ema_long, trend_direction)

# Run the bot
run_bot()
