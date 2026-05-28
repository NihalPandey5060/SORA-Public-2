import time
import subprocess
from pathlib import Path

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
        raise RuntimeError("Aeneas alignment failed")

    if not output.exists():
        raise FileNotFoundError(f"Aeneas did not create {output}")

    end = time.time()
    return end - start
