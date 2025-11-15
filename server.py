import asyncio
import json
import os
import uuid
from dotenv import load_dotenv

# --- NOVOS IMPORTS (AIOHTTP) ---
# Substitui a biblioteca 'websockets'
from aiohttp import web, WSMsgType

# --- Módulos Locais (Sem Mudança) ---
import db
import vad
import transcription
import analysis

# Carrega variáveis de ambiente
load_dotenv()

# Armazenamento temporário para interações pendentes de feedback
# (Sem Mudança)
pending_interactions = {}

# --- Lógica da Pipeline de IA (Quase Idêntica) ---
async def process_speech_pipeline(websocket, speech_segment: bytes, balcao_id: str):
    """
    Executa a pipeline de IA (Transcrição -> Análise).
    'websocket' agora é um objeto WebSocketResponse do aiohttp.
    """
    print(f"[{balcao_id}] Processando segmento de fala ({len(speech_segment)} bytes)...")
    
    try:
        # 1. Transcrição (Sem Mudança)
        texto_transcrito = await asyncio.to_thread(
            transcription.transcrever, 
            speech_segment
        )
        print(f"[{balcao_id}] Transcrição: {texto_transcrito}")

        if not texto_transcrito or texto_transcrito.startswith("[Erro"):
            return

        # 2. Análise (Sem Mudança)
        recomendacao = await asyncio.to_thread(
            analysis.analisar_texto, 
            texto_transcrito
        )

        # 3. Envio da Recomendação (Sintaxe do AIOHTTP)
        if recomendacao:
            id_interacao = str(uuid.uuid4())
            
            pending_interactions[id_interacao] = (texto_transcrito, recomendacao, balcao_id)
            
            payload = {
                "comando": "recomendar",
                "mensagem": recomendacao,
                "id_interacao": id_interacao
            }
            
            # --- MUDANÇA ---
            # websocket.send(json.dumps(payload)) -> await websocket.send_json(payload)
            await websocket.send_json(payload) 
            
            print(f"[{balcao_id}] Recomendação enviada: {recomendacao}")
            
    except Exception as e:
        print(f"[{balcao_id}] Erro na pipeline de IA: {e}")

# --- NOVOS Handlers HTTP (Rotas) ---

async def http_cadastro_cliente(request):
    """Lida com POST /cadastro/cliente"""
    try:
        data = await request.json()
        email = data.get("email")
        razao_social = data.get("razao_social")
        telefone = data.get("telefone")

        if not email or not razao_social:
            return web.json_response({"error": "Email e razão social são obrigatórios"}, status=400)
            
        result = await asyncio.to_thread(db.add_user, email, razao_social, telefone)
        
        if result["success"]:
            return web.json_response({"codigo": result["codigo"]}, status=201) # 201 Created
        else:
            return web.json_response({"error": result["error"]}, status=409) # 409 Conflict

    except json.JSONDecodeError:
        return web.json_response({"error": "JSON inválido"}, status=400)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def http_cadastro_balcao(request):
    """Lida com POST /cadastro/balcao"""
    try:
        data = await request.json()
        nome_balcao = data.get("nome_balcao")
        user_codigo = data.get("user_codigo")

        if not nome_balcao or not user_codigo:
            return web.json_response({"error": "Nome do balcão e código do usuário são obrigatórios"}, status=400)
            
        result = await asyncio.to_thread(db.add_balcao, nome_balcao, user_codigo)
        
        if result["success"]:
            return web.json_response({"api_key": result["api_key"]}, status=201)
        else:
            return web.json_response({"error": result["error"]}, status=400)

    except json.JSONDecodeError:
        return web.json_response({"error": "JSON inválido"}, status=400)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- NOVO Handler WebSocket ---

async def websocket_handler(request):
    """Lida com conexões GET /ws"""
    
    # Prepara a conexão WebSocket
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    balcao_id = None
    remote_addr = request.remote

    try:
        # --- 1. AUTENTICAÇÃO ---
        try:
            # Espera a 1a msg (autenticação) por 5 segundos
            # O cliente DEVE enviar: {"comando": "auth", "api_key": "..."}
            auth_message = await asyncio.wait_for(ws.receive(), timeout=5.0)
            
            if auth_message.type == WSMsgType.TEXT:
                auth_data = json.loads(auth_message.data)
                
                if auth_data.get("comando") == "auth":
                    api_key = auth_data.get("api_key")
                    if api_key:
                        balcao_id = await asyncio.to_thread(db.validate_api_key, api_key)
            
            if not balcao_id:
                await ws.close(code=1008, message=b"Autenticacao invalida")
                print(f"[{remote_addr}] Falha na autenticação")
                return ws

        except asyncio.TimeoutError:
            await ws.close(code=1008, message=b"Timeout na autenticacao")
            print(f"[{remote_addr}] Falha na autenticação (timeout)")
            return ws
        except (json.JSONDecodeError, TypeError):
            await ws.close(code=1008, message=b"Mensagem de autenticacao invalida")
            print(f"[{remote_addr}] Falha na autenticação (JSON invalido)")
            return ws

        # --- 2. AUTENTICADO ---
        print(f"Cliente autenticado: {balcao_id} (IP: {remote_addr})")
        client_vad = vad.VAD()

        # Loop principal: escuta por mensagens (áudio ou feedback)
        async for msg in ws:
            
            if msg.type == WSMsgType.BINARY:
                speech_segment = client_vad.process(msg.data)
                if speech_segment:
                    asyncio.create_task(
                        process_speech_pipeline(ws, speech_segment, balcao_id)
                    )

            elif msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("comando") == "feedback":
                        id_interacao = data.get("id_interacao")
                        resultado = data.get("resultado")
                        
                        if id_interacao in pending_interactions:
                            transcricao, recomendacao, int_balcao_id = pending_interactions.pop(id_interacao)
                            
                            if int_balcao_id != balcao_id:
                                print(f"[{balcao_id}] Recebeu feedback de ID de outro balcão. Ignorando.")
                                pending_interactions[id_interacao] = (transcricao, recomendacao, int_balcao_id)
                                continue

                            await asyncio.to_thread(
                                db.registrar_interacao, 
                                balcao_id, transcricao, recomendacao, resultado
                            )
                            print(f"[{balcao_id}] Feedback recebido e salvo: {id_interacao} -> {resultado}")
                        else:
                            print(f"[{balcao_id}] Feedback recebido para ID desconhecido: {id_interacao}")
                
                except json.JSONDecodeError:
                    print(f"[{balcao_id}] Recebida mensagem de texto inválida (não-JSON).")

            elif msg.type == WSMsgType.ERROR:
                print(f"Erro no WebSocket do cliente {balcao_id}: {ws.exception()}")

    except Exception as e:
        print(f"Erro inesperado com cliente {balcao_id}: {e}")
    finally:
        print(f"Conexão com {balcao_id or 'cliente desconhecido'} fechada.")

    return ws

# --- NOVO Ponto de Entrada (main) ---

async def main():
    # Inicializa o banco de dados
    db.inicializar_db()
    
    # Cria a aplicação AIOHTTP
    app = web.Application()
    
    # Registra as rotas
    app.router.add_post("/cadastro/cliente", http_cadastro_cliente)
    app.router.add_post("/cadastro/balcao", http_cadastro_balcao)
    app.router.add_get("/ws", websocket_handler) # WebSocket é sempre GET
    
    # Configura e roda a aplicação
    port = int(os.environ.get("PORT", 8765))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    print(f"Servidor AIOHTTP (HTTP e WebSocket) iniciado na porta {port}...")
    await asyncio.Event().wait() # Roda indefinidamente

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Servidor desligado.")