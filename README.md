# Yardhouse AI Avatar Backend Pipeline

This project is a multimodal AI avatar system for a Yardhouse-style restaurant assistant. It combines a FastAPI backend, a Vite React frontend, WebSocket media streaming, face registration, speech transcription, menu-aware LLM responses, text-to-speech generation, and viseme output for avatar mouth animation.

The system accepts text, microphone audio, and camera frames from the frontend. The backend maintains a session for each user, recognizes or registers faces, detects emotion from video frames, retrieves relevant menu context, generates a response with an LLM, and optionally produces audio plus `output.vsim.json` for lip-sync playback.

## Current Project Structure

```text
.
├── main.py                         # FastAPI app, WebSockets, startup model loading, media serving
├── app_config.py                   # Central app configuration loader
├── app_config.example.json          # Safe sample config committed to repo
├── app_config.json                  # Local runtime config, ignored by git
├── db.py                            # SQLite session setup
├── model.py                         # SQLAlchemy User and MenuItem models
├── errorHandler.py                  # WebSocket error helper
├── Caddyfile                        # Reverse proxy/static file config
├── docker-compose.yml               # Dev services: Redis, backend, frontend
├── docker-compose.prod.yml          # Production-style services
├── pipeline/
│   ├── session_manger.py            # Session manager and fallback session
│   ├── Client_services.py           # Main AI pipeline/session logic
│   ├── menu.txt                     # Knowledge base used for menu retrieval
│   └── scripts/
│       ├── audio_generation.py      # ElevenLabs TTS and WAV generation
│       ├── text_to_phoneme.py       # Text to phoneme conversion
│       ├── text_alingment.py        # Audio/text alignment
│       ├── map_phonemes_to_visemes.py
│       ├── phoneme_to_viseme.py
│       └── build_vism_file.py       # Final output.vsim.json generation
├── client/
│   ├── src/App.jsx                  # React UI, WebSocket client, chat, media capture, viseme consumer
│   └── src/index.css                # UI styling, including avatar mouth indicator
├── routes/                          # REST routers for auth/menu/plugins; available but not mounted in main.py
├── libs/                            # Auth, JWT, validation, config helpers
├── models/                          # Pydantic models
└── media/                           # Runtime-generated audio, video, registration, and output files
```

## Main Features

- Text chat over WebSocket.
- Microphone streaming as PCM audio chunks.
- Camera frame streaming for face recognition and emotion detection.
- Face registration using five captured photos.
- Whisper speech-to-text support.
- Groq LLM response generation.
- Semantic menu lookup using SentenceTransformers and FAISS.
- Response caching through `media/output/question_result_path.json`.
- ElevenLabs text-to-speech generation.
- Phoneme, alignment, viseme timeline, and final `output.vsim.json` generation.
- Frontend polling for generated visemes and simple mouth-state playback.
- Static media serving through `/media`.
- Optional Redis support.

## Active Runtime Endpoints

The active backend behavior is mainly WebSocket based.

```text
GET /media/*
WS  /ws/media
WS  /ws/connect
```

The route files in `routes/` define REST APIs for auth, menu, and weather plugins, but they are not currently attached in `main.py` with `app.include_router(...)`. The WebSocket/avatar pipeline is the main working path.

## Configuration

The system now uses a central config file.

```text
app_config.example.json  # committed sample
app_config.json          # local runtime config, ignored by git
```

Important config fields:

```json
{
  "persona_name": "Yardhouse",
  "system_prompt_base": "You are a waiter at Yardhouse...",
  "knowledge_base_path": "pipeline/menu.txt",
  "greeting_response": "Hi{name}! Welcome to Yardhouse. How can I help you today?",
  "llm_model": "llama-3.1-8b-instant",
  "tts_voice_id": "21m00Tcm4TlvDq8ikWAM",
  "tts_model": "eleven_flash_v2_5",
  "stt_language": "en",
  "face_match_threshold": 0.4
}
```

Environment variables are still required for external APIs:

```env
GROQ_API_KEY=your_groq_key
Elevens_lab_key=your_elevenlabs_key
ENABLE_AVATAR_PIPELINE=1
```

## Priority Fixes Completed

### P0.1 Enable Avatar Pipeline

Problem:
The avatar pipeline could remain disabled because `ENABLE_AVATAR_PIPELINE` defaulted to false-like behavior.

Fix:
`docker-compose.yml` now sets:

```yaml
ENABLE_AVATAR_PIPELINE=1
```

Result:
When a message is sent, the backend can start the audio/viseme generation path. The logs now include:

```text
Starting viseme pipeline for media/output/<id>
```

### P0.2 Fix Hardcoded Cache Path

Problem:
The phoneme cache path previously depended on a machine-specific absolute path. That made the pipeline fail on other systems.

Fix:
`pipeline/scripts/text_to_phoneme.py` now builds the cache path from the project location:

```python
BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_PATH = BASE_DIR / "media" / "output" / "phoneme_cache.json"
```

Result:
The file is created under the project runtime folder:

```text
media/output/phoneme_cache.json
```

### P0.3 Fix Duplicate JSON Key

Problem:
The WebSocket response had duplicate `"text"` keys in the payload. Python silently kept only the last one, which made the response shape unreliable.

Fix:
`main.py` now sends only one `text` field and includes `output_id`:

```json
{
  "payload": {
    "text": "response text",
    "output_id": "generated-folder-id",
    "visemes": []
  }
}
```

Result:
The frontend receives a stable response and can use `output_id` to find generated visemes.

### P1.1 Move Inference Off the Event Loop

Problem:
Face detection, face embeddings, FER emotion detection, Whisper transcription, menu search, and LLM calls can block for hundreds of milliseconds or more. Running them directly inside async WebSocket handlers risks freezing the server.

Fix:
Blocking inference calls now use `asyncio.to_thread(...)` or executor calls.

Examples:

```python
faces = await asyncio.to_thread(self.mtcnn.detect_faces, detection_frame)
embedding = await asyncio.to_thread(lambda: self.facenet.embeddings(image)[0])
result = await asyncio.to_thread(detector.detect_emotions, frame)
```

Result:
WebSocket handling stays responsive while expensive model work runs outside the event loop.

### P1.2 Add Static File Serving

Problem:
The frontend needed access to generated files such as:

```text
media/output/<id>/output.vsim.json
```

Fix:
FastAPI now mounts the media directory:

```python
app.mount("/media", StaticFiles(directory="media"), name="media")
```

The `Caddyfile` was also cleaned up to remove hardcoded absolute paths:

```caddy
handle_path /media/* {
    root * ./media
    file_server
}
```

Result:
Generated media can be served through:

```text
http://localhost:8000/media/output/<id>/output.vsim.json
```

### P1.3 Frontend Viseme Consumer

Problem:
The frontend included `visemes: []` in payloads, but it did not actually fetch or play generated viseme files.

Fix:
`client/src/App.jsx` now:

- reads `output_id` from backend messages,
- polls `/media/output/<output_id>/output.vsim.json`,
- plays the viseme timeline with `setTimeout`,
- updates a small avatar mouth indicator and viseme status.

Result:
When `output.vsim.json` is generated, the frontend consumes it and visually reflects mouth movement.

### P2.1 Model Singletons

Problem:
Loading Whisper, FaceNet, MTCNN, and FER per session wastes memory and limits concurrent users.

Fix:
Models are loaded once during FastAPI startup in `main.py`:

```python
app.state.whisper = await asyncio.to_thread(whisper.load_model, "base")
app.state.facenet = await asyncio.to_thread(FaceNet)
app.state.mtcnn = await asyncio.to_thread(MTCNN)
app.state.fer = FER()
```

They are passed into `Session_Manger`, then into each `CLientLLMSession`.

Result:
Multiple sessions share the same model instances instead of loading separate copies.

### P2.2 Lightweight Embedding Model

Problem:
`all-mpnet-base-v2` is large for a small menu knowledge base.

Fix:
Menu retrieval now uses:

```python
SentenceTransformer("all-MiniLM-L6-v2")
faiss.IndexFlatL2(384)
```

Result:
The menu embedding model is smaller and faster to load while still being suitable for the current knowledge base size.

### P3.1 Domain Configuration File

Problem:
Persona text, menu path, LLM model, TTS settings, language, and face threshold were hardcoded across multiple files.

Fix:
Added:

```text
app_config.py
app_config.example.json
app_config.json
```

`main.py` loads the config at startup and passes it into the session manager. `Client_services.py` reads prompt, model, menu path, STT language, greeting, and face threshold from the config. `audio_generation.py` reads TTS voice and model from the config.

Result:
The assistant identity and domain can be changed by editing `app_config.json` and restarting, without changing Python code.

### P3.2 Pipeline Error Reporting

Problem:
The avatar generation pipeline previously caught all errors and only printed them. The frontend had no idea whether TTS, phoneme generation, alignment, or viseme generation failed.

Fix:
`text_voice_phoneme_generation()` now runs stage-by-stage:

```python
pipeline_steps = [
    ("tts", audio_generation_main),
    ("phoneme", text_to_phoneme_main),
    ("alignment", text_alignment_main),
    ("viseme_mapping", mappinf_phonems_to_vismes),
    ("vsim", build_vism_file),
]
```

On failure, the backend sends a WebSocket frame:

```json
{
  "type": "error",
  "payload": {
    "stage": "tts",
    "message": "..."
  }
}
```

Result:
The frontend can show which stage failed instead of silently doing nothing.

### P3.3 Adaptive TTS Chunk Count

Problem:
The old TTS path always used six chunks, even for very short replies. That wastes ElevenLabs API calls and increases latency.

Fix:
`audio_generation.py` now computes chunks from response length:

```python
def choose_tts_chunk_count(text: str) -> int:
    text_length = len(text.strip())
    if text_length == 0:
        return 1
    return max(1, min(MAX_TTS_CHUNKS, (text_length + 149) // 150))
```

Result:
Short replies use one TTS request, while long replies can still split into multiple chunks.

## Problems Encountered and How They Were Dealt With

### Hardcoded Paths

Several paths assumed a specific machine or deployment folder. This made the project fragile outside the original environment.

Approach:
Paths were changed to relative/project-based paths. The Caddyfile and phoneme cache path were cleaned first because they directly blocked media serving and phoneme generation.

### Async Server Blocking

The backend uses WebSockets, so blocking model inference inside the event loop could freeze all clients.

Approach:
Blocking inference was moved into worker threads. This kept the WebSocket loop free to keep receiving audio, text, and video messages.

### Missing Frontend Viseme Playback

The backend generated an `output_id`, but the frontend did not use it.

Approach:
The frontend now polls the generated `output.vsim.json` file and uses the offsets to update a mouth state. This gives a visible confirmation that the viseme pipeline is connected end-to-end.

### Heavy Per-Session Model Loading

Loading AI models per user would create major memory pressure.

Approach:
Models were moved to FastAPI startup and shared through the session manager.

### Silent Avatar Pipeline Failures

The previous pipeline swallowed errors with `print()`, so failures were hard to debug.

Approach:
The pipeline was split into named stages. Each stage reports its own failure over WebSocket.

### TTS API Waste

Using six TTS chunks for every response caused unnecessary API calls.

Approach:
The chunk count now scales with response length.

### Docker Runtime Issue

Docker commands may fail if Docker Desktop is installed but the engine is not running.

Symptom:

```text
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

Fix:
Start Docker Desktop, wait for the engine to run, and verify with:

```powershell
docker info
```

## Validation

### P0.1 Enable Avatar Pipeline

Validation was performed by tracing the request flow from WebSocket message handling to the avatar generation pipeline. The check was that requests continue into the audio and viseme generation stages when `ENABLE_AVATAR_PIPELINE=1` is set, instead of exiting early due to configuration.

### P0.2 Fix Hardcoded Cache Path

Validation was performed by reviewing all phoneme cache read and write operations. The check was that cache files are resolved relative to the project root rather than a machine-specific absolute path, allowing the application to run across different environments without path-related failures.

### P0.3 Fix Duplicate JSON Key

Validation was performed by inspecting the final WebSocket response payload. The check was that only a single `text` field is present and that the payload consistently exposes both the generated response and the associated `output_id` required by the frontend.

### P1.1 Move Inference Off the Event Loop

Validation was performed by reviewing all inference-heavy execution paths including face detection, face embeddings, emotion detection, speech transcription, retrieval, and LLM generation. The check was that these operations execute through `asyncio.to_thread(...)` rather than directly inside async WebSocket handlers, preventing event loop blocking.

### P1.2 Add Static File Serving

Validation was performed by tracing the lifecycle of generated media files. The check was that FastAPI and Caddy expose the same media directory and that generated artifacts such as `output.vsim.json` can be accessed through the `/media` endpoint.

### P1.3 Frontend Viseme Consumer

Validation was performed by reviewing the frontend flow after a backend response is received. The check was that `output_id` is extracted from the payload, used to locate the generated viseme file, and that the returned timeline data is consumed by the avatar mouth-state logic.

### P2.1 Model Singletons

Validation was performed by reviewing application startup and session creation paths. The check was that Whisper, FaceNet, MTCNN, and FER models are initialized once during startup and shared across sessions rather than being loaded separately for each user connection.

### P2.2 Lightweight Embedding Model

Validation was performed by reviewing the retrieval initialization flow. The check was that `all-MiniLM-L6-v2` is used as the embedding model and that the FAISS index configuration matches the model's embedding dimensions.

### P3.1 Domain Configuration File

Validation was performed by tracing configuration usage throughout the application. The check was that prompts, persona settings, menu paths, model configuration, language settings, thresholds, and TTS configuration are loaded from configuration files rather than hardcoded values.

### P3.2 Pipeline Error Reporting

Validation was performed by reviewing the error handling path for each pipeline stage. The check was that failures generate structured WebSocket error responses containing both the failing stage and the associated error details instead of being silently logged.

### P3.3 Adaptive TTS Chunk Count

Validation was performed by reviewing the chunk selection logic against different response lengths. The check was that shorter responses result in fewer TTS requests while longer responses continue to support chunked audio generation.

Overall validation focused on confirming that each fix resolves the identified issue, integrates correctly with the existing pipeline architecture, and preserves the expected flow of data between backend services and the frontend client.

## How to Run

### Docker

Make sure Docker Desktop is open and running:

```powershell
docker info
```

Then run:

```powershell
cd "C:\Users\Nihal31\OneDrive - Amrita Vishwa Vidyapeetham\Documents\Sora_mind\gpu-avatar-backend-pipeline-nihal"
docker compose up --build
```

### Local Backend

```powershell
cd "C:\Users\Nihal31\OneDrive - Amrita Vishwa Vidyapeetham\Documents\Sora_mind\gpu-avatar-backend-pipeline-nihal"
python -m pip install -r requirements-app.txt
python main.py
```

### Local Frontend

Open a second terminal:

```powershell
cd "C:\Users\Nihal31\OneDrive - Amrita Vishwa Vidyapeetham\Documents\Sora_mind\gpu-avatar-backend-pipeline-nihal\client"
npm install
npm run dev
```

## Verification Checklist

Use this checklist after setup.

| Test | Expected Result |
| --- | --- |
| Send a text message | Avatar responds in chat |
| Check backend logs | `Starting viseme pipeline...` appears |
| Check generated output folder | `llm_response.txt`, `final_audio.wav`, `alignment.json`, `viseme_timeline.json`, and `output.vsim.json` are created |
| Open `/media/output/<id>/output.vsim.json` | Browser returns JSON |
| Frontend receives `output_id` | Mouth indicator starts updating after viseme file is ready |
| Short reply | TTS logs show fewer chunks, often `Chunk 1/1` |
| Invalid TTS/API setup | Frontend receives a pipeline error frame with stage name |
| Change `app_config.json` persona/prompt | Response behavior changes after restart |

## Known Notes

- `client/node_modules` is not committed. Run `npm install` before `npm run build`.
- Docker commands require Docker Desktop's engine to be running.
- `app_config.json` is ignored by git so local secrets or local domain changes are not accidentally committed.
- REST routers under `routes/` are defined but not mounted in `main.py`; WebSocket media/chat is the active path.
- The avatar pipeline depends on external tools and services such as Groq, ElevenLabs, Whisper, eSpeak, Aeneas, and ffmpeg-compatible audio handling.
