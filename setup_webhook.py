import requests
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def set_webhook():
    token = os.getenv("BOT_TOKEN")
    vercel_url = os.getenv("VERCEL_URL")
    
    if not token or not vercel_url:
        print("❌ Error: BOT_TOKEN and VERCEL_URL must be set in .env")
        return

    # Clean URL
    vercel_url = vercel_url.strip("/")
    webhook_url = f"{vercel_url}/api/webhook"
    
    print(f"🔗 Setting webhook to: {webhook_url}")
    
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    params = {"url": webhook_url, "drop_pending_updates": True}
    
    res = requests.post(api_url, params=params)
    if res.status_code == 200:
        print("✅ Webhook set successfully!")
        print(res.json())
    else:
        print("❌ Failed to set webhook.")
        print(res.text)

if __name__ == "__main__":
    set_webhook()
