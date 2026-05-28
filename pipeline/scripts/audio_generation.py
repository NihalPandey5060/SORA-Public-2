import os
import io
import sys
import json
from pathlib import Path
from pydub import AudioSegment
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from elevenlabs import ElevenLabs  #
from dotenv import load_dotenv 
import requests  

load_dotenv() 
ELEVENLABS_API_KEY = os.getenv("Elevens_lab_key")

VOICE_NAME = "Rachel (American)"

ELEVENLABS_VOICE_OPTIONS = {
    "Rachel (American)": "21m00Tcm4TlvDq8ikWAM",
    "Adam (American-Deep)": "pNInz6obpgDQGcFmaJgB",
    "Matilda (American-Warm)": "XrExE9yKIg1WjnnlVkGX",
    "Grace (American-Southern)": "oWAxZDx7w5VEj9dCyTzz",
    "Jessica (American-Young)": "cgSgspJ2msm6clMCkdW9",
    "Dave (British)": "CYw3kZ02Hs0563khs1Fj",
    "George (British-Posh)": "JBFqnCBsd6RMkjVDRZzb",
    "Fin (Irish)": "D38z5RcWu1voky8WS1ja",
    "Callum (Scottish)": "N2lVS1w4EtoT3dr4eOWO",
    "Charlie (Australian)": "IKne3meq5aSn9XLyUdCD",
    "Aria (Indian-English)": "9BWtsMINqrJLrRacOk9x",
    "Amara (African-English)": "MF3mGyEYCl7XYWbV9V6O",
    "Yuki (Japanese-English)": "VR6AewLTigWG4xSOukaG",
    "Pierre (French-Accented)": "5Q0t7uMcjvnagumLfvZi",
    "Sofia (Spanish-Accented)": "ThT5KcBeYPX3keUQqHPh"
}

ELEVENLABS_TTS_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

N_CHUNKS = 6

MAX_THREADS = min(8, max(2, cpu_count() * 2))

DEFAULT_MODEL_ID = "eleven_flash_v2_5"  


def chunk_text_equally(full_text: str, n_chunks: int = N_CHUNKS) -> list:
    """Split full_text into n_chunks as equally as possible by character count.
    Attempt to split at whitespace near boundaries."""
    if not full_text:
        return [""] * n_chunks
    L = len(full_text)
    chunks = []
    prev = 0
    for i in range(n_chunks):
        if i == n_chunks - 1:
            chunk = full_text[prev:]
            chunks.append(chunk)
            break
        target = round((i + 1) * L / n_chunks)
        back_limit = max(prev, target - 200)
        forward_limit = min(L, target + 200)

        split_pos = -1
        segment = full_text[prev:target + 1]
        r = segment.rfind(" ")
        if r != -1:
            split_pos = prev + r
        else:
            forward_segment = full_text[target:forward_limit]
            f = forward_segment.find(" ")
            if f != -1:
                split_pos = target + f
            else:
                split_pos = target

        if split_pos <= prev:
            remaining = L - prev
            split_pos = prev + max(1, remaining // (n_chunks - i))

        chunk = full_text[prev:split_pos].strip()
        chunks.append(chunk)
        prev = split_pos
    while len(chunks) < n_chunks:
        chunks.append("")
    return chunks


def generate_audio_elevenlabs_using_sdk(text: str, voice_id: str, model_id: str = DEFAULT_MODEL_ID) -> bytes:
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio_iterable = client.text_to_speech.convert(
        voice_id=voice_id,
        output_format="mp3_44100_128",
        text=text,
        model_id=model_id
    )
    out = io.BytesIO()
    for chunk in audio_iterable:
        out.write(chunk)
    return out.getvalue()


def generate_audio_elevenlabs_using_http(text: str, voice_id: str, model_id: str = DEFAULT_MODEL_ID) -> bytes:
    url = ELEVENLABS_TTS_URL_TEMPLATE.format(voice_id=voice_id)
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg, audio/wav, application/octet-stream"
    }
    payload = {
        "text": text,
        "model": model_id
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.content


def generate_chunk_wav(chunk_index: int, chunk_text: str, chunk_wav_path: Path, voice_id: str, model_id: str = DEFAULT_MODEL_ID) -> tuple[int, bool, str]:
    if not chunk_text.strip():
        return (chunk_index, False, "empty")

    try:
        mp3_bytes = generate_audio_elevenlabs_using_sdk(chunk_text, voice_id, model_id=model_id)
    except Exception as e:
        return (chunk_index, False, f"tts_request_failed: {e}")

    tmp_mp3_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
            tmp_mp3.write(mp3_bytes)
            tmp_mp3_path = Path(tmp_mp3.name)

        audio_seg = AudioSegment.from_mp3(tmp_mp3_path.as_posix())
        chunk_wav_path.parent.mkdir(parents=True, exist_ok=True)
        audio_seg.export(chunk_wav_path.as_posix(), format="wav")
        return (chunk_index, True, "")
    except Exception as e:
        return (chunk_index, False, f"mp3_to_wav_failed: {e}")
    finally:
        if tmp_mp3_path is not None:
            try:
                tmp_mp3_path.unlink(missing_ok=True)
            except Exception:
                pass


def merge_chunk_wavs(chunk_wav_paths: list[Path], out_path: Path) -> bool:
    combined = None
    for p in chunk_wav_paths:
        if not p.exists() or p.stat().st_size == 0:
            continue
        seg = AudioSegment.from_file(p.as_posix())
        combined = seg if combined is None else (combined + seg)

    if combined is None:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_path.as_posix(), format="wav")
    return True


def audio_generation_main(folder_path):
    start_time = time.time() 
    folder_path = Path(folder_path)
    file_path = folder_path / 'llm_response.txt'  
    with open(file_path,'r') as f: 
        AI_response = f.read() 

    AI_response = AI_response.replace('\n',' ') 

    if ELEVENLABS_API_KEY is None:
        print("[ERROR] set ELEVENLABS_API_KEY.", file=sys.stderr)
        return
    
    voice_id = ELEVENLABS_VOICE_OPTIONS.get(VOICE_NAME)
    if voice_id is None:
        print(f"[WARN] voice '{VOICE_NAME}' not found in options. Using first available voice.", file=sys.stderr)
        voice_id = next(iter(ELEVENLABS_VOICE_OPTIONS.values())) 

    chunks = chunk_text_equally(AI_response, n_chunks=N_CHUNKS)

    for i, c in enumerate(chunks):
        print(f"Chunk {i+1}/{N_CHUNKS}: {len(c)} chars")

    CHUNK_DIRS = folder_path / 'chunks' 
    CHUNK_DIRS.mkdir(parents=True, exist_ok=True) 

    chunk_paths = [CHUNK_DIRS / f"chunk_{i:02d}.wav" for i in range(len(chunks))]

    jobs = []
    for i, c in enumerate(chunks):
        if c.strip():
            jobs.append((i, c, chunk_paths[i]))

    if not jobs:
        print("[INFO] No non-empty chunks to generate. Exiting.")
        return

    max_workers = min(MAX_THREADS, len(jobs))
    print(f"[INFO] Generating {len(jobs)} chunks in parallel using {max_workers} threads...")

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        future_to_idx = {
            exe.submit(generate_chunk_wav, idx, text, path, voice_id, DEFAULT_MODEL_ID): idx
            for idx, text, path in jobs
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                chunk_index, ok, err = fut.result()
                results[chunk_index] = (ok, err)
                if ok:
                    print(f"[DONE] chunk {chunk_index+1} generated successfully.")
                else:
                    print(f"[FAIL] chunk {chunk_index+1} - {err}")
            except Exception as e:
                results[idx] = (False, f"exception: {e}")
                print(f"[EXC] chunk {idx+1} raised exception: {e}")

    ok_count = sum(1 for v in results.values() if v[0])
    fail_count = sum(1 for v in results.values() if not v[0])
    print(f"[SUMMARY] {ok_count} succeeded, {fail_count} failed.")

    merge_paths = [p for i, p in enumerate(chunk_paths) if results.get(i, (False,))[0]]

    print("[MERGE] Combining chunk WAVs into final file...") 

    FINAL_OUTPUT_WAV = folder_path / 'final_audio.wav'
    merged_ok = merge_chunk_wavs(merge_paths, FINAL_OUTPUT_WAV)
    if merged_ok:
        print(f"[DONE] Final merged WAV: {FINAL_OUTPUT_WAV}")
    else:
        print("[ERROR] No chunks produced or merge failed.", file=sys.stderr)

    end_time = time.time()
    return end_time - start_time
