import asyncio
import websockets
import json
import os
import uuid
from dotenv import load_dotenv

# Importa os módulos de HTTP da lib websockets
from websockets.http import HTTPStatus
from websockets.server import Serve # Para type hint

# Importa os módulos locais
import db
import vad
import transcription
import analysis

# Carrega variáveis de ambiente (OPENAI_API_KEY, DB_FILE, etc)
load_dotenv()

# Armazenamento temporário para interações pendentes de feedback
# Chave: id_interacao, Valor: (transcricao, recomendacao, balcao_id)
pending_interactions = {}

async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str):
    """
    Executa a pipeline de IA (Transcrição -> Análise).
    Usa balcao_id para logging e registro no DB.
    """
    print(f"[{balcao_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")
    
    try:
        # 1. Transcrição
        texto_transcrito = await asyncio.to_thread(
            transcription.transcrever, 
            speech_segment
        )
        print(f"[{balcao_id}] Transcrição: {texto_transcrito}")

        if not texto_transcrito or texto_transcrito.startswith("[Erro"):
            return

        # 2. Análise
        recomendacao = await asyncio.to_thread(
            analysis.analisar_texto, 
            texto_transcrito
        )

        # 3. Envio da Recomendação
        if recomendacao:
            id_interacao = str(uuid.uuid4())
            
            # Armazena para o feedback futuro, incluindo o balcao_id
            pending_interactions[id_interacao] = (texto_transcrito, recomendacao, balcao_id)
            
            payload = {
                "comando": "recomendar",
                "mensagem": recomendacao,
                "id_interacao": id_interacao
            }
            
            await websocket.send(json.dumps(payload))
            print(f"[{balcao_id}] Recomendação enviada: {recomendacao}")
            
    except Exception as e:
        print(f"[{balcao_id}] Erro na pipeline de IA: {e}")


async def http_handler(path, request_headers):
    """
    Lida com requisições HTTP que NÃO são WebSockets.
    Usado para as rotas de cadastro /cadastro/*
    """
    headers = [("Content-Type", "application/json")]
    
    # --- 1. Rotas de Cadastro (HTTP POST) ---
    if path in ["/cadastro/cliente", "/cadastro/balcao"]:
        if request_headers["Method"] != "POST":
            return (
                HTTPStatus.METHOD_NOT_ALLOWED,
                headers,
                json.dumps({"error": "Método POST requerido"}).encode("utf-8")
            )
            
        try:
            # Lê o body da requisição
            content_length = int(request_headers["Content-Length"])
            body_bytes = await request_headers.raw_request_line.read(content_length)
            data = json.loads(body_bytes)
        except (KeyError, ValueError, json.JSONDecodeError):
            return (HTTPStatus.BAD_REQUEST, headers, json.dumps({"error": "JSON inválido ou 'Content-Length' ausente"}).encode("utf-8"))

        # --- Rota /cadastro/cliente ---
        if path == "/cadastro/cliente":
            email = data.get("email")
            razao_social = data.get("razao_social")
            telefone = data.get("telefone")
            
            if not email or not razao_social:
                return (HTTPStatus.BAD_REQUEST, headers, json.dumps({"error": "Email e razão social são obrigatórios"}).encode("utf-8"))
                
            # Chama a função do DB (em outra thread para não bloquear)
            result = await asyncio.to_thread(db.add_user, email, razao_social, telefone)
            
            if result["success"]:
                return (HTTPStatus.CREATED, headers, json.dumps({"codigo": result["codigo"]}).encode("utf-8"))
            else:
                return (HTTPStatus.CONFLICT, headers, json.dumps({"error": result["error"]}).encode("utf-8"))

        # --- Rota /cadastro/balcao ---
        elif path == "/cadastro/balcao":
            nome_balcao = data.get("nome_balcao")
            user_codigo = data.get("user_codigo")
            
            if not nome_balcao or not user_codigo:
                return (HTTPStatus.BAD_REQUEST, headers, json.dumps({"error": "Nome do balcão e código do usuário são obrigatórios"}).encode("utf-8"))
                
            # Chama a função do DB (em outra thread)
            result = await asyncio.to_thread(db.add_balcao, nome_balcao, user_codigo)
            
            if result["success"]:
                return (HTTPStatus.CREATED, headers, json.dumps({"api_key": result["api_key"]}).encode("utf-8"))
            else:
                return (HTTPStatus.BAD_REQUEST, headers, json.dumps({"error": result["error"]}).encode("utf-8"))
    
    # --- 2. Rota WebSocket (deve ser /ws) ---
    if path == "/ws":
        # A requisição é para o WebSocket.
        # Retorna None para permitir o upgrade.
        # A autenticação será feita dentro do 'handle_client'.
        return None

    # --- 3. Outras rotas (Não encontradas) ---
    return (
        HTTPStatus.NOT_FOUND,
        [("Content-Type", "application/json")],
        json.dumps({"error": "Rota não encontrada. Use POST /cadastro/cliente, POST /cadastro/balcao ou conecte-se a /ws"}).encode("utf-8")
    )

async def handle_client(websocket, path):
    """
    Gerencia a conexão de um único cliente (balcão).
    AGORA INCLUI AUTENTICAÇÃO na primeira mensagem.
    'path' é o path da requisição (ex: /ws)
    """
    
    # Confirma se a conexão é no path /ws (embora o http_handler já filtre)
    if path != "/ws":
        await websocket.close(1008, "Path invalido. Conecte-se a /ws")
        return

    # --- 1. AUTENTICAÇÃO ---
    balcao_id = None
    try:
        # Espera a 1a msg (autenticação) por 5 segundos
        # O cliente DEVE enviar: {"comando": "auth", "api_key": "..."}
        auth_message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        auth_data = json.loads(auth_message)
        
        if auth_data.get("comando") == "auth":
            api_key = auth_data.get("api_key")
            if api_key:
                # Valida a API key (operação de DB, usar to_thread)
                balcao_id = await asyncio.to_thread(db.validate_api_key, api_key)
        
        if not balcao_id:
            # Se balcao_id ainda é None, a autenticação falhou
            await websocket.close(1008, "Autenticacao invalida")
            print(f"[{websocket.remote_address}] Falha na autenticação (key inválida ou não fornecida)")
            return
            
    except asyncio.TimeoutError:
        await websocket.close(1008, "Timeout na autenticacao")
        print(f"[{websocket.remote_address}] Falha na autenticação (timeout)")
        return
    except (json.JSONDecodeError, TypeError):
        await websocket.close(1008, "Mensagem de autenticacao invalida")
        print(f"[{websocket.remote_address}] Falha na autenticação (JSON invalido)")
        return
    except Exception as e:
        await websocket.close(1011, f"Erro interno na autenticacao: {e}")
        print(f"[{websocket.remote_address}] Erro na autenticação: {e}")
        return

    # --- 2. AUTENTICADO ---
    print(f"Cliente autenticado: {balcao_id} (IP: {websocket.remote_address})")
    client_vad = vad.VAD() # Cria uma instância VAD "stateful" para este cliente

    try:
        # Loop principal: escuta por mensagens (áudio ou feedback)
        async for message in websocket:
            
            if isinstance(message, bytes):
                # Mensagem é ÁUDIO
                speech_segment = client_vad.process(message)
                
                if speech_segment:
                    # Inicia a pipeline de IA sem bloquear o loop
                    asyncio.create_task(
                        process_speech_pipeline(websocket, speech_segment, balcao_id)
                    )

            elif isinstance(message, str):
                # Mensagem é TEXTO (JSON de Feedback)
                try:
                    data = json.loads(message)
                    
                    if data.get("comando") == "feedback":
                        id_interacao = data.get("id_interacao")
                        resultado = data.get("resultado")
                        
                        if id_interacao in pending_interactions:
                            # Recupera os dados da interação
                            transcricao, recomendacao, int_balcao_id = pending_interactions.pop(id_interacao)
                            
                            # Garante que o feedback veio do balcão certo (segurança extra)
                            if int_balcao_id != balcao_id:
                                print(f"[{balcao_id}] Recebeu feedback de ID de outro balcão. Ignorando.")
                                # Readiciona na lista
                                pending_interactions[id_interacao] = (transcricao, recomendacao, int_balcao_id)
                                continue

                            # Registrar no DB (usar to_thread para operação de I/O)
                            await asyncio.to_thread(
                                db.registrar_interacao, 
                                balcao_id, transcricao, recomendacao, resultado
                            )
                            print(f"[{balcao_id}] Feedback recebido e salvo: {id_interacao} -> {resultado}")
                        else:
                            print(f"[{balcao_id}] Feedback recebido para ID desconhecido: {id_interacao}")
                            
                except json.JSONDecodeError:
                    print(f"[{balcao_id}] Recebida mensagem de texto inválida (não-JSON).")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Cliente desconectado: {balcao_id} (Motivo: {e.code} {e.reason})")
    except Exception as e:
        print(f"Erro inesperado com cliente {balcao_id}: {e}")
    finally:
        print(f"Conexão com {balcao_id} fechada.")


async def main():
    # Inicializa o banco de dados ao iniciar
    db.inicializar_db()
    
    port = int(os.environ.get("PORT", 8765))
    print(f"Iniciando servidor WebSocket (em /ws) e HTTP (em /cadastro/*) na porta {port}...")
    
    # Inicia o servidor, definindo o 'http_handler' para
    # requisições que não são WebSocket.
    async with websockets.serve(
        handle_client,  # Handler para conexões WebSocket (em /ws)
        "0.0.0.0", 
        port,
        process_request=http_handler # Handler para requisições HTTP (ex: /cadastro/*)
    ):
        await asyncio.Future()  # Roda indefinidamente

if __name__ == "__main__":
    asyncio.run(main())