import requests
import os
import sys

# VPS URL
SERVER_URL = os.environ.get("BALTO_SERVER_URL", "https://balto.pbpmdev.com")
PROVIDERS = ["elevenlabs", "assemblyai", "deepgram", "gladia"]

# Create a dummy wav file if not exists (silence or small noise) or use an existing one
# We need a valid audio file. Let's use one from input if available or create a tiny one.
TEST_FILE = "testes/1_input/test_audio.wav"

def create_dummy_wav(filename):
    import wave
    import struct
    with wave.open(filename, 'w') as w:
        w.setparams((1, 2, 16000, 16000, 'NONE', 'not compressed'))
        # 1 sec of silence/noise
        for i in range(16000):
            value = struct.pack('<h', 0)
            w.writeframes(value)

def test_provider(provider, filepath):
    print(f"Testing Provider: {provider.upper()} ...", end=" ", flush=True)
    try:
        with open(filepath, 'rb') as f:
            files = {
                'audio': ('test.wav', f, 'audio/wav'),
                'provider': (None, provider)
            }
            # Add short timeout
            res = requests.post(f"{SERVER_URL}/api/test/transcrever", files=files, timeout=60)
            
            if res.status_code == 200:
                text = res.json().get("texto", "")
                print(f"OK!")
                print(f"   -> Response: {text[:50]}...")
                return True
            else:
                print(f"FAIL! (Status {res.status_code})")
                print(f"   -> Error: {res.text}")
                return False
    except Exception as e:
        print(f"EXCEPTION!")
        print(f"   -> {e}")
        return False

def main():
    # Ensure we have a file
    target_file = None
    input_dir = "testes/1_input"
    if os.path.exists(input_dir):
        files = [f for f in os.listdir(input_dir) if f.endswith('.webm') or f.endswith('.wav')]
        if files:
            target_file = os.path.join(input_dir, files[0])
            print(f"Using existing file: {target_file}")
    
    if not target_file:
         create_dummy_wav("test_dummy.wav")
         target_file = "test_dummy.wav"
         print("Created dummy file: test_dummy.wav")

    success_count = 0
    for p in PROVIDERS:
        if test_provider(p, target_file):
            success_count += 1
    
    print(f"\nSummary: {success_count}/{len(PROVIDERS)} providers working.")

if __name__ == "__main__":
    main()
