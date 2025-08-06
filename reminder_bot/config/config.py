import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
NURSE_CHAT_ID = int(os.getenv("NURSE_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment")

if NURSE_CHAT_ID == 0:
    # Will be used for escalation if needed
    raise RuntimeError("NURSE_CHAT_ID not set or invalid in environment")
