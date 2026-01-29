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
APP_AUDIO_ROOT = os.environ.get("APP_AUDIO_ROOT", "/backend/app/audio_dumps")
CSV_PATH = os.path.join(APP_AUDIO_ROOT, "monitoramento_server.csv")

# Global Cache for high-frequency access (read by websocket.py)
SYSTEM_METRICS = {
    "cpu": 0.0,
    "ram": 0.0,
    "conns": 0
}

async def start_monitor_task(app):
    if psutil is None:
         print("[MONITOR] psutil missing. Task cancelled.")
         return
    """
    Background task that:
    1. Updates SYSTEM_METRICS every 2 seconds (fast).
    2. Logs to CSV every 5 minutes (slow).
    """
    print(f"[MONITOR] Iniciando monitoramento de sistema. Log: {CSV_PATH}")
    
    # Ensure dir exists
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    
    # Header if file is new
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "cpu_percent", "ram_mb", "connections_tcp", "status"])

    last_csv_write = 0
    CSV_INTERVAL = 300 # 5 minutes

    while True:
        try:
            # 1. Update Global Cache (Fast)
            # interval=0.1 avoids blocking for too long, but gives a sample
            cpu = psutil.cpu_percent(interval=None) 
            process = psutil.Process()
            ram_mb = process.memory_info().rss / (1024 * 1024)
            conns = len(process.connections()) # This can still be heavy, be careful
            
            SYSTEM_METRICS["cpu"] = cpu
            SYSTEM_METRICS["ram"] = ram_mb
            SYSTEM_METRICS["conns"] = conns
            
            # 2. Write to CSV (Slow)
            now_ts = asyncio.get_event_loop().time()
            if now_ts - last_csv_write > CSV_INTERVAL:
                ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(CSV_PATH, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([ts_str, f"{cpu:.1f}", f"{ram_mb:.1f}", conns, "OK"])
                
                last_csv_write = now_ts
                # print(f"[MONITOR] CSV Updated. CPU: {cpu}% RAM: {ram_mb:.1f}MB")

            # Update cache every 2 seconds
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"[MONITOR] Erro: {e}")
            await asyncio.sleep(10) # Wait bit longer on error
