# 🚀 Render-BTC – RSI-Based Bitcoin Email Alert Bot

This bot analyzes Bitcoin (BTC-USD) price data using the Relative Strength Index (RSI) to detect trading signals (BUY, SELL, or NO SIGNAL). It runs hourly and sends email alerts based on RSI patterns using Gmail SMTP.

---

## 📈 How It Works

- 📊 Fetches real-time BTC-USD data (15-minute intervals)
- 🧠 Calculates RSI manually (14-period)
- 📌 Classifies the latest RSI value as:
  - **BUY** → RSI < 30
  - **SELL** → RSI > 70
  - **NO SIGNAL** → RSI between 30 and 70
- 📧 Sends an email alert with the result

---

## 🔁 Deployment via Render.com (Cron Job)

This project uses [Render Cron Jobs](https://render.com/docs/cron-jobs) to run `main.py` once every hour.

### ✅ Files Required

- `main.py` – Core bot logic
- `requirements.txt` – Python dependencies
- `render.yaml` – Render deployment config (cron setup)

---

## ⚙️ Environment Variables (set on Render)

| Key              | Description                            |
|------------------|----------------------------------------|
| `EMAIL_ADDRESS`  | Gmail address used to send emails      |
| `APP_PASSWORD`   | Gmail **App Password** (not regular PW)|
| `RECIPIENT_EMAIL`| Email address to receive alerts        |

> ⚠️ You must enable 2FA and create an App Password at: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

---

## ⏱ Cron Schedule

Configured in `render.yaml`:
```yaml
schedule: "0 * * * *"  # Runs every hour
