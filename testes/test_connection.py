#!/usr/bin/env python3
"""
Script de teste rápido para verificar conexão com o servidor Debug WebSocket.
"""
import asyncio
import websockets
import json

WS_URL = "ws://localhost:8765/ws/debug_audio"
ADMIN_SECRET = "x9PeHTY7ouQNvzJH"

async def test_connection():
    print(f"🔗 Tentando conectar a: {WS_URL}")
    try:
        extra_headers = {"X-Adm-Key": ADMIN_SECRET}
        
        async with websockets.connect(
            WS_URL + f"?key={ADMIN_SECRET}", 
            extra_headers=extra_headers,
            ping_interval=30,
            ping_timeout=60
        ) as ws:
            print("✅ Conectado com sucesso!")
            print("📡 Aguardando eventos do servidor...")
            
            # Aguarda alguns segundos para ver se recebe algum evento
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                print(f"📥 Evento recebido: {data}")
            except asyncio.TimeoutError:
                print("⏱️  Nenhum evento recebido (normal se não houver áudio)")
            
            print("✅ Teste concluído!")
            
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
