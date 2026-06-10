"""
Configure the Evolution API webhook to point at your FastAPI server.

Usage:
    python setup_webhook.py https://your-public-url.com

Examples:
    python setup_webhook.py https://abc123.ngrok-free.app
    python setup_webhook.py https://yourserver.com:8000
    python setup_webhook.py http://1.2.3.4:8000
"""
import sys
import httpx

from config import EVOLUTION_API_URL, EVOLUTION_INSTANCE, EVOLUTION_API_KEY

HEADERS = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}


def set_webhook(public_url: str):
    url = public_url.rstrip("/") + "/webhook"
    payload = {
        "webhook": {
            "enabled": True,
            "url": url,
            "webhookByEvents": False,
            "webhookBase64": False,
            "events": ["MESSAGES_UPSERT"],
        }
    }
    endpoint = f"{EVOLUTION_API_URL.rstrip('/')}/webhook/set/{EVOLUTION_INSTANCE}"
    resp = httpx.post(endpoint, json=payload, headers=HEADERS)
    resp.raise_for_status()
    print(f"Webhook configured: {url}")
    print("Response:", resp.json())


def get_webhook():
    endpoint = f"{EVOLUTION_API_URL.rstrip('/')}/webhook/find/{EVOLUTION_INSTANCE}"
    resp = httpx.get(endpoint, headers=HEADERS)
    resp.raise_for_status()
    print("Current webhook:", resp.json())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Current webhook config:")
        get_webhook()
        print()
        print("To set webhook:  python setup_webhook.py https://your-url.com")
    else:
        set_webhook(sys.argv[1])
