# Balto Backend - Database Schema Documentation

This document describes all database tables and columns, including when and where each column is populated.

---

## Tables Overview

| Table           | Purpose                                         |
|-----------------|-------------------------------------------------|
| `users`         | Registered clients (companies) using Balto      |
| `balcoes`       | Individual counter/terminals per client         |
| `funcionarios`  | Employees with voice embeddings for Speaker ID  |
| `interacoes`    | All audio processing logs (valid and discarded) |

---

## Table: `users`

| Column             | Type         | Description                            | Source File         |
|--------------------|--------------|----------------------------------------|---------------------|
| `user_id`          | TEXT (PK)    | UUID of the client                     | `db.py` (create)    |
| `email`            | TEXT (UNIQUE)| Client email                           | `db.py` (create)    |
| `razao_social`     | TEXT         | Company name                           | `db.py` (create)    |
| `telefone`         | TEXT         | Phone number                           | `db.py` (create)    |
| `codigo_6_digitos` | TEXT (UNIQUE)| 6-digit login code                     | `db.py` (create)    |

---

## Table: `balcoes`

| Column         | Type         | Description                          | Source File        |
|----------------|--------------|--------------------------------------|--------------------|
| `balcao_id`    | TEXT (PK)    | UUID of the counter                  | `db.py` (create)   |
| `user_id`      | TEXT (FK)    | References `users.user_id`           | `db.py` (create)   |
| `nome_balcao`  | TEXT         | Human-readable counter name          | `db.py` (create)   |
| `api_key`      | TEXT (UNIQUE)| WebSocket authentication key         | `db.py` (create)   |

---

## Table: `funcionarios`

| Column            | Type        | Description                          | Source File         |
|-------------------|-------------|--------------------------------------|---------------------|
| `id`              | SERIAL (PK) | Auto-increment ID                    | `db.py`             |
| `user_id`         | TEXT (FK)   | References `users.user_id`           | `db.py`             |
| `nome`            | TEXT        | Employee name                        | `db.py`             |
| `audio_file_name` | TEXT        | Original audio file name             | `db.py`             |
| `embedding`       | BYTEA       | Voice embedding (numpy bytes)        | `speaker_id.py`     |
| `criado_em`       | TIMESTAMP   | Creation/update timestamp            | `db.py`             |

---

## Table: `interacoes`

This is the main telemetry table for audio analysis. **All audio segments are now logged**, including discarded ones.

### Core Columns

| Column                  | Type      | Description                                      | Source File             |
|-------------------------|-----------|--------------------------------------------------|-------------------------|
| `id`                    | SERIAL    | Auto-increment primary key                       | `db.py`                 |
| `balcao_id`             | TEXT (FK) | References `balcoes.balcao_id`                   | `websocket.py`          |
| `timestamp`             | TIMESTAMP | When the interaction was logged                  | `db.py` (now())         |
| `transcricao_completa`  | TEXT      | Full transcription text or empty                 | `websocket.py`          |
| `recomendacao_gerada`   | TEXT      | AI recommendation or rejection reason            | `websocket.py`          |
| `resultado_feedback`    | TEXT      | Status: `processado`, `discarded`, `mock_voice`  | `websocket.py`          |
| `funcionario_id`        | INTEGER   | Matched employee ID (nullable)                   | `speaker_id.py`         |
| `modelo_stt`            | TEXT      | STT model used (e.g., whisper, deepgram)         | `transcription.py`      |
| `custo_estimado`        | REAL      | Estimated API cost                               | `transcription.py`      |
| `snr`                   | REAL      | SNR from transcription module                    | `transcription.py`      |
| `grok_raw_response`     | TEXT      | Raw JSON from AI                                 | `websocket.py`          |
| `speaker_data`          | TEXT      | JSON of speaker predictions                      | `speaker_id.py`         |
| `interaction_type`      | TEXT      | `valid`, `discarded_empty`, `mock_voice`         | `websocket.py` **NEW**  |

### Timing Columns

| Column                   | Type      | Description                            | Source File        |
|--------------------------|-----------|----------------------------------------|--------------------|
| `ts_audio_received`      | TIMESTAMP | When audio arrived                     | `websocket.py`     |
| `ts_transcription_sent`  | TIMESTAMP | When STT request started               | `websocket.py`     |
| `ts_transcription_ready` | TIMESTAMP | When STT response returned             | `websocket.py`     |
| `ts_ai_request`          | TIMESTAMP | When AI request started                | `websocket.py`     |
| `ts_ai_response`         | TIMESTAMP | When AI response returned              | `websocket.py`     |
| `ts_client_sent`         | TIMESTAMP | When recommendation sent to client     | `websocket.py`     |

### VAD Segment Metadata (from `vad.py`)

| Column                       | Type    | Description                                   | Source File   |
|------------------------------|---------|-----------------------------------------------|---------------|
| `segment_duration_ms`        | INTEGER | Duration of audio segment in ms               | `websocket.py`|
| `segment_bytes`              | INTEGER | Size of the segment in bytes                  | `websocket.py`|
| `frames_len`                 | INTEGER | Number of VAD frames                          | `vad.py`      |
| `cut_reason`                 | TEXT    | `silence_end` or `safety_limit`               | `vad.py`      |
| `silence_frames_count_at_cut`| INTEGER | Frames of silence before cut                  | `vad.py`      |
| `noise_level_start`          | REAL    | EMA noise level at segment start              | `vad.py`      |
| `noise_level_end`            | REAL    | EMA noise level at segment end                | `vad.py`      |
| `dynamic_threshold_start`    | REAL    | Energy threshold at start                     | `vad.py`      |
| `dynamic_threshold_end`      | REAL    | Energy threshold at end                       | `vad.py`      |
| `energy_rms_mean`            | REAL    | Mean RMS energy of segment                    | `vad.py` / `audio_analysis.py` |
| `energy_rms_max`             | REAL    | Max RMS energy of segment                     | `vad.py` / `audio_analysis.py` |

### VAD Configuration Snapshot (for historical analysis)

| Column                | Type    | Description                         | Source File   |
|-----------------------|---------|-------------------------------------|---------------|
| `threshold_multiplier`| REAL    | VAD threshold multiplier            | `vad.py`      |
| `min_energy_threshold`| REAL    | Minimum energy to trigger           | `vad.py`      |
| `alpha`               | REAL    | EMA alpha for noise adaptation      | `vad.py`      |
| `vad_aggressiveness`  | INTEGER | WebRTC VAD mode (0-3)               | `vad.py`      |
| `silence_frames_needed`| INTEGER| Frames of silence to cut            | `vad.py`      |
| `pre_roll_len`        | INTEGER | Pre-roll buffer size                | `vad.py`      |
| `segment_limit_frames`| INTEGER | Max segment length (safety cutoff)  | `vad.py`      |

### Advanced Audio Metrics (from `audio_analysis.py`)

| Column              | Type | Description                                | Source File          |
|---------------------|------|--------------------------------------------|----------------------|
| `peak_dbfs`         | REAL | Peak amplitude in dBFS                     | `audio_analysis.py`  |
| `clipping_ratio`    | REAL | Ratio of samples near clipping (>0.995)    | `audio_analysis.py`  |
| `dc_offset`         | REAL | Mean value (DC offset)                     | `audio_analysis.py`  |
| `zcr`               | REAL | Zero Crossing Rate                         | `audio_analysis.py`  |
| `spectral_centroid` | REAL | Spectral centroid (brightness)             | `audio_analysis.py`  |
| `band_energy_low`   | REAL | Energy in 0-250Hz band                     | `audio_analysis.py`  |
| `band_energy_mid`   | REAL | Energy in 250-4000Hz band                  | `audio_analysis.py`  |
| `band_energy_high`  | REAL | Energy in 4000-8000Hz band                 | `audio_analysis.py`  |
| `snr_estimate`      | REAL | Estimated SNR from segment                 | `audio_analysis.py`  |
| `audio_cleaner_gain_db` | REAL | Gain (reduction) applied by noise filter | `audio_processor.py` |

### Pitch & Voice Features

| Column                  | Type | Description                      | Source File          |
|-------------------------|------|----------------------------------|----------------------|
| `audio_pitch_mean`      | REAL | Mean fundamental frequency (F0)  | `audio_analysis.py`  |
| `audio_pitch_std`       | REAL | Std deviation of F0              | `audio_analysis.py`  |
| `spectral_centroid_mean`| REAL | Mean spectral centroid           | `audio_analysis.py`  |

### System & Config Snapshots

| Column             | Type | Description                               | Source File      |
|--------------------|------|-------------------------------------------|------------------|
| `config_snapshot`  | TEXT | JSON with active config at connection     | `websocket.py`   |
| `mock_status`      | TEXT | JSON if in mock mode                      | `websocket.py`   |
| `cpu_usage_percent`| REAL | Server CPU % at processing time           | `system_monitor` |
| `ram_usage_mb`     | REAL | Server RAM usage at processing time       | `system_monitor` |

---

## Notes on NULL Values

The following columns may be **NULL** under certain conditions:

| Column(s)                         | When NULL                                              |
|-----------------------------------|--------------------------------------------------------|
| `funcionario_id`                  | No employee voice matched                              |
| `grok_raw_response`, `ts_ai_*`    | No AI call was made (empty transcription or mock)      |
| `ts_client_sent`                  | No recommendation was sent to client                   |
| `config_snapshot`                 | Never null (always captured at connection)             |
| Advanced audio metrics            | If `audio_analysis.py` fails, defaults to 0.0          |

---

## `interaction_type` Values

| Value             | Meaning                                               |
|-------------------|-------------------------------------------------------|
| `valid`           | Audio was transcribed and processed normally          |
| `discarded_empty` | VAD triggered but transcription returned empty        |
| `mock_voice`      | Running in MOCK_VOICE mode (no real STT)              |

---

*Generated: 2026-01-21*
