"""
FastAPI server.

Endpoints:
  POST /webhook          — Evolution API webhook (text message → update PDF → send back)
  POST /update-pdf       — Manual trigger: { "client_name": "Apollo Hospitals" }
  GET  /health           — Liveness check
  GET  /download/{name}  — Download a generated PDF
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import ALLOWED_JIDS, OUTPUT_DIR, SEND_PDF_BACK
from name_extractor import extract_client_name
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


async def _process(client_name: str, sender_jid: str):
    """Generate the updated PDF and optionally send it back."""
    log.info("Generating proposal for: %s", client_name)
    pdf_path = update_proposal(client_name)
    log.info("PDF saved: %s", pdf_path)

    if SEND_PDF_BACK and sender_jid:
        caption = f"Updated proposal for M/S {client_name.title()}"
        await send_document(sender_jid, pdf_path, caption)
        log.info("PDF sent back to %s", sender_jid)


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Evolution API webhook and trigger PDF update for self-sent text messages."""
    payload = await request.json()

    event = payload.get("event", "")
    if event != "messages.upsert":
        return JSONResponse({"ignored": "not a message event"})

    data = payload.get("data", {})
    key = data.get("key", {})

    from_me = key.get("fromMe", False)
    remote_jid = key.get("remoteJid", "")

    # Accept messages from any configured trigger JID (from or to)
    if ALLOWED_JIDS:
        if remote_jid not in ALLOWED_JIDS:
            return JSONResponse({"ignored": "not trigger JID"})
    else:
        # No JID configured — only accept self-messages
        if not from_me:
            return JSONResponse({"ignored": "not fromMe"})

    sender_jid = remote_jid

    text = _extract_text(data)
    if not text:
        return JSONResponse({"ignored": "no text content"})

    client_name = extract_client_name(text)
    if not client_name:
        return JSONResponse({"ignored": "could not extract client name"})

    log.info("Webhook: client name extracted → %s", client_name)
    background_tasks.add_task(_process, client_name, sender_jid)

    return JSONResponse({"status": "processing", "client_name": client_name})


class UpdateRequest(BaseModel):
    client_name: str


@app.post("/update-pdf")
async def update_pdf(body: UpdateRequest):
    """Manual endpoint for testing without WhatsApp."""
    client_name = extract_client_name(body.client_name) or body.client_name.upper()
    pdf_path = update_proposal(client_name)
    filename = os.path.basename(pdf_path)
    return {"status": "ok", "client_name": client_name, "file": filename, "download": f"/download/{filename}"}


@app.get("/download/{filename}")
def download(filename: str):
    """Serve a generated PDF."""
    # Sanitise — no path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="application/pdf", filename=filename)
