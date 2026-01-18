
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

# Mock Details
MOCK_VOICE = os.environ.get("MOCK_VOICE") == "1"
MOCK_LATENCY_MIN = float(os.environ.get("MOCK_LATENCY_MIN", 0.5))
MOCK_LATENCY_MAX = float(os.environ.get("MOCK_LATENCY_MAX", 2.0))

# Startup Test
RUN_STARTUP_TEST = os.environ.get("RUN_STARTUP_TEST") == "1"

# Stress Test Mode (War Mode)
STRESS_TEST_MODE = os.environ.get("STRESS_TEST_MODE") == "True"
STRESS_DURATION_MINUTES = int(os.environ.get("STRESS_DURATION_MINUTES", 60))
STRESS_CLIENTS = int(os.environ.get("STRESS_CLIENTS", 5))
STRESS_AUDIO_FILE = os.environ.get("STRESS_AUDIO_FILE", "../8_20250702093051.webm")
STRESS_REPORT_EMAIL = os.environ.get("STRESS_REPORT_EMAIL")

# API Base URLs
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", None) # Default to official if None
ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com"

# Capacity Guard Defaults
CAPACITY_MAX_CPU_PERCENT = float(os.environ.get("CAPACITY_MAX_CPU_PERCENT", 90.0))
CAPACITY_MAX_RAM_PERCENT = float(os.environ.get("CAPACITY_MAX_RAM_PERCENT", 90.0))
CAPACITY_MAX_LATENCY_RATIO = float(os.environ.get("CAPACITY_MAX_LATENCY_RATIO", 3.0))
