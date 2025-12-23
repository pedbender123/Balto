import os
import sys
import subprocess
import wave
import numpy as np

# Adicionar o diretório pai ao path para importar 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import audio_processor, vad

def check_ffmpeg():
    """Verifica se o ffmpeg está instalado e acessível."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

def convert_webm_to_pcm(input_path):
    """
    Converte .webm (ou qualquer formato suportado pelo ffmpeg) para PCM 16kHz 16bit mono bytes.
    Retorna os bytes crus do áudio.
    """
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-f", "s16le",       # Formato PCM 16-bit little-endian
        "-acodec", "pcm_s16le",
        "-ac", "1",          # 1 canal (mono)
        "-ar", "16000",      # 16kHz
        "-"                  # Output para stdout
    ]
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        
        if process.returncode != 0:
            print(f"Erro no ffmpeg ao converter {input_path}: {err.decode('utf-8')}")
            return None
            
        return out
    except Exception as e:
        print(f"Erro ao executar ffmpeg: {e}")
        return None

def batch_process():
    base_dir = os.path.dirname(__file__)
    input_dir = os.path.join(base_dir, 'audios_brutos')
    segments_dir = os.path.join(base_dir, 'trechos_fala')

    # Garantir que diretórios existam
    os.makedirs(segments_dir, exist_ok=True)

    if not check_ffmpeg():
        print("ERRO: 'ffmpeg' não encontrado no sistema.")
        print("Por favor, instale o ffmpeg para processar arquivos .webm.")
        print("Comando sugerido: sudo apt install ffmpeg")
        return

    # Buscar arquivos suportados
    extensions = ('.webm', '.wav', '.mp3', '.ogg', '.m4a')
    files = [f for f in os.listdir(input_dir) if f.lower().endswith(extensions)]
    
    if not files:
        print(f"Nenhum arquivo de áudio encontrado em {input_dir}")
        print(f"Extensões procuradas: {extensions}")
        return

    print(f"Encontrados {len(files)} arquivos para processar.")

    for file_name in files:
        input_path = os.path.join(input_dir, file_name)
        print(f"\n--- Processando: {file_name} ---")

        # 1. Converter/Ler Áudio
        print("   -> Convertendo/Lendo áudio...")
        raw_audio = convert_webm_to_pcm(input_path)
        
        if not raw_audio:
            print("   -> Falha na leitura do áudio. Pulando.")
            continue

        # Inicializar processadores
        cleaner = audio_processor.AudioCleaner()
        vad_session = vad.VAD(vad_aggressiveness=3) # Modo agressivo para garantir apenas fala limpa

        # Configurações de processamento em chunks
        chunk_duration_ms = 30 
        sample_rate = 16000
        bytes_per_sample = 2 # 16-bit
        chunk_size = int(sample_rate * (chunk_duration_ms / 1000.0) * bytes_per_sample)
        
        total_len = len(raw_audio)
        offset = 0
        segment_counter = 0

        print(f"   -> Iniciando VAD e Limpeza (Total: {total_len} bytes)...")
        
        while offset < total_len:
            # Pegar chunk
            chunk = raw_audio[offset : offset + chunk_size]
            offset += chunk_size
            
            # Se chunk final for menor que o esperado, preencher com silêncio ou processar como está?
            # VAD pode reclamar de tamanho incorreto. Melhor ignorar sobras muito pequenas.
            if len(chunk) < chunk_size:
                continue

            # 2. Limpeza
            # Aplicar limpeza em chunks pode introduzir artefatos nas bordas se não tiver overlap/estado.
            # O AudioCleaner atual é stateless mas usa noisereduce que recomenda sinais maiores.
            # Para o batch, talvez fosse melhor limpar o arquivo inteiro primeiro se a memória permitir.
            # Mas vamos manter a lógica de stream para consistência com o server.
            cleaned_chunk = cleaner.process(chunk)
            
            # 3. VAD
            speech_segment = vad_session.process(cleaned_chunk)

            if speech_segment:
                segment_counter += 1
                base_name = os.path.splitext(file_name)[0]
                seg_name = f"{base_name}_seg_{segment_counter:02d}.wav"
                seg_path = os.path.join(segments_dir, seg_name)
                
                with wave.open(seg_path, 'wb') as seg_wf:
                    seg_wf.setnchannels(1)
                    seg_wf.setsampwidth(2)
                    seg_wf.setframerate(16000)
                    seg_wf.writeframes(speech_segment)
                
                print(f"      [Salvo] {seg_name} ({len(speech_segment)/32000:.2f}s)")

    print("\nProcessamento em lote concluído!")

if __name__ == "__main__":
    batch_process()
