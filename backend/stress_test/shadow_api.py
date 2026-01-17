
import os
import time
import json
import asyncio
import httpx
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any

app = FastAPI()

# In-memory storage for 'Spy' mode
RECORDED_RESPONSES = {
    "openai": [],
    "assemblyai_transcript": []
}
START_TIME = time.time()

# Configuration
REAL_OPENAI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
REAL_ASSEMBLYAI_URL = "https://api.assemblyai.com"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY")

def is_spy_mode():
    # Minute 0-1 is Spy Mode
    return (time.time() - START_TIME) < 60

@app.post("/reset")
def reset_timer():
    global START_TIME
    START_TIME = time.time()
    return {"message": "Timer reset. Spy Mode active for 60s."}

# --- OpenAI Handler ---

@app.post("/v1/chat/completions")
async def openai_proxy(request: Request):
    body = await request.json()
    
    if is_spy_mode() or not RECORDED_RESPONSES["openai"]:
        # Relay to Real API
        start = time.time()
        print("[ShadowAPI] SPY MODE: Forwarding to OpenAI...")
        if OPENAI_API_KEY is None:
             print("[ShadowAPI] Error: OPENAI_API_KEY not foundenv")
             return Response(content="Missing Key", status_code=500)
             
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{REAL_OPENAI_URL}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
                )
                data = resp.json()
                duration = time.time() - start
                
                # Save for later
                RECORDED_RESPONSES["openai"].append({
                    "data": data,
                    "duration": duration
                })
                print(f"[ShadowAPI] Recorded OpenAI response ({duration:.2f}s)")
                return data
            except Exception as e:
                print(f"[ShadowAPI] OpenAI Spy Error: {e}")
                return Response(status_code=500)
    else:
        # Parrot Mode
        import random
        record = random.choice(RECORDED_RESPONSES["openai"])
        delay = record["duration"]
        print(f"[ShadowAPI] PARROT MODE: Returning cached OpenAI response (delay {delay:.2f}s)")
        await asyncio.sleep(delay)
        return record["data"]

# --- AssemblyAI Handler ---

@app.post("/assemblyai/v2/upload")
async def assemblyai_upload(request: Request):
    # Always mock upload or pass through?
    # Upload is fast, we can probably just mock it directly or pass through once.
    # Let's pass through in Spy, mock in Parrot returning a fake URL.
    
    if is_spy_mode():
         print("[ShadowAPI] SPY MODE: Forwarding Upload to AssemblyAI...")
         content = await request.body()
         async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{REAL_ASSEMBLYAI_URL}/v2/upload",
                content=content,
                headers={"Authorization": ASSEMBLYAI_API_KEY}
            )
            return resp.json()
    else:
        # Parrot Upload
        return {"upload_url": "https://cdn.assemblyai.com/upload/fake_url"}

@app.post("/assemblyai/v2/transcript")
async def assemblyai_transcript(request: Request):
    body = await request.json()
    
    if is_spy_mode():
        print("[ShadowAPI] SPY MODE: Forwarding Transcript Request...")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{REAL_ASSEMBLYAI_URL}/v2/transcript",
                json=body,
                headers={"Authorization": ASSEMBLYAI_API_KEY}
            )
            data = resp.json()
            # We don't record the *request* response effectively here, we need the *poll* result.
            # But we need to return a valid ID.
            return data
    else:
        import uuid
        fake_id = str(uuid.uuid4())
        return {"id": fake_id, "status": "queued"}

@app.get("/assemblyai/v2/transcript/{transcript_id}")
async def assemblyai_poll(transcript_id: str):
    # If it's a real ID (Spy Mode), we might proxy.
    # But usually we want to capture the final TEXT.
    
    # Simplified Logic:
    # Spy Mode: Proxy. If status=completed, save the text.
    # Parrot Mode: Return queued... then completed with saved text.
    
    if is_spy_mode():
         async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{REAL_ASSEMBLYAI_URL}/v2/transcript/{transcript_id}",
                headers={"Authorization": ASSEMBLYAI_API_KEY}
            )
            data = resp.json()
            if data.get("status") == "completed":
                RECORDED_RESPONSES["assemblyai_transcript"].append(data["text"])
                print(f"[ShadowAPI] Captured AssemblyAI Text: {data['text'][:30]}...")
            return data
    else:
        # Parrot Mode
        # Simulate processing time randomly or fixed
        if not RECORDED_RESPONSES["assemblyai_transcript"]:
             return {"status": "processing"} # Fail-safe if Spy caught nothing
             
        import random
        if random.random() < 0.2: # 20% chance of completion per poll
             text = random.choice(RECORDED_RESPONSES["assemblyai_transcript"])
             return {"status": "completed", "text": text}
        else:
             return {"status": "processing"}

