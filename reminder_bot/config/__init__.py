"""
Configuration package for Reminder Bot: exports BOT_TOKEN, NURSE_CHAT_ID, and DIALOGS.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Static configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
NURSE_CHAT_ID = int(os.getenv("NURSE_CHAT_ID", "0"))

# Dialogs configuration loader
from .dialogs_loader import DIALOGS
