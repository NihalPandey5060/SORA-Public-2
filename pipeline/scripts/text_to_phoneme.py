import json
import os
import subprocess
import time
from pathlib import Path
from multiprocessing import Pool, cpu_count
from functools import partial
from tqdm import tqdm

# BASE = Path(__file__).resolve().parents[1]
# INPUT_PATH = BASE / "input" / "transcript.txt"
# OUTPUT_PATH = BASE / "output" / "text_phonemes.txt"
# CACHE_PATH = BASE / "output" / "phoneme_cache.json"
# LOG_PATH = BASE / "output" / "run_times.log"
CACHE_PATH = Path("/home/selvan/soraminds/gpu-avatar-backend-pipeline-audio_encoder/vardhan/gpu-avatar-backend-pipeline/media/output") / "phoneme_cache.json"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True) 

ESPEAK_BIN = "/usr/bin/espeak-ng"

WORKERS = int(os.environ.get("PHONEME_WORKERS", cpu_count()))

ESPEAK_CMD = [ESPEAK_BIN, "--ipa", "-q", "--stdout"]  # --stdout prints phonemes to stdout

def espeak_phonemize(text: str) -> str:
    try:
        proc = subprocess.run(
            ESPEAK_CMD + [text],
            capture_output=True,
            text=True,
            shell=False,
            timeout=10,
            encoding="utf-8",
            errors="ignore"
        )
        out = (proc.stdout or "").replace("\r", " ").replace("\n", " ").strip()
        if not out and proc.stderr:
            out = proc.stderr.strip()
        return out
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        print(f"[WARN] espeak failed on: {text[:30]}... ({e})")
        return ""


def worker(idx_line):
    idx, line = idx_line
    line_key = line.strip()
    if not line_key:
        return (idx, line, "")
    phon = espeak_phonemize(line_key)
    return (idx, line, phon)

def text_to_phoneme_main(folder_path):
    start_total = time.time() 
    folder_path = Path(folder_path) 
    
    INPUT_PATH = folder_path / 'llm_response.txt' 
    OUTPUT_PATH = folder_path / 'text_phonemes.txt' 
    LOG_PATH = folder_path / "run_times.log"    
    # BASE.mkdir(parents=True, exist_ok=True)
    # (BASE / "output").mkdir(parents=True, exist_ok=True)

    with INPUT_PATH.open("r", encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f]

    if CACHE_PATH.exists():
        try:
            with CACHE_PATH.open("r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    else:
        cache = {}

    indexed = list(enumerate(lines))

    need = [(i, text) for i, text in indexed if text.strip() and text not in cache]

    if not need:
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            for ln in lines:
                phon = cache.get(ln, "")
                f.write(phon + "\n")
        end_total = time.time()
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(f"Text→Phonemes (cached): {end_total - start_total:.3f} seconds\n")
        print("All lines retrieved from cache. Done.")
        return

    pool_size = min(WORKERS, max(1, len(need)))
    print(f"Workers: {pool_size}; Lines total: {len(lines)}; To compute: {len(need)}")
    with Pool(pool_size) as p:
        for idx, line, phon in tqdm(p.imap_unordered(worker, need), total=len(need), desc="phonemize"):
            cache[line] = phon

    tmp_cache = CACHE_PATH.with_suffix(".json.tmp")
    with tmp_cache.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    tmp_cache.replace(CACHE_PATH)

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(cache.get(ln, "") + "\n")

    end_total = time.time()
    elapsed = end_total - start_total
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"Text→Phonemes: {elapsed:.3f} seconds (workers={pool_size})\n")
    return elapsed

