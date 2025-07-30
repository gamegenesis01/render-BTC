import yfinance as yf
import pandas as pd
import numpy as np
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ========== BTC RSI EMAIL ALERT BOT ==========
# This bot runs via Render.com cron job every 15 minutes
# It analyzes BTC's RSI and sends an email if conditions match

# === Environment Variables ===
your_email = os.getenv("EMAIL_ADDRESS")
your_app_password = os.getenv("APP_PASSWORD")
recipient = os.getenv("RECIPIENT_EMAIL")

def send_rsi_alert(signal_type, price, rsi_value):
    subject = f"📈 BTC RSI Alert: {signal_type.upper()}"
    header = "📌 BTC ALERT SYSTEM – PATTERN DETECTED"
    body = f"""
{header}

🔔 RSI Signal: {signal_type}
💰 BTC Price: ${price:,.2f}
📊 RSI Value: {rsi_value:.2f}
🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

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
    print(f"🔄 Checking BTC at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    df = yf.download("BTC-USD", interval="15m", period="7d")
    df.dropna(inplace=True)

    # Calculate RSI manually
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Determine signal pattern
    df['Pattern'] = np.where(df['RSI'] < 30, 'Oversold',
                     np.where(df['RSI'] > 70, 'Overbought', None))

    # Extract latest row
    latest = df.iloc[-1]
    pattern = latest['Pattern']
    price = latest['Close'].item() if hasattr(latest['Close'], 'item') else float(latest['Close'])
    rsi_value = latest['RSI'].item() if hasattr(latest['RSI'], 'item') else float(latest['RSI'])

    # Send alert
    if pattern == 'Oversold':
        send_rsi_alert("BUY", price, rsi_value)
    elif pattern == 'Overbought':
        send_rsi_alert("SELL", price, rsi_value)
    else:
        send_rsi_alert("NO SIGNAL", price, rsi_value)


# === Run Bot ===
run_bot()
