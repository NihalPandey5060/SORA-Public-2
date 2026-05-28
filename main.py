import queue
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from sqlalchemy.orm import Session # type: ignore
import json
import time
import os
from pathlib import Path
from datetime import datetime
from db import get_db
from model import MenuItem
import redis # type: ignore
from typing import Optional
import base64
from errorHandler import ErrorHandler
from dotenv import load_dotenv # type: ignore
from libs.encoder import webm_to_mp3
#from pipeline.rag_llm import llm_response
import asyncio
from pipeline.session_manger import Session_Manger
# from mtcnn import MTCNN 
# from sklearn.metrics.pairwise import cosine_similarity
# from keras_facenet import FaceNet

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



# load_and_index_menu()
# start_workers()
load_dotenv()
ENV = os.getenv("ENV", "dev")
app = FastAPI(docs_url='/api/docs' if ENV=='dev' else None, openapi_url="/api/openapi.json" if ENV == "dev" else None)


from routes import authRoute, menuRoute, pluginRoute


redis_client: Optional[redis.Redis] = None
CACHE_TTL = 3600 
MEDIA_DIR = Path("media")
AUDIO_DIR = MEDIA_DIR / "audio"
VIDEO_DIR = MEDIA_DIR / "video"
VERIFICATION_DIR = MEDIA_DIR / "verification"

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], 
    allow_headers=["*"],  
)

active_clients = {}

app.include_router(authRoute.auth_router)
app.include_router(menuRoute.menu_router)
app.include_router(pluginRoute.plug_router)

session_manger = Session_Manger()
# it stores the audio chunks in opus webm format and stores in webm files and it is acutally playable
@app.websocket("/ws/media")
async def streamer(ws: WebSocket):
    await ws.accept()
    try: 
        init_msg = await ws.receive_text()
    except WebSocketDisconnect: 
        print("client got disconnected")
        return 
    init_data = json.loads(init_msg)

    if init_data["type"] != "init":
        await ws.close()
        return 

    session_id = init_data["session_id"]
    client_session = await session_manger.connect(session_id=session_id) 
    Registration_process = "Not_Done"
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_file = AUDIO_DIR / f"audio.pcm"
    print(f"Streaming audio to: {output_file}")

    try:
        while True:
            message = await ws.receive_text()
            data = json.loads(message)
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
                # Convert Base64 → raw bytes
                audio_bytes = base64.b64decode(audio["data"])
                if not audio_bytes:
                    await ErrorHandler.send_error(ws, "Empty audio data", code=400)
                    continue
                if np is None:
                    output = await client_session.handle_voice(audio_bytes)
                else:
                    pcm_audio = np.frombuffer(audio_bytes,dtype="<i2")  
                    output = await client_session.handle_voice(pcm_audio)
                if output:
                    user_query = output["User_query"]
                    llm_response = output["llm_response"]
                    print(f"User Query : {user_query}")
                    print(f"llm response : {llm_response}")
                # await process_audio_chunk(pcm_audio=pcm_audio) 
                with open(output_file, "ab") as f:
                    f.write(audio_bytes)

                #print(f"Received and saved chunk of {len(audio_bytes)} bytes")
            elif data["type"] == 'text_message':
                payload_text = data.get("payload", {}).get("text", "")
                if not payload_text:
                    await ErrorHandler.send_error(ws, "Invalid text message payload", code=400)
                    continue
                print("User Message: " + payload_text)
                start_ms = int(time.time() * 1000)
                # llm_output = await asyncio.to_thread(llm_response, payload_text)
                result = await client_session.handle_text(payload_text)
                end_ms = int(time.time() * 1000)
                elapsed_ms = end_ms - start_ms
                await ws.send_json({
                    "type": "text_message",
                    "timestamp": int(time.time() * 1000),
                    "id": data.get("id", ""),
                    "payload": {
                        "text": "server response " + payload_text,
                        "text": f"{result}\n\nTook: {elapsed_ms} ms",
                        "visemes": [],
                    },
                    "metadata": {
                        "speaker": "avatar",
                        "conversation_id": data.get("metadata", {}).get("conversation_id", ""),
                    },
                })
            elif data['type'] == 'video_frame':
                payload = data.get("payload", {})
                if not payload:
                    await ErrorHandler.send_error(ws, "Invalid video frame payload", code=400)
                    continue
                video_img = payload.get("video", {})
                if not video_img or "data" not in video_img:
                    await ErrorHandler.send_error(ws, "Invalid video image data", code=400)
                    continue
                timestamp_str = data.get('timestamp', '')
                if not timestamp_str:
                    await ErrorHandler.send_error(ws, "Invalid timestamp", code=400)
                    continue
                video_bytes = base64.b64decode(video_img.get("data", ""))
                if not video_bytes:
                    await ErrorHandler.send_error(ws, "Invalid video frame data", code=400)
                    continue
                video_file = VIDEO_DIR / f"video_{timestamp_str}.jpg"
                with open(video_file, "wb") as vf:
                    vf.write(video_bytes)
                if Registration_process == "Not_Done":
                    reg = await client_session.handle_registration(image_path=video_file)
                    print(f"Registratoin : {reg}")
                    if reg=="Not registered":
                        # call the pop up 
                        await ws.send_json({
                            "type": "Pop_up",
                            "timestamp": int(time.time() * 1000),
                            "id": data.get("id", ""),
                            "payload": {
                                "title": "User face is not found",
                                "message":"Would like to register",
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
                    Registration_process = "Done"
                    print(f"Registration process : {Registration_process}") 
                emotion_detector = getattr(app.state, "fer", None)
                if emotion_detector is not None:
                    await client_session.handle_video(emotion_detector, image_path=video_file)
                
                #print(f"Received and saved video frame of {len(video_bytes)} bytes")
            elif data["type"] == "user_verification":
                # ✅ Fix typo: "payload" not "paylaod"
                payload = data.get("payload", {})

                username = payload.get("username", "unknown").strip()
                photos   = payload.get("photos", [])

                # 1. Validate
                if not username:
                    await ErrorHandler.send_error(ws, "Username is required", code=400)
                    continue

                if len(photos) != 5:
                    await ErrorHandler.send_error(
                        ws, f"Expected 5 photos, got {len(photos)}", code=400
                    )
                    continue

                # 2. Create a folder for this user's verification images
                #    e.g. media/verification/John_<session_id>/
                user_dir = VERIFICATION_DIR / f"{username}_{session_id}"
                user_dir.mkdir(parents=True, exist_ok=True)

                saved_paths = []
                failed = False

                for photo in photos:
                    index    = photo.get("index")          # 1–5
                    fmt      = photo.get("format", "webp")
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

                    # ✅ Non-blocking file write
                    await asyncio.to_thread(file_path.write_bytes, image_bytes)
                    saved_paths.append(file_path)
                    print(f"Saved: {file_path}  ({len(image_bytes)} bytes)")

                if failed:
                    continue

                # 3. Register the user using saved photos
                try:
                    registered = await client_session.handle_new_user_registration(
                        username,
                        saved_paths,
                    )
                    if not registered:
                        await ErrorHandler.send_error(ws, "No valid face found in registration photos", code=422)
                        continue
                    Registration_process = "Done"  # ✅ Mark registration complete
                    print(f"User '{username}' registered with {len(saved_paths)} photos")
                except Exception as e:
                    print(f"Registration failed for '{username}': {e}")
                    await ErrorHandler.send_error(ws, "Registration failed", code=500)
                    continue

                # 4. Confirm back to the frontend (shows in chat)
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
                    Registration_process = "Done"  # ✅ Stop asking on every video frame
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
                    # Optionally authenticate with token here
                    
                    response = {
                        "type": "connected",
                        "message": "Connection established"
                    }
                    await websocket.send_text(json.dumps(response))
                    continue
            except json.JSONDecodeError:
                pass

            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        print(f"CLIENT DISCONNECTED: {session_id}")
        del active_clients[session_id]


@app.on_event('startup')
def startup_event():
    global redis_client
    try:
        redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=False
        )
        redis_client.ping() # type: ignore
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

@app.on_event('shutdown')
def shutdown_event():
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

