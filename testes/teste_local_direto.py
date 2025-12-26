import os
import sys
import csv
from datetime import datetime
import numpy as np

# Adicionar o diretório pai ao path para importar modulos do backend
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from app.silero_vad import SileroVAD
    from app.transcription import transcrever_inteligente, decidir_roteamento, key_manager, ASSEMBLYAI_API_KEY
except ImportError as e:
    print(f"Erro ao importar módulos do backend: {e}")
    sys.exit(1)

# Configurações
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "audios_para_teste")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_CSV = os.path.join(BASE_DIR, f"relatorio_local_{TIMESTAMP}.csv")

# Carregar .env manualmente se necessário (já que estamos rodando fora do contexto do server)
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '..', 'backend', '.env'))

# Recarregar chaves de ambiente após load_dotenv
if not key_manager.keys or not key_manager.keys[0]:
    # Tenta reinicializar o manager se as chaves estavam vazias antes do load_dotenv
    pass # O import já instanciou, mas as env vars podiam não estar lá.
    # Hack simples: recriar ou injetar
    keys_str = os.environ.get("ELEVENLABS_API_KEYS", "") or os.environ.get("ELEVENLABS_API_KEY", "")
    key_manager.keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    print(f"[Setup] Chaves ElevenLabs recarregadas: {len(key_manager.keys)}")

def run_local_test():
    print("🚀 Iniciando Processamento Local Direto (Bypass Server)")
    print(f"📁 Pasta de Entrada: {INPUT_DIR}")
    print(f"📄 Arquivo de Saída: {OUTPUT_CSV}")

    if not os.path.exists(INPUT_DIR):
        print(f"❌ Diretório de entrada não encontrado: {INPUT_DIR}")
        return

    files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith('.webm') or f.endswith('.wav')])
    if not files:
        print("❌ Nenhum arquivo de áudio encontrado.")
        return

    print(f"📊 Encontrados {len(files)} arquivos.")

    # Inicializar VAD
    try:
        vad = SileroVAD()
    except Exception as e:
        print(f"❌ Falha ao carregar SileroVAD: {e}")
        return

    csv_headers = [
        "Arquivo_Origem", "Segmento_ID", "Inicio(s)", "Fim(s)", "Duracao(s)", 
        "Routing_Model", "Routing_Reason",
        "Texto_Transcrito", "Custo_Estimado", "SNR"
    ]
    
    results = []

    for i, filename in enumerate(files):
        print(f"\n📂 Processando [{i+1}/{len(files)}]: {filename}")
        file_path = os.path.join(INPUT_DIR, filename)

        try:
            # Converter para PCM
            pcm_data = convert_webm_to_pcm(file_path)
            if not pcm_data:
                print("      ❌ Falha na conversão de áudio.")
                continue

            # Processar VAD
            print(f"   🔍 Analisando VAD...")
            segments = vad.get_speech_segments(pcm_data)
            print(f"      🔹 Segmentos detectados: {len(segments)}")

            if not segments:
                print("      ⚠️ Nenhum segmento de fala detectado neste arquivo.")

            for j, segment_bytes in enumerate(segments):
                seg_duration = len(segment_bytes) / 32000.0
                print(f"      🗣️ Segmento {j+1}: {seg_duration:.2f}s | Processando Transcrição...")

                # Transcrição
                result = transcrever_inteligente(segment_bytes)
                
                row = {
                    "Arquivo_Origem": filename,
                    "Segmento_ID": f"{filename}_seg_{j+1}",
                    "Inicio(s)": "N/A",
                    "Fim(s)": "N/A",
                    "Duracao(s)": f"{seg_duration:.2f}",
                    "Routing_Model": result.get("modelo"),
                    "Routing_Reason": "Local Logic",
                    "Texto_Transcrito": result.get("texto"),
                    "Custo_Estimado": result.get("custo"),
                    "SNR": f"{result.get('snr', 0):.2f}"
                }
                
                results.append(row)
                texto_preview = result.get('texto', '') or ''
                print(f"         ✅ Texto: {texto_preview[:50]}...")

        except Exception as e:
            print(f"   ❌ Erro no arquivo {filename}: {e}")

    # Salvar CSV
    print(f"\n💾 Salvando CSV em {OUTPUT_CSV}...")
    with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print("✅ Concluído!")

def convert_webm_to_pcm(input_path):
    import subprocess
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    try:
        command = [
            ffmpeg_exe, '-i', input_path,
            '-f', 's16le', '-ac', '1', '-ar', '16000',
            '-v', 'quiet', '-'
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        
        if process.returncode != 0:
            print(f"Erro ffmpeg: {err.decode('utf-8', errors='ignore')}")
            return None
        return out
    except Exception as e:
        print(f"Erro subprocess ffmpeg: {e}")
        return None

if __name__ == "__main__":
    run_local_test()
