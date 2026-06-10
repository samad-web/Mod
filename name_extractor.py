"""
Extract a client/company name from a plain WhatsApp text message.
No AI — pure string parsing.

Accepted formats (case-insensitive):
  "Proposal for Apollo Hospitals"
  "The proposal for Apollo Hospitals"
  "the proposal for City Care Clinic"
"""
import re

_PROPOSAL_FOR = re.compile(r"^(?:the\s+)?proposal\s+for\s+(.+)$", re.IGNORECASE)


def extract_client_name(message_text: str) -> str | None:
    text = message_text.strip()
    if not text:
        return None

    m = _PROPOSAL_FOR.match(text)
    if not m:
        return None

    name = m.group(1).strip()
    if len(name) < 2 or len(name) > 120:
        return None

    return name.upper()
