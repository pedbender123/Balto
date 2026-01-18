import asyncio
import csv
import os
from datetime import datetime
try:
    import psutil
except ImportError:
    psutil = None
    print("[MONITOR] Warning: psutil not installed. Monitoring disabled.")

# Path to persistent storage
CSV_PATH = "/backend/app/dados/monitoramento_server.csv"

async def start_monitor_task(app):
    if psutil is None:
         print("[MONITOR] psutil missing. Task cancelled.")
         return
    """
    Background task that logs system metrics every 5 minutes (300s).
    """
    print(f"[MONITOR] Iniciando monitoramento de sistema. Log: {CSV_PATH}")
    
    # Ensure dir exists
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    
    # Header if file is new
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "cpu_percent", "ram_mb", "connections_tcp", "status"])

    while True:
        try:
            # Coletar Métricas
            cpu = psutil.cpu_percent(interval=1)
            process = psutil.Process()
            ram_mb = process.memory_info().rss / (1024 * 1024)
            
            # Count connections (approx)
            conns = len(process.connections())
            
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(CSV_PATH, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([ts, f"{cpu:.1f}", f"{ram_mb:.1f}", conns, "OK"])
                
            # print(f"[MONITOR] {ts} - CPU: {cpu}% RAM: {ram_mb:.1f}MB Conns: {conns}")
            
            # Wait 5 minutes
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"[MONITOR] Erro: {e}")
            await asyncio.sleep(60) # Wait 1 min on error before retry
