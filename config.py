import os
from dotenv import load_dotenv

load_dotenv()

# Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

# The bot's own WhatsApp number — messages sent TO this number trigger PDF generation
BOT_JID = os.getenv("BOT_JID", "")
ALLOWED_JIDS: set[str] = set()  # no sender restriction — any number can trigger

# PDF template settings
TEMPLATE_PDF = os.getenv("TEMPLATE_PDF", "Wecare-Clinic-Business-Proposal.pdf")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

# Exact client-name span in the template (the part after "M/S")
TEMPLATE_CLIENT_NAME = "WECARE CLINIC"

# Exact price span in the template (page 3)
TEMPLATE_PRICE = "2,400AED/Yearly"

# Send generated PDF back to WhatsApp after update
SEND_PDF_BACK = os.getenv("SEND_PDF_BACK", "true").lower() == "true"
