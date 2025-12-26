import asyncio
import aiohttp
import sys
import os
import json

# Config
SERVER_URL = "ws://localhost:8765/ws/debug_audio"
API_KEY = "admin123" # Default admin secret
AUDIO_FILE = "tests_audio/audios_brutos/audio_teste.wav" # Ajuste conforme necessário

async def run_client():
    print(f"Conectando a {SERVER_URL}...")
    
    # 1. Conexão com Autenticação
    # Opção A: Header
    headers = {"X-Adm-Key": API_KEY}
    # Opção B: Query Param
    url = f"{SERVER_URL}?key={API_KEY}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(url, headers=headers) as ws:
                print("Conectado! Enviando áudio...")
                
                # 2. Enviar Áudio (Simulando Stream)
                # Verifica se arquivo existe, senão pega um exemplo ou para
                if len(sys.argv) > 1:
                   filepath = sys.argv[1]
                else:
                   # Tenta achar um wav qualquer na pasta
                   files = [f for f in os.listdir("tests_audio/audios_brutos") if f.endswith(".wav")]
                   if files:
                       filepath = os.path.join("tests_audio/audios_brutos", files[0])
                   else:
                       print("Nenhum arquivo .wav encontrado para teste.")
                       return

                print(f"Enviando arquivo: {filepath}")
                
                # Task para receber mensagens enquanto enviamos
                async def receive_loop():
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            event = data.get("event")
                            print(f"\n[EVENTO] {event}")
                            print(json.dumps(data["data"], indent=2, ensure_ascii=False))
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print("Conexão fechada pelo servidor.")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print("Erro no Websocket")
                            break
                
                receiver = asyncio.create_task(receive_loop())
                
                # Envio (Stream)
                with open(filepath, "rb") as f:
                    chunk_size = 4096 # Simulando pacotes de rede
                    while True:
                        data = f.read(chunk_size)
                        if not data: break
                        await ws.send_bytes(data)
                        await asyncio.sleep(0.01) # Pequeno delay simular rede
                
                print("\nEnvio concluído. Aguardando processamento final...")
                await asyncio.sleep(5) # Espera respostas finais
                await ws.close()
                await receiver
                
        except Exception as e:
            print(f"Erro na conexão: {e}")

if __name__ == "__main__":
    if not os.path.exists("tests_audio/audios_brutos"):
         os.makedirs("tests_audio/audios_brutos")
         print("Criei pasta 'tests_audio/audios_brutos'. Coloque um .wav lá.")
    
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        pass
