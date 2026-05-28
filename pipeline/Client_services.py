import asyncio 
import numpy as np 
from scipy.signal import resample 
import webrtcvad 
import whisper 
from groq import Groq
import os 
from sentence_transformers import SentenceTransformer
import faiss 
from typing import List, Dict, Optional
import os 
import json 
import uuid
from pipeline.scripts.audio_generation import audio_generation_main 
from pipeline.scripts.text_to_phoneme import text_to_phoneme_main 
from pipeline.scripts.text_alingment import text_alignment_main
from pipeline.scripts.phoneme_to_viseme import phoneme_to_viseme 
from pipeline.scripts.map_phonemes_to_visemes import mappinf_phonems_to_vismes 
from pipeline.scripts.build_vism_file import build_vism_file 
from dotenv import load_dotenv 
import cv2
try:
    from fer import FER
except Exception as exc:
    FER = None
    print(f"FER unavailable in Client_services: {exc.__class__.__name__}: {exc}")
from mtcnn import MTCNN
from keras_facenet import FaceNet
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path
load_dotenv()

path = "media/output"
# os.makedirs(path,exist_ok=True)

json_path = path + "/question_result_path.json"
MEDIA_DIR = Path("media")
VERIFICATION_DIR = MEDIA_DIR / "verification"
face_encodings_path = VERIFICATION_DIR / "face_encodings.json"
FACE_EMBEDDING_SIZE = 512
MENU_EMBEDDER = None
MENU_INDEX = None
MENU_CHUNKS = None

def prev_ans(filepath=json_path):
    """Load previously stored question -> folder_path mapping"""
    if not os.path.exists(path):
        os.makedirs(path)

    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as file:
                return json.load(file)
        except Exception:
            return {}
    else:
        # Create empty json file first time
        with open(filepath, "w") as file:
            json.dump({}, file)
        return {}

def save_prev_ans(question: str, folder_path: str, filepath=json_path):
    """Save question -> folder mapping"""
    if os.path.exists(filepath):
        with open(filepath, "r") as file:
            data = json.load(file)
    else:
        data = {}

    data[question] = folder_path

    with open(filepath, "w") as file:
        json.dump(data, file, indent=2)


def load_and_index_menu(filepath="pipeline/menu.txt"):
    """Load and index menu items for semantic search"""
    global MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS
    if MENU_EMBEDDER is not None and MENU_INDEX is not None and MENU_CHUNKS is not None:
        return MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS

    index = faiss.IndexFlatL2(768) 
    embedder = SentenceTransformer("all-mpnet-base-v2")
    
    if not os.path.exists(filepath): 
        print(f"Warning: Menu file {filepath} not found")
        return index, []
    
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    
    menu_chunks = [c.strip() for c in text.split("\n") if c.strip()]
    
    if menu_chunks:
        embeddings = embedder.encode(menu_chunks, convert_to_numpy=True).astype("float32")
        index.add(np.array(embeddings))
    
    MENU_EMBEDDER = embedder
    MENU_INDEX = index
    MENU_CHUNKS = menu_chunks
    return MENU_EMBEDDER, MENU_INDEX, MENU_CHUNKS

def is_avatar_pipeline_enabled():
    return os.getenv("ENABLE_AVATAR_PIPELINE", "0").lower() in {"1", "true", "yes", "on"}

def load_face_encoding_json(filename=face_encodings_path):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not read face encodings from {filename}: {exc}")
        return {}

def save_face_encoding_json(json_data, filename=face_encodings_path):
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    tmp_filename = Path(f"{filename}.tmp")
    with open(tmp_filename, "w") as file:
        json.dump(json_data, file, indent=4)
    os.replace(tmp_filename, filename)

def load_face_encodings(filename=face_encodings_path):
    """Load face encodings from JSON file"""
    json_data = load_face_encoding_json(filename)
    if not json_data:
        return np.array([]), [], {}
    
    face_names = []
    known_embeddings = []
    
    for name, data in json_data.items():
        if not isinstance(data, dict) or 'embedding' not in data:
            continue

        embedding = np.array(data['embedding'], dtype=np.float32)
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
    def __init__(self, client_id): 
        self.client_id = client_id 
        
        # Get API key from environment
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        
        self.llm_client = Groq(api_key=api_key) 
        self.vad = webrtcvad.Vad(2) 
        self.stt_model = None
        
        # Initialize speech buffer - THIS WAS MISSING
        self.speech_buffer: List[np.ndarray] = []
        
        self.silence_count = 0 
        
        # FIX: Use consistent naming - frame_30MS corresponds to 30ms at 48kHz
        # 48000 Hz * 0.030 sec = 1440 samples
        self.FRAME_30MS = 1440 
        
        self.embedder, self.index, self.menu_chunks = load_and_index_menu() 
        self.chat_history: List[Dict[str, str]] = []
        self.lock = asyncio.Lock() 

        self.prev_data = prev_ans()
        self.emotion_history=[]
        self.frame_count = 0

        self.registration_state=False
        self.face_embedings,self.face_names,_ = load_face_encodings()
        self.fer = FER() if FER is not None else None
        self.facenet = FaceNet()
        self.mtcnn = MTCNN()
        self.username = ""
    
    async def text_voice_phoneme_generation(self,folder_path): 
        ''' save the folder in the following formate 
        uuid 
            1.llm_response.txt 
            2.final_audio.wav
            3.text_phonemes.txt
            4.viseme_timeline.json
            5.chunk contains the chunk audio part
            6.alignment.json
            7.output.vsim.json 
        '''
        try:
            loop = asyncio.get_running_loop()
            audio_time = await loop.run_in_executor(None,audio_generation_main,folder_path)
            phoneme_time = await loop.run_in_executor(None,text_to_phoneme_main,folder_path) 
            alignemnt_time = await loop.run_in_executor(None,text_alignment_main,folder_path)
            mapping_time = await loop.run_in_executor(None,mappinf_phonems_to_vismes,folder_path) 
            build_time = await loop.run_in_executor(None,build_vism_file,folder_path)
        except Exception as e:
            print(f"Avatar audio/viseme generation skipped: {e}")

    def search_menu(self, user_query: str, k: int) -> str:
        """Search menu using semantic similarity"""
        if not self.menu_chunks:
            return "Menu information not available."
        
        query_embedding = self.embedder.encode(
            [user_query],
            convert_to_numpy=True
        ).astype("float32")
        
        # Ensure k doesn't exceed available chunks
        k = min(k, len(self.menu_chunks))
        
        distance, indices = self.index.search(query_embedding, k) 
        results = [self.menu_chunks[i] for i in indices[0]]  # FIX: indices is 2D array
        results_text = "\n".join(results)
        return results_text 
    
    async def ask_llm(self, user_query: str) -> str:
        """Send query to LLM and get response"""
        llm_response = None
        normalized_query = user_query.strip().lower().strip("'\".!?")
        if normalized_query in {"hi", "hello", "hey", "hii", "hiii"}:
            name = f" {self.username}" if self.username else ""
            return f"Hi{name}! Welcome to Yardhouse. How can I help you today?"

        self.prev_data = prev_ans()
        async with self.lock: 
            self.chat_history.append({"role": "user", "content": user_query})
            if user_query in self.prev_data:
                folder_path = self.prev_data[user_query]
                llm_response_path = os.path.join(folder_path, "llm_response.txt")

                if os.path.exists(llm_response_path):
                    with open(llm_response_path, "r") as file:
                        llm_response = file.read()
                    self.chat_history.append({"role": "assistant", "content": llm_response})
                    print("Loaded response from cache")
                    return llm_response 
            
            menu_content = self.search_menu(user_query=user_query, k=6) 
            system_prompt = f'''You are a waiter at Yardhouse. Respond to the user query with the available 
details from the menu below. Give them a precise and helpful answer.

Menu Information:
{menu_content}
'''
            if self.emotion_history:
                system_prompt=f'''Your are a waiter at yardhouse. Respond to the user query with the available
                details from the menu and this the current emotion of the user:{self.emotion_history[-1]}. So 
                respond to the user with compaction. 
                Menu Information: {menu_content}'''
            
            if self.username and self.emotion_history: 
                system_prompt=f'''Your are a waiter at yardhouse. Respond to the user name; {self.username} query with the available
                details from the menu and this the current emotion of the user:{self.emotion_history[-1]}. So 
                respond to the user with compaction. 
                Menu Information: {menu_content}'''
            
            history = [{"role": "system", "content": system_prompt}]
            
            for msg in self.chat_history: 
                if msg["role"] == "user" or msg["role"] == "assistant":
                    history.append(msg) 
            
            try:
                completion = self.llm_client.chat.completions.create( 
                    model="llama-3.1-8b-instant", 
                    messages=history,
                    temperature=0.6
                )
                
                reply = completion.choices[0].message.content.strip()
                self.chat_history.append({"role": "assistant", "content": reply})
                # update the json file 
                folder_name = str(uuid.uuid4())
                folder_path = os.path.join(path, folder_name)
                os.makedirs(folder_path, exist_ok=True)

                llm_response_file_path = os.path.join(folder_path, "llm_response.txt")
                with open(llm_response_file_path, "w") as f:
                    f.write(reply)
                
                save_prev_ans(user_query, folder_path) 
                if is_avatar_pipeline_enabled():
                    asyncio.create_task(self.text_voice_phoneme_generation(folder_path=folder_path))
                return reply 
            except Exception as e:
                error_msg = f"Error getting LLM response: {str(e)}"
                print(error_msg)
                return "I apologize, I'm having trouble processing your request right now."
                
    
    async def handle_text(self, text: str) -> str:
        """Handle text input from user"""
        try:
            return await self.ask_llm(user_query=text)
        except Exception as e:
            print(f"Error in handle_text: {e}")
            return "Sorry, I encountered an error processing your message."
    
    async def _transcribe_speech(self) -> str:
        """Transcribe buffered speech to text"""
        try:
            if not self.speech_buffer:
                return ""

            if self.stt_model is None:
                loop = asyncio.get_running_loop()
                self.stt_model = await loop.run_in_executor(None, whisper.load_model, "base")
            
            # Concatenate all audio chunks
            audio_48 = np.concatenate(self.speech_buffer).astype(np.float32)
            
            # Resample from 48kHz to 16kHz for Whisper
            new_len = int(len(audio_48) * 16000 / 48000)
            audio_16 = resample(audio_48, new_len) / 32768.0
            
            # Run transcription in executor to avoid blocking
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.stt_model.transcribe(
                    audio_16, language="en", fp16=False
                )
            )
            
            return result["text"].strip()
            
        except Exception as e:
            print(f"Error in transcription: {e}")
            return ""
    
    async def handle_voice(self, pcm_audio: np.ndarray) -> Optional[Dict[str, str]]:
        """Handle voice input with VAD and transcription"""
        try:
            is_speech = False 
            
            # Check if audio contains speech
            for i in range(0, len(pcm_audio), self.FRAME_30MS):
                chunk = pcm_audio[i:i + self.FRAME_30MS]
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
                return None
            
            # Increment silence counter
            self.silence_count += 1
            
            # Process speech if we have enough silence
            if self.silence_count > 3 and self.speech_buffer:
                text = await self._transcribe_speech()
                self.speech_buffer = []
                self.silence_count = 0
                
                if text:
                    # FIX: Use ask_llm instead of _ask_llm
                    reply = await self.ask_llm(text)
                    return {"User_query": text, "llm_response": reply}
            
            return None
            
        except Exception as e:
            print(f"Error in handle_voice: {e}")
            # Reset state on error
            self.speech_buffer = []
            self.silence_count = 0
            return None
        
    async def handle_registration(self,image_path): 
        print(f"Checking registration for image: {image_path}")
        frame = cv2.imread(image_path)
        if frame is None:
            print("Failed to read frame")
            return "Not registered"
            
        detection_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = self.mtcnn.detect_faces(detection_frame)
        print(f"Found {len(faces)} faces in frame")
        
        for face in faces:
            x, y, w, h = face['box']
            x, y = max(0, x), max(0, y)
            x2, y2 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
            
            if x2 <= x or y2 <= y:
                continue
            
            extracted_face = frame[y:y2, x:x2]
            if extracted_face.size == 0:
                continue

            # image = cv2.resize(extracted_face, (160, 160))
            # image = np.expand_dims(image, axis=0)
            if len(extracted_face.shape) == 2:
                extracted_face = cv2.cvtColor(extracted_face, cv2.COLOR_GRAY2RGB)
            else:
                extracted_face = cv2.cvtColor(extracted_face, cv2.COLOR_BGR2RGB)

            # ✅ Resize
            image = cv2.resize(extracted_face, (160, 160))

            # ✅ Normalize (important for FaceNet)
            image = image.astype('float32') / 255.0

            # ✅ Add batch dimension
            image = np.expand_dims(image, axis=0)                
            embedding = self.facenet.embeddings(image)[0]
            print(f"Generated embedding, checking against {len(self.face_embedings)} stored embeddings")
            print(f" face embedings : {len(self.face_embedings)}")
            print(f"Names : {self.face_names}")
            best_match_idx = None
            if len(self.face_embedings) > 0:
                similarities = cosine_similarity([embedding], self.face_embedings)[0]
                best_match_idx = np.argmax(similarities)
                best_similarity = similarities[best_match_idx]
            else:
                best_similarity = 0
            print(f"best similarity : {best_similarity} {best_match_idx}")
            if best_match_idx is not None and best_similarity >= 0.40: 
                self.username = self.face_names[best_match_idx] 
                self.registration_state=True
                print(f"Recognized user: {self.username}")
                return self.username
        print("No matching face found")
        return "Not registered"
        
    async def handle_new_user_registration(self, username, saved_paths):
        print(f"Starting registration for {username} with {len(saved_paths)} photos")
        embeddings = []

        for image_path in saved_paths:
            print(f"Processing image: {image_path}")
            frame = cv2.imread(image_path)
            if frame is None:
                print(f"Failed to read image: {image_path}")
                continue

            detection_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = self.mtcnn.detect_faces(detection_frame)
            print(f"Found {len(faces)} faces in image")

            if len(faces) == 0:
                continue

            for face in faces:
                x, y, w, h = face['box']

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
                image = image.astype('float32') / 255.0
                image = np.expand_dims(image, axis=0)

                embedding = self.facenet.embeddings(image)[0]
                embeddings.append(embedding)
                print(f"Generated embedding for face")

        print(f"Total embeddings generated: {len(embeddings)}")
        if len(embeddings) == 0:
            print("No valid faces found")
            return False

        avg_embedding = np.mean(embeddings, axis=0)
        avg_embedding = avg_embedding.tolist()

        json_data = load_face_encoding_json()

        json_data[username] = {
            "embedding": avg_embedding
        }
        self.username = username
        save_face_encoding_json(json_data)

        self.face_embedings, self.face_names, _ = load_face_encodings()
        print(f"User {username} registered successfully - saved to {face_encodings_path}")
        return True

    async def handle_video(self,fer,image_path):
        self.frame_count+=1
        if self.frame_count%5==0:
            frame = cv2.imread(image_path)
            result = fer.detect_emotions(frame)
            if result:
                face_data = max(result, key=lambda x: x["box"][2] * x["box"][3])
                emotions = face_data["emotions"]
                dominant_emotion = max(emotions, key=emotions.get)
                self.emotion_history.append(dominant_emotion)
                print(dominant_emotion)
