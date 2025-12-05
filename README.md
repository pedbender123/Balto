🤖 Balto Server Backend

Serviço de backend em Python (AIOHTTP + WebSockets) responsável pela pipeline de inteligência artificial do sistema Balto. O sistema processa áudio em tempo real, gerencia transações e fornece sugestões farmacêuticas baseadas em sintomas.

📋 Stack Tecnológica

Linguagem: Python 3.10

Server: AIOHTTP (Async)

VAD (Voice Activity Detection): WebRTCVAD + Energy Gate (Filtro de ruído e silêncio)

STT (Speech-to-Text): ElevenLabs (Scribe)

LLM (Inteligência): xAI (Grok Beta)

Infra: Docker & Docker Compose

⚙️ Estrutura do Projeto

O projeto foi reorganizado para maior escalabilidade:

/
├── backend/
│   ├── app/           # Código fonte da aplicação
│   ├── Dockerfile     # Definição da imagem
│   └── .env           # Variáveis (NÃO COMITAR)
├── docker-compose.yml # Orquestração dos containers
└── README.md


🚀 Como Rodar (Localmente ou Servidor)

IMPORTANTE: Não tente rodar comandos docker run manuais. O projeto utiliza volumes gerenciados e redes internas configuradas no docker-compose.

1. Configuração de Ambiente (.env)

Crie um arquivo .env dentro da pasta backend/ com as seguintes chaves:

# Chaves de API (Obrigatórias)
XAI_API_KEY="sua-chave-grok-aqui"
ELEVENLABS_API_KEY="sua-chave-elevenlabs-aqui"

# Configurações do Sistema
PORT=8765
DB_FILE="/backend/app/dados/registro.db"

# Ajuste de Sensibilidade do VAD (Opcional, Padrão: 300)
# Aumente se houver muito ruído de fundo, diminua se a voz estiver cortando.
VAD_ENERGY_THRESHOLD=300


2. Execução

Na raiz do projeto (onde está o docker-compose.yml), execute:

docker-compose up --build -d


Este comando irá:

Construir a imagem baseada no Dockerfile correto.

Montar o volume balto-dados para que o banco de dados não seja perdido ao reiniciar.

Iniciar o servidor na porta 8765.

Para ver os logs:

docker-compose logs -f


📡 Protocolo de Comunicação (WebSocket)

Endpoint: ws://localhost:8765/ws (ou IP do servidor)

Fluxo de Dados

Autenticação (Cliente -> Servidor)

Assim que conectar, envie:

{ "comando": "auth", "api_key": "sua-api-key-do-balcao" }


Envio de Áudio (Cliente -> Servidor)

Envie chunks de áudio binário (16kHz, 16-bit, Mono) continuamente.

O sistema possui um Denoiser e VAD Integrados: Ele automaticamente descarta silêncio e ruído de fundo antes de processar, economizando custos de API.

Recomendação (Servidor -> Cliente)

Quando uma sugestão é identificada, o servidor envia:

{
  "comando": "recomendar",
  "produto": "Nome do Produto",
  "explicacao": "Breve motivo da sugestão baseado nos sintomas.",
  "transcricao_base": "Texto original transcrito para auditoria"
}


Nota: Se não houver produto relevante, o servidor não envia nada.

🛠️ Manutenção e Banco de Dados

O banco de dados SQLite é persistido no volume Docker balto-dados.
Para fazer backup ou acessar o arquivo .db diretamente, ele está mapeado internamente no container em /backend/app/dados/registro.db.