from fastapi import WebSocket
from fastapi.websockets import WebSocketState
import json 

# sends error messages to the client over WebSocket connections
class ErrorHandler: 
    @staticmethod
    async def send_error(ws: WebSocket, error_message: str, code: int = 400):
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_text(json.dumps({
                "type": "error",
                "payload": {
                    "code": code,
                    "message": error_message
                }
            }))
