import os
from dotenv import load_dotenv

load_dotenv()

# Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

# Comma-separated list of allowed trigger JIDs
# Format: "919876543210@s.whatsapp.net,971501234567@s.whatsapp.net"
_raw_jids = os.getenv("MY_WHATSAPP_JID", "")
ALLOWED_JIDS: set[str] = {j.strip() for j in _raw_jids.split(",") if j.strip()}
MY_WHATSAPP_JID = next(iter(ALLOWED_JIDS), "")  # kept for backwards compat

# PDF template settings
TEMPLATE_PDF = os.getenv("TEMPLATE_PDF", "Wecare-Clinic-Business-Proposal.pdf")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

# Exact client-name span in the template (the part after "M/S")
TEMPLATE_CLIENT_NAME = "WECARE CLINIC"

# Send generated PDF back to WhatsApp after update
SEND_PDF_BACK = os.getenv("SEND_PDF_BACK", "true").lower() == "true"
