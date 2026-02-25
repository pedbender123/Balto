import os

def setup_rclone():
    print("--- Balto Rclone Setup Helper ---")
    print("Este script ajudará a configurar o rclone.conf no servidor.")
    print("Certifique-se de que você já tem o TOKEN gerado no seu notebook via 'rclone authorize \"drive\"'.\n")
    
    token = input("Cole o TOKEN (JSON longo) aqui: ").strip()
    
    if not token.startswith("{") or not token.endswith("}"):
        print("[ERRO] O token parece estar em formato inválido. Deve ser um JSON.")
        return

    rclone_config_content = f"""[balto_drive]
type = drive
scope = drive
token = {token}
team_drive = 
"""

    config_path = "rclone.conf"
    with open(config_path, "w") as f:
        f.write(rclone_config_content)
        
    print(f"\n[SUCESSO] Arquivo '{config_path}' gerado com sucesso!")
    print("Agora você pode rodar 'docker compose up -d' para iniciar o sistema com sync no Drive.")

if __name__ == "__main__":
    setup_rclone()
