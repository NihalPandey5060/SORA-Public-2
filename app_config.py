import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_APP_CONFIG: Dict[str, Any] = {
    "persona_name": "Yardhouse",
    "system_prompt_base": (
        "You are a waiter at Yardhouse. Respond to the user query with the available "
        "details from the menu below. Give them a precise and helpful answer."
    ),
    "system_prompt_emotion": (
        "You are a waiter at Yardhouse. Respond to the user query with the available "
        "details from the menu and the current emotion of the user: {emotion}. "
        "Respond to the user with compassion."
    ),
    "system_prompt_user_emotion": (
        "You are a waiter at Yardhouse. Respond to user {username}'s query with the "
        "available details from the menu and the current emotion of the user: {emotion}. "
        "Respond to the user with compassion."
    ),
    "knowledge_base_path": "pipeline/menu.txt",
    "greeting_response": "Hi{name}! Welcome to Yardhouse. How can I help you today?",
    "llm_model": "llama-3.1-8b-instant",
    "tts_voice_id": "21m00Tcm4TlvDq8ikWAM",
    "tts_model": "eleven_flash_v2_5",
    "stt_language": "en",
    "face_match_threshold": 0.40,
}


def load_app_config() -> Dict[str, Any]:
    config = DEFAULT_APP_CONFIG.copy()

    for path in (Path("app_config.json"), Path("app_config.example.json")):
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as file:
            loaded_config = json.load(file)

        if isinstance(loaded_config, dict):
            config.update(loaded_config)

        break

    return config
