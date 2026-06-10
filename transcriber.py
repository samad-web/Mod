"""
Audio transcription using OpenAI Whisper API.
Accepts raw audio bytes + MIME type, returns transcript string.
"""
import io
import tempfile
import os
from openai import OpenAI
from config import OPENAI_API_KEY

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# WhatsApp voice notes arrive as audio/ogg (opus codec) — map to a file extension
_MIME_TO_EXT = {
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/aac": ".aac",
}


def transcribe_audio(audio_bytes: bytes, mimetype: str = "audio/ogg") -> str:
    """Transcribe audio bytes to text using OpenAI Whisper."""
    ext = _MIME_TO_EXT.get(mimetype.lower().strip(), ".ogg")

    # Write to a temp file because the Whisper API needs a file-like object with a name
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        client = _get_client()
        with open(tmp_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en",
            )
        return response.text.strip()
    finally:
        os.unlink(tmp_path)
