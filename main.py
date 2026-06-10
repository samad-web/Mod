"""
FastAPI server.

Endpoints:
  POST /webhook          — Evolution API webhook (text message → update PDF → send back)
  POST /update-pdf       — Manual trigger: { "client_name": "Apollo Hospitals", "price": "2400" }
  GET  /health           — Liveness check
  GET  /download/{name}  — Download a generated PDF
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import BOT_JID, OUTPUT_DIR, SEND_PDF_BACK
from name_extractor import extract_proposal
from pdf_editor import update_proposal
from evolution_client import send_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    yield


app = FastAPI(title="Proposal PDF Updater", lifespan=lifespan)


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_text(data: dict) -> str | None:
    """Pull plain text out of an Evolution API message payload."""
    msg = data.get("message", {})
    msg_type = data.get("messageType", "")

    if msg_type == "conversation":
        return msg.get("conversation", "").strip() or None

    if msg_type == "extendedTextMessage":
        return msg.get("extendedTextMessage", {}).get("text", "").strip() or None

    return None


async def _process(client_name: str, price: str | None, sender_jid: str):
    """Generate the updated PDF and optionally send it back."""
    try:
        log.info("Generating proposal for: %s  price: %s", client_name, price or "unchanged")
        pdf_path = update_proposal(client_name, price=price)
        log.info("PDF saved: %s", pdf_path)

        if SEND_PDF_BACK and sender_jid:
            caption = f"Updated proposal for M/S {client_name.title()}"
            log.info("Sending PDF to %s ...", sender_jid)
            result = await send_document(sender_jid, pdf_path, caption)
            log.info("Send result: %s", result)
        else:
            log.warning("PDF not sent — SEND_PDF_BACK=%s sender_jid=%r", SEND_PDF_BACK, sender_jid)
    except Exception as e:
        log.exception("ERROR in _process: %s", e)


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Evolution API webhook and trigger PDF update."""
    payload = await request.json()

    event = payload.get("event", "")
    if event != "messages.upsert":
        return JSONResponse({"ignored": "not a message event"})

    data = payload.get("data", {})
    key = data.get("key", {})

    from_me = key.get("fromMe", False)
    remote_jid = key.get("remoteJid", "")

    # Only accept inbound messages FROM BOT_JID — ignore everything else
    if from_me:
        return JSONResponse({"ignored": "outgoing message"})
    if BOT_JID and remote_jid != BOT_JID:
        return JSONResponse({"ignored": "sender not BOT_JID"})

    sender_jid = BOT_JID  # always send PDF back to BOT_JID

    text = _extract_text(data)
    if not text:
        return JSONResponse({"ignored": "no text content"})

    proposal = extract_proposal(text)
    if not proposal:
        return JSONResponse({"ignored": "could not extract client name"})

    client_name = proposal["name"]
    price = proposal["price"]

    log.info("Webhook: client=%s  price=%s", client_name, price or "unchanged")
    background_tasks.add_task(_process, client_name, price, sender_jid)

    return JSONResponse({"status": "processing", "client_name": client_name, "price": price})


class UpdateRequest(BaseModel):
    client_name: str
    price: Optional[str] = None


@app.post("/update-pdf")
async def update_pdf(body: UpdateRequest):
    """Manual endpoint for testing without WhatsApp."""
    proposal = extract_proposal(f"proposal for {body.client_name}")
    client_name = proposal["name"] if proposal else body.client_name.upper()
    pdf_path = update_proposal(client_name, price=body.price)
    filename = os.path.basename(pdf_path)
    return {"status": "ok", "client_name": client_name, "price": body.price, "file": filename, "download": f"/download/{filename}"}


@app.get("/download/{filename}")
def download(filename: str):
    """Serve a generated PDF."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="application/pdf", filename=filename)
