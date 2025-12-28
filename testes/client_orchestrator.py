import os
import requests
import base64
import json
import time

# Configurações
SERVER_URL = "https://balto.pbpmdev.com" # Apontando para VPS Produção
# Se rodar local na VPS, localhost ok. Se rodar do seu PC, tunnel ou IP.
# O user pediu "script para rodar na minha máquina". Assumindo acesso HTTP à VPS.
# Mas o user disse "não no servidor".
# Assumindo que o usuário vai configurar a URL certa ou rodamos via tunnel.
# Vou deixar localhost default mas fácil de mudar.

INPUT_DIR = "1_input"
SEGMENTS_DIR = "2_cortados"
TRANSCRIPTS_DIR = "3_transcricoes"
ANALYSIS_DIR = "4_analises"

def ensure_dirs():
    for d in [INPUT_DIR, SEGMENTS_DIR, TRANSCRIPTS_DIR, ANALYSIS_DIR]:
        os.makedirs(d, exist_ok=True)

def step_1_segmentation(filename):
    print(f"\n--- [1] Segmentação: {filename} ---")
    file_path = os.path.join(INPUT_DIR, filename)
    if not os.path.exists(file_path):
        print("Arquivo input não encontrado.")
        return []

    with open(file_path, 'rb') as f:
        files = {'audio': (filename, f, 'audio/webm')} # Mime type generico
        try:
            res = requests.post(f"{SERVER_URL}/api/test/segmentar", files=files)
            if res.status_code != 200:
                print(f"Erro Segmentação: {res.text}")
                return []
            
            data = res.json()
            segments = data.get("segments", [])
            print(f"Segmentos encontrados: {len(segments)}")
            
            saved_files = []
            for i, seg in enumerate(segments):
                # Salvar RAW PCM (que veio do server)
                # O server mandou PCM RAW (s16le).
                # Para transcrever depois, precisamos que seja WAV ou RAW aceito.
                # Vamos salvar como .raw por enquanto e converter ou enviar wrapper.
                # Melhor: O server mandou base64 do PCM. Vamos salvar em disco.
                
                raw_bytes = base64.b64decode(seg["audio_base64"])
                
                # Salvar como WAV localmente para facilitar
                import wave
                out_name = f"{os.path.splitext(filename)[0]}_seg_{i:03d}.wav"
                out_path = os.path.join(SEGMENTS_DIR, out_name)
                
                with wave.open(out_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(raw_bytes)
                
                saved_files.append(out_name)
                print(f"   -> Salvo: {out_name} ({seg['duration_sec']:.2f}s)")
                
            return saved_files
            
        except Exception as e:
            print(f"Erro Req: {e}")
            return []

def step_2_transcription(seg_filename):
    print(f"\n--- [2] Transcrição: {seg_filename} ---")
    seg_path = os.path.join(SEGMENTS_DIR, seg_filename)
    
    results = {}
    
    for provider in ["elevenlabs", "assemblyai"]:
        print(f"   -> Enviando para {provider}...")
        try:
            with open(seg_path, 'rb') as f:
                # O arquivo já é WAV (salvo no passo 1)
                files = {
                    'audio': (seg_filename, f, 'audio/wav'),
                    'provider': (None, provider)
                }
                res = requests.post(f"{SERVER_URL}/api/test/transcrever", files=files)
                
                if res.status_code == 200:
                    text = res.json().get("texto", "")
                    print(f"      Texto: '{text}'")
                    
                    # Salvar txt
                    out_txt = f"{os.path.splitext(seg_filename)[0]}_{provider}.txt"
                    with open(os.path.join(TRANSCRIPTS_DIR, out_txt), 'w') as ft:
                        ft.write(text)
                        
                    results[provider] = text
                else:
                    print(f"      Erro: {res.text}")
                    results[provider] = ""
                    
        except Exception as e:
            print(f"      Exceção: {e}")
            results[provider] = ""
            
    return results

def step_3_analysis(seg_filename, text_dict):
    print(f"\n--- [3] Análise: {seg_filename} ---")
    
    # Vamos analisar a transcrição do ElevenLabs como principal (ou qual vier preenchida)
    texto_base = text_dict.get("elevenlabs") or text_dict.get("assemblyai")
    
    if not texto_base:
        print("   -> Sem texto para analisar.")
        return

    try:
        payload = {"texto": texto_base}
        res = requests.post(f"{SERVER_URL}/api/test/analisar", json=payload)
        
        if res.status_code == 200:
            analysis_data = res.json()
            print("   -> Resultado:", json.dumps(analysis_data, indent=2, ensure_ascii=False))
            
            # Salvar JSON
            out_json = f"{os.path.splitext(seg_filename)[0]}_analysis.json"
            with open(os.path.join(ANALYSIS_DIR, out_json), 'w') as fj:
                json.dump(analysis_data, fj, indent=2, ensure_ascii=False)
        else:
            print(f"   -> Erro: {res.text}")
            
    except Exception as e:
        print(f"   -> Exceção: {e}")

def run_pipeline():
    ensure_dirs()
    
    # Pegar primeiro arquivo de input
    inputs = [f for f in os.listdir(INPUT_DIR) if not f.startswith('.')]
    if not inputs:
        print(f"Pasta '{INPUT_DIR}' vazia. Coloque um arquivo de áudio lá.")
        return

    target_file = inputs[0] # Testar com o primeiro
    print(f"=== Iniciando Pipeline para: {target_file} ===")
    
    # 1. Segmentar
    segment_files = step_1_segmentation(target_file)
    
    if not segment_files:
        print("Nenhum segmento gerado. Fim.")
        return
        
    # 2 & 3. Transcrever e Analisar cada segmento
    for seg_file in segment_files:
        transcripts = step_2_transcription(seg_file)
        step_3_analysis(seg_file, transcripts)
        
    print("\n=== Pipeline Finalizado ===")

if __name__ == "__main__":
    run_pipeline()
