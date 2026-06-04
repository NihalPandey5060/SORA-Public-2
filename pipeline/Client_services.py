import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import deque

import cv2
import numpy as np
import webrtcvad
from dotenv import load_dotenv
from groq import Groq
from keras_facenet import FaceNet
from scipy.signal import resample
from mtcnn import MTCNN

from app_config import DEFAULT_APP_CONFIG

try:
    import faiss
    from sentence_transformers import SentenceTransformer
except Exception as exc:
    faiss = None
    SentenceTransformer = None
    print(f"Semantic menu search unavailable: {exc.__class__.__name__}: {exc}")

try:
    from fer import FER
except Exception as exc:
    FER = None
    print(f"FER unavailable in Client_services: {exc.__class__.__name__}: {exc}")

from pipeline.scripts.audio_generation import audio_generation_main
from pipeline.scripts.build_vism_file import build_vism_file
from pipeline.scripts.map_phonemes_to_visemes import mappinf_phonems_to_vismes
from pipeline.scripts.phoneme_to_viseme import phoneme_to_viseme
from pipeline.scripts.text_alingment import text_alignment_main
from pipeline.scripts.text_to_phoneme import text_to_phoneme_main

load_dotenv()

PATH = "media/output"
JSON_PATH = PATH + "/question_result_path.json"

MEDIA_DIR = Path("media")
VERIFICATION_DIR = MEDIA_DIR / "verification"
FACE_ENCODINGS_PATH = VERIFICATION_DIR / "face_encodings.json"

FACE_EMBEDDING_SIZE = 512
MENU_EMBEDDER = None
MENU_INDEX = None
MENU_CHUNKS = None


def prev_ans(filepath=JSON_PATH):
    """Load previously stored question -> folder_path mapping."""
    if not os.path.exists(PATH):
        os.makedirs(PATH, exist_ok=True)

    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return {}
    else:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump({}, file)
        return {}


def save_prev_ans(question: str, folder_path: str, filepath=JSON_PATH):
    """Save question -> folder mapping."""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)
    else:
        data = {}

    data[question] = folder_path

    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_and_index_menu(filepath="pipeline/menu.txt"):
    """Load and index menu items for semantic search."""
    global MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS

    if MENU_EMBEDDER is not None and MENU_INDEX is not None and MENU_CHUNKS is not None:
        return MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS

    index = None
    embedder = None

    if faiss is not None and SentenceTransformer is not None:
        index = faiss.IndexFlatL2(384)
        embedder = SentenceTransformer("all-MiniLM-L6-v2")

    if not os.path.exists(filepath):
        print(f"Warning: Menu file {filepath} not found")
        MENU_EMBEDDER = embedder
        MENU_INDEX = index
        MENU_CHUNKS = []
        return MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    menu_chunks = [c.strip() for c in text.split("\n") if c.strip()]

    if menu_chunks and embedder is not None and index is not None:
        embeddings = embedder.encode(menu_chunks, convert_to_numpy=True).astype("float32")
        index.add(np.array(embeddings))

    MENU_EMBEDDER = embedder
    MENU_INDEX = index
    MENU_CHUNKS = menu_chunks
    return MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS


def is_avatar_pipeline_enabled():
    return os.getenv("ENABLE_AVATAR_PIPELINE", "0").lower() in {"1", "true", "yes", "on"}


def load_face_encoding_json(filename=FACE_ENCODINGS_PATH):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not read face encodings from {filename}: {exc}")
        return {}


def save_face_encoding_json(json_data, filename=FACE_ENCODINGS_PATH):
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    tmp_filename = Path(f"{filename}.tmp")
    with open(tmp_filename, "w", encoding="utf-8") as file:
        json.dump(json_data, file, indent=4)
    os.replace(tmp_filename, filename)


def load_face_encodings(filename=FACE_ENCODINGS_PATH):
    """Load face encodings from JSON file."""
    json_data = load_face_encoding_json(filename)
    if not json_data:
        return np.array([]), [], {}

    face_names = []
    known_embeddings = []

    for name, data in json_data.items():
        if not isinstance(data, dict) or "embedding" not in data:
            continue

        embedding = np.array(data["embedding"], dtype=np.float32)
        if embedding.ndim != 1 or embedding.shape[0] != FACE_EMBEDDING_SIZE:
            print(
                f"Skipping invalid face encoding for {name}: "
                f"expected {FACE_EMBEDDING_SIZE}, got {embedding.shape}"
            )
            continue

        face_names.append(name)
        known_embeddings.append(embedding)

    return np.array(known_embeddings), face_names, json_data


class CLientLLMSession:
    def __init__(
        self,
        client_id,
        whisper_model=None,
        facenet=None,
        mtcnn=None,
        fer=None,
        config=None,
    ):
        self.client_id = client_id
        self.config = DEFAULT_APP_CONFIG.copy()
        if config:
            self.config.update(config)

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")

        self.llm_client = Groq(api_key=api_key)
        self.vad = webrtcvad.Vad(2)

        # Shared singleton model injected from startup/session manager.
        self.stt_model = whisper_model
        self.fer = fer
        self.facenet = facenet
        self.mtcnn = mtcnn

        self.speech_buffer: List[np.ndarray] = []
        self.silence_count = 0

        # 48000 Hz * 0.030 sec = 1440 samples
        self.FRAME_30MS = 1440

        self.embedder, self.index, self.menu_chunks = load_and_index_menu(
            self.config["knowledge_base_path"]
        )
        self.chat_history = deque(maxlen=20)
        self.lock = asyncio.Lock()

        self.prev_data = prev_ans()
        self.emotion_history = deque(maxlen=50)
        self.frame_count = 0

        self.registration_state = False
        self.face_embedings, self.face_names, _ = load_face_encodings()
        self.username = ""
        self.pipeline_error_callback = None

    def set_pipeline_error_callback(self, callback):
        self.pipeline_error_callback = callback

    async def report_pipeline_error(self, stage: str, message: str):
        print(f"Avatar pipeline error [{stage}]: {message}")
        if self.pipeline_error_callback is None:
            return

        try:
            await self.pipeline_error_callback(stage, message)
        except Exception as exc:
            print(f"Could not send pipeline error to client: {exc}")

    async def text_voice_phoneme_generation(self, folder_path):
        """
        Folder layout:
            uuid/
                llm_response.txt
                final_audio.wav
                text_phonemes.txt
                viseme_timeline.json
                chunks/
                alignment.json
                output.vsim.json
        """
        print(f"Starting viseme pipeline for {folder_path}")
        loop = asyncio.get_running_loop()
        pipeline_steps = [
            ("tts", audio_generation_main),
            ("phoneme", text_to_phoneme_main),
            ("alignment", text_alignment_main),
            ("viseme_mapping", mappinf_phonems_to_vismes),
            ("vsim", build_vism_file),
        ]

        for stage, step in pipeline_steps:
            try:
                await loop.run_in_executor(None, step, folder_path)
            except Exception as e:
                await self.report_pipeline_error(stage, str(e))
                return

    def search_menu(self, user_query: str, k: int) -> str:
        """Search menu using semantic similarity."""
        if not self.menu_chunks:
            return "Menu information not available."

        if self.embedder is None or self.index is None:
            query_terms = {
                term.strip(".,!?;:()[]{}\"'").lower()
                for term in user_query.split()
                if len(term.strip(".,!?;:()[]{}\"'")) > 2
            }
            scored_chunks = []
            for chunk in self.menu_chunks:
                chunk_lower = chunk.lower()
                score = sum(1 for term in query_terms if term in chunk_lower)
                scored_chunks.append((score, chunk))

            scored_chunks.sort(key=lambda item: item[0], reverse=True)
            results = [chunk for score, chunk in scored_chunks[:k] if score > 0]
            if not results:
                results = self.menu_chunks[:k]
            return "\n".join(results)

        query_embedding = self.embedder.encode([user_query], convert_to_numpy=True).astype("float32")
        k = min(k, len(self.menu_chunks))
        _, indices = self.index.search(query_embedding, k)
        results = [self.menu_chunks[i] for i in indices[0]]
        return "\n".join(results)

    async def ask_llm(self, user_query: str) -> Tuple[str, Optional[str]]:
        """Send query to LLM and get response."""
        normalized_query = user_query.strip().lower().strip("'\".!?")

        if normalized_query in {"hi", "hello", "hey", "hii", "hiii"}:
            name = f" {self.username}" if self.username else ""
            return self.config["greeting_response"].format(name=name), None

        self.prev_data = prev_ans()

        async with self.lock:
            self.chat_history.append({"role": "user", "content": user_query})

            if user_query in self.prev_data:
                folder_path = self.prev_data[user_query]
                llm_response_path = os.path.join(folder_path, "llm_response.txt")

                if os.path.exists(llm_response_path):
                    llm_response = await asyncio.to_thread(
                        Path(llm_response_path).read_text,
                        encoding="utf-8",
                    )
                    self.chat_history.append({"role": "assistant", "content": llm_response})
                    print("Loaded response from cache")
                    return llm_response, Path(folder_path).name

            menu_content = await asyncio.to_thread(self.search_menu, user_query, 6)

            system_prompt = f"""{self.config["system_prompt_base"]}

Menu Information:
{menu_content}
"""

            if self.emotion_history:
                system_prompt = f"""{self.config["system_prompt_emotion"].format(
                    emotion=self.emotion_history[-1]
                )}

Menu Information:
{menu_content}
"""

            if self.username and self.emotion_history:
                system_prompt = f"""{self.config["system_prompt_user_emotion"].format(
                    username=self.username,
                    emotion=self.emotion_history[-1],
                )}

Menu Information:
{menu_content}
"""

            history = [{"role": "system", "content": system_prompt}]
            for msg in self.chat_history:
                if msg["role"] in {"user", "assistant"}:
                    history.append(msg)

            try:
                completion = await asyncio.to_thread(
                    self.llm_client.chat.completions.create,
                    model=self.config["llm_model"],
                    messages=history,
                    temperature=0.6,
                )

                reply = completion.choices[0].message.content.strip()
                self.chat_history.append({"role": "assistant", "content": reply})

                while len(self.chat_history) > 20:
                    self.chat_history.popleft()

                folder_name = str(uuid.uuid4())
                folder_path = os.path.join(PATH, folder_name)
                os.makedirs(folder_path, exist_ok=True)

                llm_response_file_path = os.path.join(folder_path, "llm_response.txt")
                with open(llm_response_file_path, "w", encoding="utf-8") as f:
                    f.write(reply)

                await asyncio.to_thread(save_prev_ans, user_query, folder_path)

                if is_avatar_pipeline_enabled():
                    asyncio.create_task(self.text_voice_phoneme_generation(folder_path=folder_path))

                return reply, folder_name

            except Exception as e:
                error_msg = f"Error getting LLM response: {str(e)}"
                print(error_msg)
                return "I apologize, I'm having trouble processing your request right now.", None

    async def handle_text(self, text: str) -> Tuple[str, Optional[str]]:
        """Handle text input from user."""
        try:
            return await self.ask_llm(user_query=text)
        except Exception as e:
            print(f"Error in handle_text: {e}")
            return "Sorry, I encountered an error processing your message.", None

    async def _transcribe_speech(self) -> str:
        """Transcribe buffered speech to text."""
        try:
            if not self.speech_buffer:
                return ""

            if self.stt_model is None:
                raise RuntimeError("Shared Whisper model not initialized")

            audio_48 = np.concatenate(self.speech_buffer).astype(np.float32)

            # Resample from 48kHz to 16kHz for Whisper
            new_len = int(len(audio_48) * 16000 / 48000)
            audio_16 = resample(audio_48, new_len) / 32768.0

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.stt_model.transcribe(
                    audio_16,
                    language=self.config["stt_language"],
                    fp16=False,
                ),
            )

            return result["text"].strip()

        except Exception as e:
            print(f"Error in transcription: {e}")
            return ""

    async def handle_voice(self, pcm_audio: np.ndarray) -> Optional[Dict[str, str]]:
        """Handle voice input with VAD and transcription."""
        try:
            is_speech = False

            for i in range(0, len(pcm_audio), self.FRAME_30MS):
                chunk = pcm_audio[i : i + self.FRAME_30MS]
                if len(chunk) == self.FRAME_30MS:
                    try:
                        if self.vad.is_speech(chunk.tobytes(), 48000):
                            is_speech = True
                            break
                    except Exception as e:
                        print(f"VAD error: {e}")
                        continue

            if is_speech:
                self.silence_count = 0
                self.speech_buffer.append(pcm_audio)

                if len(self.speech_buffer) > 400:
                    self.speech_buffer = self.speech_buffer[-400:]

                return None

            self.silence_count += 1

            if self.silence_count > 3 and self.speech_buffer:
                text = await self._transcribe_speech()
                self.speech_buffer = []
                self.silence_count = 0

                if text:
                    reply, output_id = await self.ask_llm(text)
                    return {
                        "User_query": text,
                        "llm_response": reply,
                        "output_id": output_id or "",
                    }

            return None

        except Exception as e:
            print(f"Error in handle_voice: {e}")
            self.speech_buffer = []
            self.silence_count = 0
            return None

    async def handle_registration(self, image_path):
        print(f"Checking registration for image: {image_path}")

        if self.mtcnn is None or self.facenet is None:
            print("Face models are not initialized")
            return "Not registered"

        frame = cv2.imread(image_path)
        if frame is None:
            print("Failed to read frame")
            return "Not registered"

        detection_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = await asyncio.to_thread(self.mtcnn.detect_faces, detection_frame)
        print(f"Found {len(faces)} faces in frame")

        for face in faces:
            x, y, w, h = face["box"]
            x, y = max(0, x), max(0, y)
            x2, y2 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)

            if x2 <= x or y2 <= y:
                continue

            extracted_face = frame[y:y2, x:x2]
            if extracted_face.size == 0:
                continue

            if len(extracted_face.shape) == 2:
                extracted_face = cv2.cvtColor(extracted_face, cv2.COLOR_GRAY2RGB)
            else:
                extracted_face = cv2.cvtColor(extracted_face, cv2.COLOR_BGR2RGB)

            image = cv2.resize(extracted_face, (160, 160))
            image = image.astype("float32") / 255.0
            image = np.expand_dims(image, axis=0)

            embedding = await asyncio.to_thread(lambda: self.facenet.embeddings(image)[0])

            print(f"Generated embedding, checking against {len(self.face_embedings)} stored embeddings")
            print(f"face embeddings: {len(self.face_embedings)}")
            print(f"Names: {self.face_names}")

            best_match_idx = None
            if len(self.face_embedings) > 0:
                known_embeddings = np.asarray(self.face_embedings, dtype=np.float32)
                current_embedding = np.asarray(embedding, dtype=np.float32)
                denominators = (
                    np.linalg.norm(known_embeddings, axis=1)
                    * np.linalg.norm(current_embedding)
                )
                similarities = np.divide(
                    known_embeddings @ current_embedding,
                    denominators,
                    out=np.zeros(len(known_embeddings), dtype=np.float32),
                    where=denominators != 0,
                )
                best_match_idx = np.argmax(similarities)
                best_similarity = similarities[best_match_idx]
            else:
                best_similarity = 0

            print(f"best similarity: {best_similarity} {best_match_idx}")

            if (
                best_match_idx is not None
                and best_similarity >= float(self.config["face_match_threshold"])
            ):
                self.username = self.face_names[best_match_idx]
                self.registration_state = True
                print(f"Recognized user: {self.username}")
                return self.username

        print("No matching face found")
        return "Not registered"

    async def handle_new_user_registration(self, username, saved_paths):
        print(f"Starting registration for {username} with {len(saved_paths)} photos")
        embeddings = []

        if self.mtcnn is None or self.facenet is None:
            print("Face models are not initialized")
            return False

        for image_path in saved_paths:
            print(f"Processing image: {image_path}")
            frame = cv2.imread(image_path)
            if frame is None:
                print(f"Failed to read image: {image_path}")
                continue

            detection_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = await asyncio.to_thread(self.mtcnn.detect_faces, detection_frame)
            print(f"Found {len(faces)} faces in image")

            if len(faces) == 0:
                continue

            for face in faces:
                x, y, w, h = face["box"]

                x1, y1 = max(x, 0), max(y, 0)
                x2, y2 = min(x + w, frame.shape[1]), min(y + h, frame.shape[0])

                if x2 <= x1 or y2 <= y1:
                    continue

                extracted_face = frame[y1:y2, x1:x2]

                if extracted_face.size == 0:
                    continue

                if len(extracted_face.shape) == 2:
                    extracted_face = cv2.cvtColor(extracted_face, cv2.COLOR_GRAY2RGB)
                else:
                    extracted_face = cv2.cvtColor(extracted_face, cv2.COLOR_BGR2RGB)

                image = cv2.resize(extracted_face, (160, 160))
                image = image.astype("float32") / 255.0
                image = np.expand_dims(image, axis=0)

                embedding = await asyncio.to_thread(lambda: self.facenet.embeddings(image)[0])
                embeddings.append(embedding)
                print("Generated embedding for face")

        print(f"Total embeddings generated: {len(embeddings)}")
        if len(embeddings) == 0:
            print("No valid faces found")
            return False

        avg_embedding = np.mean(embeddings, axis=0).tolist()

        json_data = load_face_encoding_json()
        json_data[username] = {"embedding": avg_embedding}
        self.username = username
        save_face_encoding_json(json_data)

        self.face_embedings, self.face_names, _ = load_face_encodings()
        print(f"User {username} registered successfully - saved to {FACE_ENCODINGS_PATH}")
        return True

    async def handle_video(self, fer, image_path):
        self.frame_count += 1

        detector = fer or self.fer
        if detector is None:
            return

        if self.frame_count % 5 == 0:
            frame = cv2.imread(image_path)
            if frame is None:
                return

            result = await asyncio.to_thread(detector.detect_emotions, frame)
            if result:
                face_data = max(result, key=lambda x: x["box"][2] * x["box"][3])
                emotions = face_data["emotions"]
                dominant_emotion = max(emotions, key=emotions.get)
                self.emotion_history.append(dominant_emotion)

                while len(self.emotion_history) > 50:
                    self.emotion_history.popleft()

                print(dominant_emotion)
