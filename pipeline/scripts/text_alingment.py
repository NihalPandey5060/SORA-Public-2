import time
import subprocess
import json
import wave
from pathlib import Path


def _audio_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate:
                return max(0.1, frames / float(rate))
    except Exception:
        pass
    return 1.0


def _fallback_alignment(audio_path: Path, text_path: Path, output_path: Path) -> None:
    lines = [
        line.strip()
        for line in text_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        lines = [""]

    duration = _audio_duration_seconds(audio_path)
    step = duration / len(lines)
    fragments = []

    for index, line in enumerate(lines):
        begin = index * step
        end = duration if index == len(lines) - 1 else (index + 1) * step
        fragments.append({
            "id": f"f{index + 1:04d}",
            "begin": f"{begin:.3f}",
            "end": f"{end:.3f}",
            "lines": [line],
        })

    output_path.write_text(
        json.dumps({"fragments": fragments}, indent=2),
        encoding="utf-8",
    )


def text_alignment_main(folder_path): 
    folder_path = Path(folder_path)
    audio = folder_path / "final_audio.wav"          # or "final_audio.wav", but be consistent
    text = folder_path / "llm_response.txt"
    output = folder_path / "alignment.json"

    if not audio.exists():
        raise FileNotFoundError(f"Missing audio file: {audio}")
    if not text.exists():
        raise FileNotFoundError(f"Missing transcript file: {text}")

    start = time.time()

    task = "task_language=eng|is_text_type=plain|os_task_file_format=json"

    cmd = [
        "python3", "-m", "aeneas.tools.execute_task",
        str(audio),
        str(text),
        task,
        str(output)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("[AENEAS ERROR]")
        print(result.stderr)
        print("[AENEAS FALLBACK] Using even text/audio alignment.")
        _fallback_alignment(audio, text, output)

    if not output.exists():
        print("[AENEAS FALLBACK] Alignment output missing. Using even text/audio alignment.")
        _fallback_alignment(audio, text, output)

    end = time.time()
    return end - start
