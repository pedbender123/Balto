import asyncio
import websockets
import json
import os
import uuid
from dotenv import load_dotenv

# Importa os módulos locais
import db
import vad
import transcription
import analysis

# Carrega variáveis de ambiente (OPENAI_API_KEY, DB_FILE)
load_dotenv()

# Armazenamento temporário para interações pendentes de feedback
# Chave: id_interacao, Valor: (transcricao, recomendacao)
pending_interactions = {}

async def process_speech_pipeline(websocket, speech_segment: bytes, client_id: str):
    """
    Executa a pipeline de IA (Transcrição -> Análise) em uma thread separada
    para não bloquear o loop principal de áudio.
    Baseado nas fontes 85, 86, 89.
    """
    print(f"[{client_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")
    
    # 1. Transcrição (Lenta, I/O-bound) (fonte 87)
    try:
        texto_transcrito = await asyncio.to_thread(
            transcription.transcrever, 
            speech_segment
        )
        print(f"[{client_id}] Transcrição: {texto_transcrito}")

        if not texto_transcrito or texto_transcrito.startswith("[Erro"):
            return

        # 2. Análise (Lenta, I/O-bound) (fonte 89)
        recomendacao = await asyncio.to_thread(
            analysis.analisar_texto, 
            texto_transcrito
        )

        # 3. Envio da Recomendação (fonte 90)
        if recomendacao:
            id_interacao = str(uuid.uuid4())
            
            # Armazena para o feedback futuro
            pending_interactions[id_interacao] = (texto_transcrito, recomendacao)
            
            payload = {
                "comando": "recomendar",
                "mensagem": recomendacao,
                "id_interacao": id_interacao
            } # (fonte 14)
            
            await websocket.send(json.dumps(payload))
            print(f"[{client_id}] Recomendação enviada: {recomendacao}")
            
    except Exception as e:
        print(f"[{client_id}] Erro na pipeline de IA: {e}")


async def handle_client(websocket): # <-- CORREÇÃO: Removemos o ', path'
    """
    Gerencia a conexão de um único cliente (balcão).
    Baseado na fonte 80.
    """
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    print(f"Cliente conectado: {client_id}")
    
    # Cria uma instância VAD "stateful" para este cliente (fonte 99)
    client_vad = vad.VAD()

    try:
        # Loop principal: escuta por mensagens (áudio ou feedback)
        async for message in websocket:
            
            if isinstance(message, bytes):
                # 1. Mensagem é ÁUDIO (fonte 12)
                
                # --- NOSSO TESTE DE DEBUG ---
                print(f"[{client_id}] Recebi {len(message)} bytes de áudio.")
                # --- FIM DO TESTE ---

                # Passa o chunk para o VAD (fonte 83)
                speech_segment = client_vad.process(message)
                
                # Se o VAD retornar um segmento de fala completo... (fonte 84)
                if speech_segment:
                    # ...inicia a pipeline de IA sem bloquear o loop
                    asyncio.create_task(
                        process_speech_pipeline(websocket, speech_segment, client_id)
                    )

            elif isinstance(message, str):
                # 2. Mensagem é TEXTO (JSON de Feedback) (fonte 15)
                try:
                    data = json.loads(message)
                    
                    if data.get("comando") == "feedback": # (fonte 91)
                        id_interacao = data.get("id_interacao")
                        resultado = data.get("resultado")
                        
                        if id_interacao in pending_interactions:
                            # Recupera os dados da interação
                            transcricao, recomendacao = pending_interactions.pop(id_interacao)
                            
                            # Registra no banco de dados
                            db.registrar_interacao(transcricao, recomendacao, resultado)
                            print(f"[{client_id}] Feedback recebido e salvo: {id_interacao} -> {resultado}")
                        else:
                            print(f"[{client_id}] Feedback recebido para ID desconhecido: {id_interacao}")
                            
                except json.JSONDecodeError:
                    print(f"[{client_id}] Recebida mensagem de texto inválida (não-JSON).")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Cliente desconectado: {client_id} (Motivo: {e.code} {e.reason})")
    except Exception as e:
        print(f"Erro inesperado com cliente {client_id}: {e}")
    finally:
        print(f"Conexão com {client_id} fechada.")


async def main():
    # Inicializa o banco de dados ao iniciar (fonte 125)
    db.inicializar_db()
    
    port = int(os.environ.get("PORT", 8765))
    print(f"Iniciando servidor WebSocket na porta {port}...")
    
    async with websockets.serve(handle_client, "0.0.0.0", port):
        await asyncio.Future()  # Roda indefinidamente

if __name__ == "__main__":
    asyncio.run(main())