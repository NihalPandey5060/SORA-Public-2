from typing import Optional

CLIENT_SESSION_IMPORT_ERROR: Optional[str] = None
ClientSessionClass = None

try:
  from pipeline.Client_services import CLientLLMSession as ClientSessionClass
  print(f"Successfully imported ClientSessionClass: {ClientSessionClass}")
except Exception as exc:
  CLIENT_SESSION_IMPORT_ERROR = f"{exc.__class__.__name__}: {exc}"
  print(f"Failed to import ClientSessionClass: {CLIENT_SESSION_IMPORT_ERROR}")


class FallbackClientSession:
  def __init__(self, client_id: str, unavailable_reason: Optional[str] = None):
    self.client_id = client_id
    self.unavailable_reason = unavailable_reason or "Avatar pipeline dependencies are unavailable."

  async def handle_text(self, text: str) -> str:
    return (
      "The backend is running, but the full avatar pipeline is not configured in this local environment yet. "
      "Text, voice, emotion, and face-recognition responses need the optional AI dependencies and API keys listed in the README."
    )

  async def handle_voice(self, pcm_audio):
    return None

  async def handle_registration(self, image_path):
    return "Not registered"

  async def handle_new_user_registration(self, username, saved_paths):
    return None

  async def handle_video(self, fer, image_path):
    return None


class Session_Manger:
  def __init__(self):
    self.active_connections = {}

  async def connect(self, session_id):
    if session_id not in self.active_connections.keys():
      if ClientSessionClass is None:
        self.active_connections[session_id] = FallbackClientSession(
          client_id=session_id,
          unavailable_reason=CLIENT_SESSION_IMPORT_ERROR,
        )
      else:
        try:
          self.active_connections[session_id] = ClientSessionClass(client_id=session_id)
        except Exception as exc:
          self.active_connections[session_id] = FallbackClientSession(
            client_id=session_id,
            unavailable_reason=f"{exc.__class__.__name__}: {exc}",
          )
    return self.active_connections[session_id]

  async def disconnect(self, session_id):
    removed_connection = self.active_connections.pop(session_id, None)
    return removed_connection
