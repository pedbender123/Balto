import asyncio
import websockets
import json
import os
from datetime import datetime

# Configurações
WS_URL = "wss://balto.pbpmdev.com/ws/debug_audio"
ADMIN_SECRET = "x9PeHTY7ouQNvzJH"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "audios_para_teste")

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_CSV = os.path.join(BASE_DIR, f"relatorio_comparativo_{TIMESTAMP}.csv")

# Configuração de Streaming
CHUNK_SIZE_MS = 100
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
CHUNK_SIZE_BYTES = int(SAMPLE_RATE * BYTES_PER_SAMPLE * (CHUNK_SIZE_MS / 1000))

CURRENT_FILENAME = "Iniciando..."

def get_audio_stream(file_path):
    try:
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                yield data
    except Exception as e:
        print(f"      ❌ Erro ao ler arquivo {file_path}: {e}")
        return

async def enviar_audios_continuos(ws, files):
    global CURRENT_FILENAME
    
    for i, file_name in enumerate(files):
        CURRENT_FILENAME = file_name
        file_path = os.path.join(INPUT_DIR, file_name)
        print(f"\n�� [{i+1}/{len(files)}] Enviando streaming: {file_name}")

        if not os.path.exists(file_path):
            print(f"❌ Arquivo não encontrado: {file_path}")
            continue

        audio_generator = get_audio_stream(file_path)
        bytes_buffer = bytearray()
        total_sent = 0
        
        for block in audio_generator:
            bytes_buffer.extend(block)
            
            while len(bytes_buffer) >= CHUNK_SIZE_BYTES:
                chunk = bytes_buffer[:CHUNK_SIZE_BYTES]
                bytes_buffer = bytes_buffer[CHUNK_SIZE_BYTES:]
                
                await ws.send(chunk)
                total_sent += len(chunk)
                await asyncio.sleep((CHUNK_SIZE_MS / 1000) * 1.1) 

        if len(bytes_buffer) > 0:
            await ws.send(bytes_buffer)
            total_sent += len(bytes_buffer)

        print(f"   📤 Enviado: {total_sent} bytes. Inserindo pausa longa (10s)...")
        
        silence_duration_ms = 10000
        silence_bytes = int(SAMPLE_RATE * BYTES_PER_SAMPLE * (silence_duration_ms / 1000))
        silence_chunk = b'\x00' * silence_bytes
        
        chunk_silence = 3200
        for j in range(0, len(silence_chunk), chunk_silence):
             await ws.send(silence_chunk[j:j+chunk_silence])
             await asyncio.sleep(0.01)

    CURRENT_FILENAME = "Finalizado"
    print("\n✅ Todos os arquivos foram enviados. Aguardando últimos eventos...")
    await asyncio.sleep(5.0)

async def receber_eventos(ws, segments_data):
    try:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            
            event_type = data.get("event", "unknown")
            event_payload = data.get("data", {})
            
            print(f"      📥 Evento recebido: {event_type}")
            
            seg_id = event_payload.get("segment_id")
            
            if event_type == "segment_created":
                if not seg_id:
                    seg_id = f"unknown_{len(segments_data)}"
                
                segments_data[seg_id] = {
                    "id": seg_id,
                    "source_file": CURRENT_FILENAME,
                    "duration": event_payload.get("duration_seconds", 0),
                    "routing": {},
                    "transcriptions": {},
                    "analysis": {},
                    "raw_events": []
                }
                print(f"      🔹 Segmento detectado: {seg_id} ({event_payload.get('duration_seconds')}s)")

            elif seg_id and seg_id in segments_data:
                if event_type == "routing_decision":
                    segments_data[seg_id]["routing"] = event_payload
                
                elif event_type == "transcription_result":
                    segments_data[seg_id]["transcriptions"] = event_payload.get("transcriptions", {})
                    segments_data[seg_id]["chosen_stt"] = event_payload.get("chosen_for_analysis")

                elif event_type == "analysis_result":
                    segments_data[seg_id]["analysis"] = event_payload.get("analysis", {})
                    print(f"      ✨ Análise concluída para {seg_id}")
            
            else:
                 print(f"      ❓ Evento ignorado ou ID ausente: {event_type} - ID: {seg_id}")

    except websockets.exceptions.ConnectionClosed:
        print("   🔌 Conexão fechada pelo servidor.")

async def main():
    print("🚀 Iniciando Teste Comparativo Contínuo (Single Connection)")
    print(f"📁 Pasta de Entrada: {INPUT_DIR}")
    print(f"📄 Arquivo de Saída: {OUTPUT_CSV}")
    print(f"🔗 URL: {WS_URL}")

    if not os.path.exists(INPUT_DIR):
        print(f"❌ Diretório de entrada não encontrado: {INPUT_DIR}")
        return

    files = sorted([f for f in os.listdir(INPUT_DIR) if not f.startswith('.')])
    if not files:
        print("❌ Nenhum arquivo encontrado.")
        return

    print(f"📊 Encontrados {len(files)} arquivos para processar na sessão.")

    headers = [
        "Arquivo_Origem", "Segmento_ID", "Duracao_(s)", 
        "Routing_Model", "Routing_Reason",
        "Transcricao_ElevenLabs", "Transcricao_AssemblyAI",
        "Recomendacao_Produto", "Confianca", "Explicacao_IA"
    ]

    segments_data = {}

    try:
        async with websockets.connect(
            WS_URL + f"?key={ADMIN_SECRET}",
            ping_interval=30,
            ping_timeout=60
        ) as ws:
            print("   ✅ Conectado ao WebSocket de Debug")

            receber_task = asyncio.create_task(receber_eventos(ws, segments_data))
            await enviar_audios_continuos(ws, files)
            receber_task.cancel()
            
    except Exception as e:
        print(f"\n❌ Erro Fatal na Conexão: {e}")
    
    print("💾 Salvando relatório...")
    import csv
    with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        count = 0
        for seg_id, data in segments_data.items():
            analysis = data.get("analysis", {})
            transcriptions = data.get("transcriptions", {})
            routing = data.get("routing", {})
            
            writer.writerow([
                data.get("source_file", "Unknown"),
                seg_id,
                f"{data.get('duration', 0):.2f}",
                routing.get("suggested_model", "N/A"),
                routing.get("reason", "N/A"),
                transcriptions.get("elevenlabs", ""),
                transcriptions.get("assemblyai", ""),
                analysis.get("produto", ""),
                analysis.get("confianca", ""),
                analysis.get("explicacao", "")
            ])
            count += 1
            
        print(f"📝 {count} segmentos registrados no relatório.")

    print(f"✅ Teste concluído. Relatório: {OUTPUT_CSV}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Teste interrompido pelo usuário.")
    except ConnectionRefusedError:
        print(f"\n❌ Falha na conexão: Não foi possível conectar a {WS_URL}")
        print("Verifique se o servidor Balto está rodando e se a porta está correta.")
