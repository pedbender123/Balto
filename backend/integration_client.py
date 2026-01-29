
import asyncio
import aiohttp
import json
import wave
import sys
import os

# Add backend to path to use db module directly for setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from app import db

AUDIO_FILE = os.environ.get("AUDIO_FILE", "testes/artifacts/test_10s.wav")
WS_URL = "ws://localhost:8765/ws"

async def run_client():
    print("[INTEGRATION] Starting Client Simulation...")
    
    # 1. Setup: Ensure we have a valid API Key
    try:
        # Create a temp user/balcao for testing
        print("[INTEGRATION] Setting up DB credentials...")
        import random
        rnd = random.randint(1000, 99999)
        user_code = db.create_client(f"test_integ_{rnd}@balto.ai", "Integration Test Corp", "555-0100")

        user_id = db.get_user_by_code(user_code)
        balcao_id, api_key = db.create_balcao(user_id, "Balcao Integration Test")
        print(f"[INTEGRATION] Created Balcao: {balcao_id} | Key: {api_key}")
    except Exception as e:
        print(f"[INTEGRATION] DB Setup Failed: {e}")
        # Try to continue if DB is optional or running elsewhere, 
        # but realistically this fails the test logic if we can't auth.
        return

    # 2. Connect via WebSocket
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(WS_URL) as ws:
                # Auth
                await ws.send_json({"api_key": api_key})
                print("[INTEGRATION] Connected & Authenticated.")
                
                # 3. Read Audio
                if not os.path.exists(AUDIO_FILE):
                     print(f"[INTEGRATION] Error: Audio file {AUDIO_FILE} not found.")
                     return

                # Read as raw binary to send RIFF header so FFMPEG identifies it as WAV
                with open(AUDIO_FILE, "rb") as f:
                    chunk_size = 4096 
                    data = f.read(chunk_size)
                    
                    print("[INTEGRATION] Sending Audio Stream...")
                    while data:
                        await ws.send_bytes(data)
                        await asyncio.sleep(0.1)
                        data = f.read(chunk_size)
                
                print("[INTEGRATION] Audio Stream Finished. Waiting for responses...")
                
                # Wait for a bit to receive responses
                # We expect at least one "cmd: recomendar"
                try:
                    # Wait up to 10s for response
                    msg = await ws.receive_json(timeout=10.0)
                    print(f"[INTEGRATION] Received: {msg}")
                    
                    if msg.get("comando") == "recomendar" and "itens" in msg:
                        print("[INTEGRATION] SUCCESS: Received valid recommendation batch.")
                        if len(msg["itens"]) > 0:
                             print(f"   -> Items: {len(msg['itens'])}")
                        else:
                             print("   -> Warning: Items list is empty (but format valid).")
                    else:
                        print("[INTEGRATION] WARNING: Received message but not strictly recommendation format.")
                        
                except asyncio.TimeoutError:
                    print("[INTEGRATION] TIMEOUT: No response received from AI within 10s.")
                
        except Exception as e:
            print(f"[INTEGRATION] Connection Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        pass
