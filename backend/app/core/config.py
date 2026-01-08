
import os
from dotenv import load_dotenv

load_dotenv()

# Server Settings
PORT = int(os.environ.get("PORT", 8765))
MOCK_MODE = os.environ.get("MOCK_MODE") == "1"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")
SAVE_AUDIO = os.environ.get("SAVE_AUDIO_DUMPS") == "1"
AUDIO_DUMP_DIR = os.environ.get("AUDIO_DUMP_DIR", "./audio_dumps")

# OpenAI Settings
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[WARNING] OPENAI_API_KEY not found in environment variables.")

# Smart Routing (Legacy Support)
SMART_ROUTING_ENABLE = os.environ.get("SMART_ROUTING_ENABLE") == "1"
