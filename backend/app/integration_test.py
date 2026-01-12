
import asyncio
import aiohttp
import json
import os
import sys
import logging
from app import db
from app.core import config

# Configure logging
logger = logging.getLogger("IntegrationTest")
logger.setLevel(logging.INFO)

# Path to the test audio (relative to /backend WORKDIR)
AUDIO_FILE = os.environ.get("AUDIO_FILE", "tests/artifacts/test_10s.wav")
WS_URL = f"ws://localhost:{config.PORT}/ws"

async def run_client_simulation():
    logger.info("========================================")
    logger.info("🚀 STARTING SELF-DIAGNOSTIC TEST")
    logger.info("========================================")
    
    # 1. Setup: Ensure we have a valid API Key
    try:
        # Create a temp user/balcao for testing (randomized to valid collision)
        import random
        rnd = random.randint(10000, 99999)
        # Unique email every run
        user_code = db.create_client(f"healthcheck_{rnd}@balto.ai", "HealthCheck Corp", "000-0000")
        user_id = db.get_user_by_code(user_code)
        balcao_id, api_key = db.create_balcao(user_id, f"HealthCheck Balcao {rnd}")
        logger.info(f"[TEST] Created Balcao: {balcao_id} | Key: {api_key[:10]}...")
    except Exception as e:
        logger.error(f"[TEST] ❌ DB Setup Failed: {e}")
        return

    # 2. Connect via WebSocket
    async with aiohttp.ClientSession() as session:
        try:
            logger.info(f"[TEST] Connecting to {WS_URL} ...")
            async with session.ws_connect(WS_URL) as ws:
                # Auth
                await ws.send_json({"api_key": api_key})
                logger.info("[TEST] ✅ WebSocket Connected & Authenticated.")
                
                # 3. Read Audio
                if not os.path.exists(AUDIO_FILE):
                     logger.error(f"[TEST] ❌ Audio file {AUDIO_FILE} not found.")
                     return

                # Read as raw binary to send RIFF header so FFMPEG identifies it as WAV
                with open(AUDIO_FILE, "rb") as f:
                    chunk_size = 4096 
                    data = f.read(chunk_size)
                    
                    logger.info("[TEST] Sending Audio Stream...")
                    while data:
                        await ws.send_bytes(data)
                        await asyncio.sleep(0.1) # approx real-time
                        data = f.read(chunk_size)
                
                logger.info("[TEST] Audio Stream Finished. Waiting for AI response...")
                
                # Wait for response
                try:
                    # Wait up to 15s for response (VAD + Transcription + LLM latency)
                    msg = await ws.receive_json(timeout=15.0)
                    logger.info(f"[TEST] Received Payload: {str(msg)[:200]}...")
                    
                    if msg.get("comando") == "recomendar" and "itens" in msg:
                        logger.info("========================================")
                        logger.info("✅ SELF-TEST PASSED: Recommendation Received.")
                        logger.info(f"   Items: {len(msg['itens'])}")
                        logger.info("========================================")
                    else:
                        logger.warning("========================================")
                        logger.warning("⚠️ SELF-TEST WARNING: Protocol mismatch or empty response.")
                        logger.warning("========================================")
                        
                except asyncio.TimeoutError:
                    logger.error("========================================")
                    logger.error("❌ SELF-TEST FAILED: Timeout (No AI Response in 15s).")
                    logger.error("   Possible causes: VAD Threshold too high, OpenAI Error, or Audio too short.")
                    logger.error("========================================")
                
        except Exception as e:
             logger.error(f"========================================")
             logger.error(f"❌ SELF-TEST FAILED: Connection Error: {e}")
             logger.error(f"========================================")

async def start_startup_test():
    """Runs the test after a short delay to allow server startup."""
    if not config.RUN_STARTUP_TEST:
        return

    await asyncio.sleep(5) # Wait for server bind/start
    await run_client_simulation()
