
import os
from dotenv import load_dotenv

load_dotenv()

# Server Settings
# Server Settings
PORT = int(os.environ.get("PORT", 8765))

def parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.lower() in ("true", "1", "yes", "on")

MOCK_MODE = parse_bool(os.environ.get("MOCK_MODE"))
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin123")
SAVE_AUDIO = parse_bool(os.environ.get("SAVE_AUDIO_DUMPS"))
AUDIO_DUMP_DIR = os.environ.get("AUDIO_DUMP_DIR", "./audio_dumps")

# OpenAI Settings
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[WARNING] OPENAI_API_KEY not found in environment variables.")

# Smart Routing (Legacy Support)
SMART_ROUTING_ENABLE = parse_bool(os.environ.get("SMART_ROUTING_ENABLE"))

# Mock Details
MOCK_VOICE = parse_bool(os.environ.get("MOCK_VOICE"))
MOCK_LATENCY_MIN = float(os.environ.get("MOCK_LATENCY_MIN", 0.5))
MOCK_LATENCY_MAX = float(os.environ.get("MOCK_LATENCY_MAX", 2.0))
MOCK_RECOMMENDATION = parse_bool(os.environ.get("MOCK_RECOMMENDATION"))

# Startup Test
RUN_STARTUP_TEST = parse_bool(os.environ.get("RUN_STARTUP_TEST"))

# Stress Test Mode (War Mode)
STRESS_TEST_MODE = parse_bool(os.environ.get("STRESS_TEST_MODE"))
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

# Drive Sync Settings
DRIVE_SYNC_ENABLED = parse_bool(os.environ.get("DRIVE_SYNC_ENABLED", "True"))
DRIVE_SYNC_INTERVAL_MINUTES = int(os.environ.get("DRIVE_SYNC_INTERVAL_MINUTES", 30))

# Simple Chunk Mode: bypasses VAD, SileroVAD, Speaker ID, AudioAnalysis
# Sends fixed-duration 5s chunks directly to transcription with 0.8s overlap
# To revert to VAD-based flow, set SIMPLE_CHUNK_MODE = False
SIMPLE_CHUNK_MODE = True
