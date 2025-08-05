"""
Centralised static configuration moved into the config package.
BOT_TOKEN and NURSE_CHAT_ID are loaded from environment variables or fallback defaults.
"""
import os
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
NURSE_CHAT_ID = int(os.getenv("NURSE_CHAT_ID", "0"))
