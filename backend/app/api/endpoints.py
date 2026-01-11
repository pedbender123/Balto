import json
import base64
import asyncio
import io
import os
import pandas as pd
from datetime import datetime
from aiohttp import web
from app import db, transcription, audio_processor, vad, speaker_id
from app.core import config, audio_utils, ai_client

# --- Test Endpoints ---

async def api_test_segmentar(request):
    """Simula o streaming WebSocket via HTTP."""
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != 'audio':
            return web.json_response({"error": "Campo 'audio' obrigatório"}, status=400)
        
        filename = field.filename or "audio_upload.wav"
        audio_bytes = await field.read()
        
        pcm_bytes = audio_utils.decode_webm_to_pcm16le(audio_bytes)
        if not pcm_bytes:
            return web.json_response({"error": "Falha na decodificação de áudio"}, status=400)
            
        vad_session = vad.VAD()
        cleaner = audio_processor.AudioCleaner()
        
        print(f"[TEST] Limpando áudio completo ({len(pcm_bytes)} bytes)...")
        cleaned_pcm_full = cleaner.process(pcm_bytes)
        print("[TEST] Limpeza concluída.")
        
        segments_found = []
        CHUNK_SIZE = 960 
        total_len = len(cleaned_pcm_full)
        offset = 0
        
        while offset < total_len:
            end = min(offset + CHUNK_SIZE, total_len)
            chunk = cleaned_pcm_full[offset:end]
            offset = end
            
            speech = vad_session.process(chunk)
            
            if speech:
                b64_seg = base64.b64encode(speech).decode('utf-8')
                segments_found.append({
                    "size_bytes": len(speech),
                    "duration_sec": len(speech) / 32000.0,
                    "audio_base64": b64_seg
                })
        
        return web.json_response({"segments": segments_found, "total_segments": len(segments_found)})
        
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_test_transcrever(request):
    try:
        reader = await request.multipart()
        data = {}
        while True:
            field = await reader.next()
            if field is None: break
            if field.name == 'audio':
                data['audio'] = await field.read()
            elif field.name == 'provider':
                data['provider'] = await field.read(decode=True)
                data['provider'] = data['provider'].decode('utf-8')
        
        if 'audio' not in data:
            return web.json_response({"error": "Audio required"}, status=400)
            
        provider = data.get('provider', 'elevenlabs')
        audio_bytes = data['audio']
        
        text = ""
        # Assuming transcription module handles provider logic
        if provider == 'assemblyai':
            text = transcription.transcrever_assemblyai(audio_bytes)
        elif provider == 'deepgram':
            text = transcription.transcrever_deepgram(audio_bytes)
        elif provider == 'gladia':
            text = transcription.transcrever_gladia(audio_bytes)
        else:
            text = transcription.transcrever_elevenlabs(audio_bytes)
            
        return web.json_response({"texto": text})
        
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_test_analisar(request):
    try:
        data = await request.json()
        texto = data.get("texto")
        if not texto: return web.json_response({"error": "Texto empty"}, status=400)
        
        res_json_str = ai_client.ai_client.analisar_texto(texto)
        
        if res_json_str:
            try:
                res = json.loads(res_json_str)
            except:
                res = {"raw": res_json_str}
            return web.json_response(res)
        else:
            return web.json_response({"error": "No analysis result"}, status=500)
            
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- Admin & Business Endpoints ---

async def admin_page(request):
    return web.FileResponse('./app/static/admin.html')

async def admin_login(request):
    try:
        data = await request.json()
        if data.get("password") == config.ADMIN_SECRET:
            resp = web.Response(text="OK")
            resp.set_cookie("admin_token", "auth_ok", max_age=3600)
            return resp
        return web.Response(status=401)
    except:
        return web.Response(status=400)

async def api_export_xlsx(request):
    try:
        if request.cookies.get("admin_token") != "auth_ok":
            return web.Response(status=403, text="Forbidden")

        conn = db.get_db_connection()
        query = """
        SELECT 
            i.id,
            i.timestamp,
            b.nome_balcao,
            f.nome as funcionario,
            i.transcricao_completa,
            i.recomendacao_gerada,
            i.resultado_feedback,
            i.modelo_stt,
            i.custo_estimado
        FROM interacoes i
        LEFT JOIN balcoes b ON i.balcao_id = b.balcao_id
        LEFT JOIN funcionarios f ON i.funcionario_id = f.id
        ORDER BY i.timestamp DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%d/%m/%Y %H:%M:%S')
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Interacoes')
            worksheet = writer.sheets['Interacoes']
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 50)
        
        output.seek(0)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"relatorio_balto_{timestamp_str}.xlsx"
        
        return web.Response(
            body=output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        print(f"Erro Export Excel: {e}")
        return web.Response(status=500, text=str(e))

async def api_data_interacoes(request):
    try:
        if request.cookies.get("admin_token") != "auth_ok":
            return web.Response(status=403, text="Forbidden")
        rows = db.listar_interacoes(limit=50)
        return web.json_response(rows)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_cadastro_cliente(request):
    try:
        data = await request.json()
        email = data.get("email")
        razao = data.get("razao_social")
        tel = data.get("telefone")
        
        if not email or not razao:
             return web.json_response({"error": "Campos email e razao_social origatorios"}, status=400)
             
        try:
            codigo = db.create_client(email, razao, tel)
            return web.json_response({"codigo": codigo}, status=201)
        except Exception as e:
             return web.json_response({"error": f"Erro ao criar cliente: {str(e)}"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def api_cadastro_balcao(request):
    try:
        data = await request.json()
        nome_balcao = data.get("nome_balcao")
        user_codigo = data.get("user_codigo")
        
        if not nome_balcao or not user_codigo:
            return web.json_response({"error": "Campos nome_balcao e user_codigo obrigatorios"}, status=400)
            
        user_id = db.get_user_by_code(user_codigo)
        if user_id:
            balcao_id, api_key = db.create_balcao(user_id, nome_balcao)
            return web.json_response({
                "api_key": api_key,
                "balcao_id": balcao_id,
                "status": "registered"
            })
        else:
            return web.json_response({"error": "Codigo invalido ou expirado"}, status=404)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_cadastro_voz(request):
    """
    POST multipart/form-data:
      - user_codigo (text)   # codigo de 6 dígitos do cliente
      - balconista_id (text) # nome do funcionário (ex: "joao")
      - audio (file)
    """
    try:
        reader = await request.multipart()

        user_codigo = None
        balconista_id = None
        audio_bytes = None

        async for part in reader:
            if part.name == "user_codigo":
                user_codigo = (await part.text()).strip().strip('"')
            elif part.name == "balconista_id":
                balconista_id = (await part.text()).strip().strip('"')
            elif part.name == "audio":
                audio_bytes = await part.read()

        if not user_codigo:
            return web.json_response({"success": False, "error": "Campo 'user_codigo' é obrigatório."}, status=400)

        if not balconista_id:
            return web.json_response({"success": False, "error": "Campo 'balconista_id' é obrigatório."}, status=400)

        if not audio_bytes:
            return web.json_response({"success": False, "error": "Arquivo de áudio ('audio') é obrigatório."}, status=400)

        user_id = db.get_user_by_code(user_codigo)
        if not user_id:
            return web.json_response({"success": False, "error": "user_codigo inválido."}, status=404)

        pcm16 = audio_utils.decode_webm_to_pcm16le(audio_bytes)
        if not pcm16:
            return web.json_response({"success": False, "error": "Falha ao decodificar o áudio para PCM16."}, status=400)

        # agora salva WAV + embedding no Postgres (funcionarios)
        filepath, funcionario_db_id, audio_file_name = speaker_id.cadastrar_voz_funcionario(
            user_id=user_id,
            nome=balconista_id,
            audio_pcm16=pcm16,
            sample_rate=16000,
        )

        return web.json_response(
            {
                "success": True,
                "user_id": user_id,
                "balconista_id": balconista_id,
                "funcionario_id": funcionario_db_id,
                "arquivo_salvo": filepath,
                "audio_file_name": audio_file_name,
            },
            status=201,
        )

    except Exception as e:
        print(f"[CADASTRO_VOZ] Erro: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


    except Exception as e:
        print(f"[CADASTRO_VOZ] Erro: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)
