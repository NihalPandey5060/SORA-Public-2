import subprocess
import os 
import base64
import datetime


def webm_to_mp3(base64_data : str):
    print("Converting webm to mp3...")
    webm_bytes = base64.b64decode(base64_data)
    current_time = datetime.datetime.now()
    temp_webm_path = os.path.join("tmp", "webm", f"temp_audio_{current_time.timestamp()}.webm")
    temp_mp3_path = os.path.join("tmp", "mp3", f"temp_audio_{current_time.timestamp()}.mp3")

    with open(temp_webm_path, "wb") as webm_file:
        webm_file.write(webm_bytes)
    
    subprocess.run(
            [
                "ffmpeg",
                "-y",                  # overwrite
                "-i", temp_webm_path,  # input WebM
                "-vn",                 # ignore video
                "-ar", "48000",        # match WebM sample rate
                "-b:a", "128k",        # output bitrate
                temp_mp3_path          # output MP3
            ],
            check=True,

            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return temp_mp3_path
