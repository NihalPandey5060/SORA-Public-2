import asyncio
import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import redis  # type: ignore
from dotenv import load_dotenv  # type: ignore
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore

from app_config import load_app_config
from errorHandler import ErrorHandler
from pipeline.session_manger import Session_Manger

try:
    import numpy as np
    NUMPY_IMPORT_ERROR = None
except Exception as exc:
    np = None  # type: ignore[assignment]
    NUMPY_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"

try:
    from fer import FER
    FER_IMPORT_ERROR = None
except Exception as exc:
    FER = None  # type: ignore[assignment]
    FER_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"

try:
    import whisper
    WHISPER_IMPORT_ERROR = None
except Exception as exc:
    whisper = None  # type: ignore[assignment]
    WHISPER_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"

try:
    from keras_facenet import FaceNet
    FACENET_IMPORT_ERROR = None
except Exception as exc:
    FaceNet = None  # type: ignore[assignment]
    FACENET_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"

try:
    from mtcnn import MTCNN
    MTCNN_IMPORT_ERROR = None
except Exception as exc:
    MTCNN = None  # type: ignore[assignment]
    MTCNN_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"

load_dotenv()

ENV = os.getenv("ENV", "dev")
app = FastAPI(
    docs_url="/api/docs" if ENV == "dev" else None,
    openapi_url="/api/openapi.json" if ENV == "dev" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

MEDIA_DIR = Path("media")
AUDIO_DIR = MEDIA_DIR / "audio"
VIDEO_DIR = MEDIA_DIR / "video"
VERIFICATION_DIR = MEDIA_DIR / "verification"

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory="media"), name="media")

redis_client: Optional[redis.Redis] = None
session_manger: Optional[Session_Manger] = None
active_clients = {}


def append_binary_file(path: Path, data: bytes) -> None:
    with open(path, "ab") as f:
        f.write(data)


def write_binary_file(path: Path, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


@app.websocket("/ws/media")
async def streamer(ws: WebSocket):
    await ws.accept()

    global session_manger
    if session_manger is None:
        await ErrorHandler.send_error(ws, "Session manager is not initialized", code=500)
        await ws.close()
        return

    try:
        init_msg = await ws.receive_text()
    except WebSocketDisconnect:
        print("client got disconnected")
        return

    try:
        init_data = json.loads(init_msg)
    except json.JSONDecodeError:
        await ErrorHandler.send_error(ws, "Invalid init message", code=400)
        await ws.close()
        return

    if init_data.get("type") != "init":
        await ws.close()
        return

    session_id = init_data.get("session_id")
    if not session_id:
        await ErrorHandler.send_error(ws, "Missing session_id", code=400)
        await ws.close()
        return

    client_session = await session_manger.connect(session_id=session_id)

    if hasattr(client_session, "set_pipeline_error_callback"):
        async def pipeline_error_callback(stage: str, message: str):
            await ws.send_json({
                "type": "error",
                "timestamp": int(time.time() * 1000),
                "id": session_id,
                "payload": {
                    "stage": stage,
                    "message": message,
                },
                "metadata": {
                    "speaker": "avatar",
                    "conversation_id": session_id,
                },
            })

        client_session.set_pipeline_error_callback(pipeline_error_callback)

    registration_process = "Not_Done"

    audio_session_file = AUDIO_DIR / f"audio_{session_id}.pcm"
    audio_session_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"Streaming audio to: {audio_session_file}")

    try:
        while True:
            message = await ws.receive_text()

            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await ErrorHandler.send_error(ws, "Invalid JSON message", code=400)
                continue

            if not data or not data.get("type"):
                await ErrorHandler.send_error(ws, "Invalid message format", code=400)
                continue

            if data["type"] == "audio_chunk":
                payload = data.get("payload", {})
                if not payload:
                    await ErrorHandler.send_error(ws, "Invalid audio chunk payload", code=400)
                    continue

                audio = payload.get("audio", {})
                if not audio or "data" not in audio:
                    await ErrorHandler.send_error(ws, "Invalid audio data", code=400)
                    continue

                audio_bytes = base64.b64decode(audio["data"])
                if not audio_bytes:
                    await ErrorHandler.send_error(ws, "Empty audio data", code=400)
                    continue

                if np is None:
                    output = await client_session.handle_voice(audio_bytes)
                else:
                    pcm_audio = np.frombuffer(audio_bytes, dtype="<i2")
                    output = await client_session.handle_voice(pcm_audio)

                if output:
                    user_query = output.get("User_query", "")
                    llm_response = output.get("llm_response", "")
                    print(f"User Query : {user_query}")
                    print(f"llm response : {llm_response}")

                await asyncio.to_thread(append_binary_file, audio_session_file, audio_bytes)

            elif data["type"] == "text_message":
                payload_text = data.get("payload", {}).get("text", "")
                if not payload_text:
                    await ErrorHandler.send_error(ws, "Invalid text message payload", code=400)
                    continue

                print("User Message: " + payload_text)
                start_ms = int(time.time() * 1000)

                result = await client_session.handle_text(payload_text)
                if isinstance(result, tuple):
                    text_result, output_id = result
                else:
                    text_result, output_id = result, None

                end_ms = int(time.time() * 1000)
                elapsed_ms = end_ms - start_ms

                await ws.send_json({
                    "type": "text_message",
                    "timestamp": int(time.time() * 1000),
                    "id": data.get("id", ""),
                    "payload": {
                        "text": f"{text_result}\n\nTook: {elapsed_ms} ms",
                        "output_id": output_id,
                        "visemes": [],
                    },
                    "metadata": {
                        "speaker": "avatar",
                        "conversation_id": data.get("metadata", {}).get("conversation_id", ""),
                    },
                })

            elif data["type"] == "video_frame":
                payload = data.get("payload", {})
                if not payload:
                    await ErrorHandler.send_error(ws, "Invalid video frame payload", code=400)
                    continue

                video_img = payload.get("video", {})
                if not video_img or "data" not in video_img:
                    await ErrorHandler.send_error(ws, "Invalid video image data", code=400)
                    continue

                timestamp_str = data.get("timestamp", "")
                if not timestamp_str:
                    await ErrorHandler.send_error(ws, "Invalid timestamp", code=400)
                    continue

                video_bytes = base64.b64decode(video_img.get("data", ""))
                if not video_bytes:
                    await ErrorHandler.send_error(ws, "Invalid video frame data", code=400)
                    continue

                video_session_dir = VIDEO_DIR / session_id
                video_session_dir.mkdir(parents=True, exist_ok=True)
                video_file = video_session_dir / f"video_{timestamp_str}.jpg"

                await asyncio.to_thread(write_binary_file, video_file, video_bytes)

                if registration_process == "Not_Done":
                    reg = await client_session.handle_registration(image_path=str(video_file))
                    print(f"Registration : {reg}")

                    if reg == "Not registered":
                        await ws.send_json({
                            "type": "Pop_up",
                            "timestamp": int(time.time() * 1000),
                            "id": data.get("id", ""),
                            "payload": {
                                "title": "User face is not found",
                                "message": "Would like to register",
                                "visemes": [],
                            },
                            "metadata": {
                                "speaker": None,
                                "conversation_id": None,
                            },
                        })
                    else:
                        await ws.send_json({
                            "type": "text_message",
                            "timestamp": int(time.time() * 1000),
                            "id": data.get("id", ""),
                            "payload": {
                                "text": f"Welcome {reg}!",
                                "visemes": [],
                            },
                            "metadata": {
                                "speaker": "avatar",
                                "conversation_id": data.get("metadata", {}).get("conversation_id", ""),
                            },
                        })

                    registration_process = "Done"
                    print(f"Registration process : {registration_process}")

                emotion_detector = getattr(app.state, "fer", None)
                if emotion_detector is not None:
                    await client_session.handle_video(emotion_detector, image_path=str(video_file))

            elif data["type"] == "user_verification":
                payload = data.get("payload", {})
                username = payload.get("username", "unknown").strip()
                photos = payload.get("photos", [])

                if not username:
                    await ErrorHandler.send_error(ws, "Username is required", code=400)
                    continue

                if len(photos) != 5:
                    await ErrorHandler.send_error(
                        ws, f"Expected 5 photos, got {len(photos)}", code=400
                    )
                    continue

                user_dir = VERIFICATION_DIR / f"{username}_{session_id}"
                user_dir.mkdir(parents=True, exist_ok=True)

                saved_paths = []
                failed = False

                for photo in photos:
                    index = photo.get("index")
                    b64_data = photo.get("data", "")

                    if not b64_data:
                        await ErrorHandler.send_error(
                            ws, f"Empty data for photo {index}", code=400
                        )
                        failed = True
                        break

                    try:
                        image_bytes = base64.b64decode(b64_data)
                    except Exception as e:
                        await ErrorHandler.send_error(
                            ws, f"Invalid base64 on photo {index}: {str(e)}", code=400
                        )
                        failed = True
                        break

                    file_path = user_dir / f"photo_{index}.jpg"
                    await asyncio.to_thread(write_binary_file, file_path, image_bytes)
                    saved_paths.append(str(file_path))
                    print(f"Saved: {file_path}  ({len(image_bytes)} bytes)")

                if failed:
                    continue

                try:
                    registered = await client_session.handle_new_user_registration(
                        username,
                        saved_paths,
                    )
                    if not registered:
                        await ErrorHandler.send_error(
                            ws, "No valid face found in registration photos", code=422
                        )
                        continue

                    registration_process = "Done"
                    print(f"User '{username}' registered with {len(saved_paths)} photos")
                except Exception as e:
                    print(f"Registration failed for '{username}': {e}")
                    await ErrorHandler.send_error(ws, "Registration failed", code=500)
                    continue

                await ws.send_json({
                    "type": "text_message",
                    "timestamp": int(time.time() * 1000),
                    "id": data.get("id", ""),
                    "payload": {
                        "text": f"Welcome {username}! You've been registered successfully.",
                        "visemes": [],
                    },
                    "metadata": {
                        "speaker": "avatar",
                        "conversation_id": data.get("metadata", {}).get("conversation_id", ""),
                    },
                })

            elif data["type"] == "popup_response":
                response = data.get("payload", {}).get("response", "")
                if response == "no":
                    registration_process = "Done"
                    print(f"User declined registration for session {session_id}")
                    await ws.send_json({
                        "type": "text_message",
                        "timestamp": int(time.time() * 1000),
                        "id": data.get("id", ""),
                        "payload": {
                            "text": "No problem, continuing without registration.",
                            "visemes": [],
                        },
                        "metadata": {
                            "speaker": "avatar",
                            "conversation_id": data.get("metadata", {}).get("conversation_id", ""),
                        },
                    })

            else:
                print("Unknown message type:", data["type"])
                await ErrorHandler.send_error(ws, "Unknown message type", code=400)

    except WebSocketDisconnect:
        await session_manger.disconnect(session_id=session_id)
        print(f"Client disconnected {session_id}")
        return

    except Exception as e:
        print("Internal error:", e)
        await session_manger.disconnect(session_id=session_id)
        await ErrorHandler.send_error(ws, "Internal server error", code=500)
        await ws.close()
        return


@app.websocket("/ws/connect")
async def connect(websocket: WebSocket):
    await websocket.accept()
    session_id = str(time.time())
    active_clients[session_id] = websocket

    print(f"CLIENT CONNECTED: {session_id}")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received message from {session_id}: {data}")

            try:
                message = json.loads(data)
                if message.get("type") == "connect":
                    token = message.get("token")
                    response = {
                        "type": "connected",
                        "message": "Connection established",
                    }
                    await websocket.send_text(json.dumps(response))
                    continue
            except json.JSONDecodeError:
                pass

            await websocket.send_text(f"Echo: {data}")

    except WebSocketDisconnect:
        print(f"CLIENT DISCONNECTED: {session_id}")
        active_clients.pop(session_id, None)


@app.on_event("startup")
async def startup_event():
    global redis_client, session_manger

    try:
        app.state.config = load_app_config()
        print(f"Loaded app config for {app.state.config.get('persona_name', 'avatar')}")
    except Exception as e:
        app.state.config = {}
        print(f"Failed to load app config: {e}")

    try:
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=False,
        )
        redis_client.ping()  # type: ignore
        print("Redis connection established successfully")
    except Exception as e:
        print(f"Failed to connect to Redis: {e}. Caching will be disabled.")
        redis_client = None

    if FER is None:
        app.state.fer = None
        print(f"FER unavailable: {FER_IMPORT_ERROR}")
    else:
        try:
            app.state.fer = FER()
            print("FER is loaded")
        except Exception as e:
            app.state.fer = None
            print(f"FER unavailable: {e}")

    app.state.whisper = None
    app.state.facenet = None
    app.state.mtcnn = None

    if whisper is None:
        print(f"Whisper unavailable: {WHISPER_IMPORT_ERROR}")
    else:
        try:
            app.state.whisper = await asyncio.to_thread(whisper.load_model, "base")
            print("Whisper model loaded")
        except Exception as e:
            print(f"Whisper unavailable: {e}")

    if FaceNet is None:
        print(f"FaceNet unavailable: {FACENET_IMPORT_ERROR}")
    else:
        try:
            app.state.facenet = await asyncio.to_thread(FaceNet)
            print("FaceNet model loaded")
        except Exception as e:
            print(f"FaceNet unavailable: {e}")

    if MTCNN is None:
        print(f"MTCNN unavailable: {MTCNN_IMPORT_ERROR}")
    else:
        try:
            app.state.mtcnn = await asyncio.to_thread(MTCNN)
            print("MTCNN model loaded")
        except Exception as e:
            print(f"MTCNN unavailable: {e}")

    try:
        session_manger = Session_Manger(
            whisper_model=app.state.whisper,
            facenet=app.state.facenet,
            mtcnn=app.state.mtcnn,
            fer=app.state.fer,
            config=app.state.config,
        )
    except TypeError:
        session_manger = Session_Manger()


@app.on_event("shutdown")
async def shutdown_event():
    global redis_client
    if redis_client:
        try:
            redis_client.close()
            print("Redis connection closed")
        except Exception as e:
            print(f"Error closing Redis connection: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
