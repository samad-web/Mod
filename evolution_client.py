"""
Evolution API client:
  - send_document()  → send a PDF back to a WhatsApp number
"""
import base64
import os
import httpx
from config import EVOLUTION_API_URL, EVOLUTION_INSTANCE, EVOLUTION_API_KEY


def _headers() -> dict:
    return {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}


def _base_url() -> str:
    return EVOLUTION_API_URL.rstrip("/")


async def send_document(to_jid: str, pdf_path: str, caption: str = "") -> dict:
    """
    Send a PDF file to a WhatsApp number via Evolution API.

    Evolution API endpoint:
        POST /message/sendMedia/{instance}
    """
    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    # to_jid can be "919876543210@s.whatsapp.net" or just the number
    number = to_jid.split("@")[0]
    filename = os.path.basename(pdf_path)

    url = f"{_base_url()}/message/sendMedia/{EVOLUTION_INSTANCE}"
    payload = {
        "number": number,
        "mediatype": "document",
        "mimetype": "application/pdf",
        "caption": caption,
        "media": b64,
        "fileName": filename,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
        return resp.json()
