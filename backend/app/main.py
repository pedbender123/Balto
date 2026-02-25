
import os
from aiohttp import web
from app import db, diagnostics, transcription, speaker_id, silero_vad
from app.core import config, audio_analysis
from app.api import websocket, endpoints
from app.core import system_monitor, audio_archiver, drive_sync

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
    
    # Startup Events
    async def on_startup(app):
        print("--- Starting System Monitor ---")
        asyncio.create_task(system_monitor.start_monitor_task(app))
        
        # Init Models (Prevent Latency on First Request)
        print("--- Pre-loading Models ---")
        await asyncio.to_thread(speaker_id.initialize_model)
        
        # Init SileroVAD (IA layer)
        try:
            from app import silero_vad
            app['silero_vad'] = await asyncio.to_thread(silero_vad.SileroVAD)
            print("--- SileroVAD Loaded ---")
        except Exception as e:
            print(f"[WARN] Failed to load SileroVAD: {e}")
            app['silero_vad'] = None

        await asyncio.to_thread(audio_analysis.warmup)
        # Start Parallel Audio Archiver
        audio_archiver.archiver.start()
        
        # Start Drive Sync Loop if enabled
        if config.DRIVE_SYNC_ENABLED:
            asyncio.create_task(drive_sync.drive_sync_loop())
            
        print("--- Models Ready ---")
        
    app.on_startup.append(on_startup)
    
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
    app.router.add_get('/api/data/balcao/{balcao_id}/metricas', endpoints.api_interacoes_balcao_metricas)

    # Admin VAD Management
    app.router.add_get('/api/admin/client/{user_codigo}/balcoes', endpoints.api_admin_listar_balcoes)
    app.router.add_put('/api/admin/balcao/{balcao_id}/vad', endpoints.api_admin_update_balcao_vad)

    print("---------------------------------------")
    print(f"Balto Server 3.0 (Modular) Running on port {config.PORT}")
    print(f"MOCK_MODE: {config.MOCK_MODE}")
    print(f"SAVE_AUDIO_DUMPS: {config.SAVE_AUDIO}")
    print(f"SMART_ROUTING_ENABLE: {config.SMART_ROUTING_ENABLE}")
    if config.SMART_ROUTING_ENABLE:
        print(f" -> SNR_THRESHOLD: {transcription.SMART_ROUTING_SNR_THRESHOLD} dB")
        print(f" -> MIN_DURATION: {transcription.SMART_ROUTING_MIN_DURATION} s")
    print(f"OPENAI_ENABLED: {bool(config.OPENAI_API_KEY)}")
    print(f"VAD_MIN_ENERGY: {os.environ.get('VAD_MIN_ENERGY_THRESHOLD', '50.0')}")
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
