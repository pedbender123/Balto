# Balto - Assistente de Farmácia (Servidor)

`Balto` é um assistente de IA em tempo real para farmácias. Ele escuta ativamente as interações no balcão, processa o áudio e sugere produtos relevantes (fármacos e não-fármacos) para o balconista, aumentando as oportunidades de venda cruzada.

Este repositório contém o serviço de **`server` (Backend)**, que é o "cérebro" do sistema.

## 🚀 Visão Geral da Arquitetura

O sistema funciona com uma pipeline de áudio contínua via WebSockets (`wss://`):

1.  Um cliente (aplicativo de balcão, não incluído neste repo) captura o áudio do microfone e o envia como um fluxo de *bytes*.
2.  O **Servidor Balto** recebe o fluxo de áudio.
3.  O áudio passa por um **VAD** (`webrtcvad`) que detecta atividade de fala e "corta" o áudio em segmentos.
4.  Cada segmento de fala é enviado para a API da **ElevenLabs** para transcrição (Speech-to-Text).
5.  O texto transcrito é enviado para o **Grok 3-mini** (x.ai) para análise de intenção.
6.  O Grok compara os sintomas mencionados com a base de dados `produtos.json` e decide se uma recomendação é aplicável.
7.  Se aplicável, o servidor envia um comando JSON de volta ao cliente, que exibe um pop-up de sugestão.

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python 3.10 (com `asyncio`)
* **Servidor:** `websockets`
* **Deploy:** Docker & Docker Compose
* **IA - Análise (LLM):** Grok 3-mini (via API x.ai)
* **IA - Transcrição (STT):** ElevenLabs
* **IA - Detecção de Voz (VAD):** `webrtcvad-wheels`
* **Banco de Dados:** `sqlite3` (para log de interações)

## ⚙️ Instalação e Deploy (VPS)

O servidor é projetado para rodar como um contêiner Docker em uma VPS.

### 1. Pré-requisitos

* Um servidor (VPS) com **Docker** e **Docker Compose** instalados.
* Um proxy reverso (como **Nginx**) configurado com **SSL** (Certbot) para permitir WebSockets seguros (`wss://`).

### 2. Clonar o Repositório

```bash
# Na sua VPS
git clone [https://github.com/pedbender123/Balto.git](https://github.com/pedbender123/Balto.git)
cd Balto