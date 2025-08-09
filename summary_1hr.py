from utils import utc_now, ts_str, hourly_digest, send_email

def run():
    now = utc_now()
    print(f"🧾 Hourly summary @ {ts_str(now)}")
    body = hourly_digest(now)
    if body:
        subject = "BTC Hourly Update"
        send_email(subject, body)
    else:
        print("No log or nothing to summarize.")

if __name__ == "__main__":
    run()
