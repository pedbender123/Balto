#!/bin/bash
set -e

# Garante que roda na pasta do script
cd "$(dirname "$0")"

echo "--- [STRESS TEST] MODO LOCAL (HOST) ---"
echo "Alvo: ws://localhost:8765/ws"

# 0. Verifica e Instala Python/Venv se necessário
if ! command -v python3 &> /dev/null; then
    echo "[!] Python3 não encontrado. Tentando instalar..."
    if [ -x "$(command -v apt-get)" ]; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    else
        echo "[Err] Gerenciador de pacotes não suportado. Instale python3 manualmente."
        exit 1
    fi
fi

# Verifica se o ensurepip está disponível (venv quebrado no Debian/Ubuntu)
if ! python3 -c "import ensurepip" &> /dev/null; then
    echo "[!] 'ensurepip' não encontrado. O venv provavelmente está quebrado."
    echo "[!] Tentando instalar python3-venv genérico..."
    if [ -x "$(command -v apt-get)" ]; then
         # Tenta instalar o genérico, que geralmente puxa a versão certa
         sudo apt-get update && sudo apt-get install -y python3-venv
    else
         echo "[Err] Instale o pacote python3-venv (ou python3.X-venv) manualmente."
         exit 1
    fi
fi

# 1. Configura Python Virtual Env
if [ ! -d "stress_venv" ]; then
    echo "[!] Criando ambiente virtual (stress_venv)..."
    python3 -m venv stress_venv
fi

source stress_venv/bin/activate

# 2. Instala Dependências (Sempre tenta atualizar para garantir)
echo "[!] Verificando dependências..."
pip install -q -r requirements-stress.txt


# 3. Executa o Orquestrador
# Forçamos a variável aqui para garantir que pegue localhost
export STRESS_TARGET_URL="ws://localhost:8765/ws"
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"

echo "[!] Iniciando Ataque..."
python3 stress_test/orchestrator.py
