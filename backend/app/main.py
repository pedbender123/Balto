
import os
from aiohttp import web
from app import db, diagnostics, transcription
from app.core import config
from app.api import websocket, endpoints

@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        resp = web.Response()
    else:
        resp = await handler(request)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp

def main():
    try:
        db.inicializar_db()
    except Exception as e:
        print(f"[WARN] Failed to initialize DB: {e}")
        print("[WARN] Server starting in DEGRADED mode (No DB Connection)")
    
    app = web.Application(middlewares=[cors_middleware])
    
    # WebSocket
    app.router.add_get('/ws', websocket.websocket_handler)
    
    # Admin Pages
    app.router.add_get('/admin', endpoints.admin_page)
    
    # API Routes
    app.router.add_post('/admin/login', endpoints.admin_login)
    app.router.add_post('/cadastro/cliente', endpoints.api_cadastro_cliente)
    app.router.add_post('/cadastro/balcao', endpoints.api_cadastro_balcao)
    app.router.add_post('/cadastro/voz', endpoints.api_cadastro_voz)
    
    # Test Routes
    app.router.add_post('/api/test/segmentar', endpoints.api_test_segmentar)
    app.router.add_post('/api/test/transcrever', endpoints.api_test_transcrever)
    app.router.add_post('/api/test/analisar', endpoints.api_test_analisar)

    # Export Routes
    app.router.add_get('/api/export/xlsx', endpoints.api_export_xlsx)
    app.router.add_get('/api/data/interacoes', endpoints.api_data_interacoes)

    print("---------------------------------------")
    print(f"Balto Server 3.0 (Modular) Running on port {config.PORT}")
    print(f"MOCK_MODE: {config.MOCK_MODE}")
    print(f"SAVE_AUDIO_DUMPS: {config.SAVE_AUDIO}")
    print(f"SMART_ROUTING_ENABLE: {config.SMART_ROUTING_ENABLE}")
    if config.SMART_ROUTING_ENABLE:
        print(f" -> SNR_THRESHOLD: {transcription.SMART_ROUTING_SNR_THRESHOLD} dB")
        print(f" -> MIN_DURATION: {transcription.SMART_ROUTING_MIN_DURATION} s")
    print(f"OPENAI_ENABLED: {bool(config.OPENAI_API_KEY)}")
    print("---------------------------------------")
    
    # Diagnostics
    diagnostics.run_all_checks()
    
    # Schedule Integration Test (Background Task)
    import asyncio
    from app import integration_test
    
    async def run_test_bg(app):
         asyncio.create_task(integration_test.start_startup_test())

    app.on_startup.append(run_test_bg)

    web.run_app(app, port=config.PORT)

if __name__ == "__main__":
    main()
