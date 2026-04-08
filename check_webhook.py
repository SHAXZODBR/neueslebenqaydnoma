import requests
import os
from dotenv import load_dotenv

load_dotenv()

def check_webhook():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ Error: BOT_TOKEN not found in .env")
        return

    api_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    res = requests.get(api_url)
    
    if res.status_code == 200:
        data = res.json()
        if data.get("ok"):
            info = data.get("result", {})
            url = info.get("url")
            if url:
                print(f"✅ Webhook is ACTIVE")
                print(f"🔗 URL: {url}")
                print(f"📈 Pending updates: {info.get('pending_update_count', 0)}")
                if info.get("last_error_message"):
                    print(f"⚠️ Last Error: {info.get('last_error_message')}")
            else:
                print("⚠️ Webhook is NOT SET (The bot is currently in polling mode or disconnected)")
        else:
            print(f"❌ API Error: {data.get('description')}")
    else:
        print(f"❌ Failed to connect to Telegram API. Status: {res.status_code}")

if __name__ == "__main__":
    check_webhook()
