import asyncio
import aiohttp
import json
import os
import sys
import time

# Configurações
WS_URL = os.environ.get("BALTO_WS_URL", "ws://localhost:8765/ws")
# Procurar um áudio real na pasta de assets
POSSIBLE_AUDIO_PATHS = [
    "assets/test_10s.wav",
    "assets/test_audio.wav"
]

async def test_websocket_flow(api_key):
    print(f"\n--- Testing WebSocket Flow on {WS_URL} ---")
    
    if not api_key:
        print("❌ Error: No API Key provided for WebSocket test.")
        return

    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(WS_URL) as ws:
                # 1. Handshake / Auth
                print(f"[WS] Sending Auth (Key: {api_key[:10]}...)")
                await ws.send_json({"api_key": api_key})
                
                # 2. Simulation - Stream Audio
                audio_file = None
                script_dir = os.path.dirname(os.path.abspath(__file__))
                for path in POSSIBLE_AUDIO_PATHS:
                    abs_path = os.path.join(script_dir, path)
                    if os.path.exists(abs_path):
                        audio_file = abs_path
                        break
                
                if not audio_file:
                    print("⚠️ Warning: No test audio found. Testing only connection and auth.")
                    # Aguardar um pequeno ping-pong se houver
                    try:
                        msg = await ws.receive(timeout=2.0)
                        print(f"[WS] Received: {msg.data}")
                    except asyncio.TimeoutError:
                        print("[WS] No message received (expected if no audio sent).")
                else:
                    print(f"[WS] Streaming audio: {os.path.basename(audio_file)}")
                    with open(audio_file, "rb") as f:
                        # Enviar em chunks para simular tempo real
                        chunk = f.read(4096)
                        while chunk:
                            await ws.send_bytes(chunk)
                            await asyncio.sleep(0.05)
                            chunk = f.read(4096)
                    
                    print("[WS] Stream finished. Waiting for recommendation...")
                    try:
                        # Timeout maior para IA processar
                        msg = await ws.receive_json(timeout=15.0)
                        print(f"✅ [WS] RECOMMENDATION RECEIVED: {json.dumps(msg, indent=2)}")
                    except asyncio.TimeoutError:
                        print("❌ [WS] TIMEOUT: No recommendation received after 15s.")
                    except Exception as e:
                        print(f"❌ [WS] ERROR receiving JSON: {e}")
                
                print("[WS] Closing connection.")
                await ws.close()
                
        except Exception as e:
            print(f"❌ [WS] CONNECTION FAILED: {e}")

async def main():
    # Se rodar isoladamente, tenta pegar do env ou falha
    api_key = os.environ.get("BALTO_API_KEY")
    if not api_key:
        print("⚠️ No BALTO_API_KEY found in env. Running flow will likely fail auth unless hardcoded or passed.")
    
    await test_websocket_flow(api_key)

if __name__ == "__main__":
    asyncio.run(main())
