"""
Extract client name and optional price from a plain WhatsApp text message.
No AI — pure string parsing.

Accepted formats (case-insensitive):
  "Proposal for Apollo Hospitals"
  "The proposal for Apollo Hospitals"
  "Proposal for Apollo Hospitals price 2400 AED"
  "proposal for City Care Clinic price 3,600 AED"
"""
import re

_PROPOSAL_FOR = re.compile(
    r"^(?:the\s+)?proposal\s+for\s+(.+?)(?:\s+price\s+([\d,]+)\s*(?:aed)?)?$",
    re.IGNORECASE,
)


def extract_proposal(message_text: str) -> dict | None:
    """
    Returns {"name": str, "price": str | None} or None if no match.
    price is the raw digits string, e.g. "2400" or "3,600".
    """
    text = message_text.strip()
    if not text:
        return None

    m = _PROPOSAL_FOR.match(text)
    if not m:
        return None

    name = m.group(1).strip()
    price = m.group(2).strip() if m.group(2) else None

    if len(name) < 2 or len(name) > 120:
        return None

    return {"name": name.upper(), "price": price}


def extract_client_name(message_text: str) -> str | None:
    """Legacy single-value wrapper."""
    result = extract_proposal(message_text)
    return result["name"] if result else None
