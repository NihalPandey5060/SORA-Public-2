# Service_App_Bbackend (FastAPI + Vite React)

Short README documenting the integration between a FastAPI backend and a Vite/React frontend, plus Docker setup.

## Project overview

### Multimodal AI Avatar System

This repository contains the complete implementation of a **AI companion system** consisting of a **FastAPI backend** and a **React (Vite) frontend**. The system processes **image, audio, and text inputs** from users and generates responses using an **LLM**, which are then converted into **speech and avatar visemes** for interactive responses.


## #System Overview

The application allows users to interact through **multiple modalities**:

- **Image Input** – Used to detect the user's emotion using **Facial Emotion Recognition (FER)**.
- **Audio Input** – Users can ask questions using voice.
- **Text Input** – Users can directly type their queries.

Both **audio and text queries** are processed by the backend and sent to a **Large Language Model (LLM)** for response generation.

To improve efficiency, the system stores **previous chat responses**. If multiple users ask the same question, the system can retrieve the response from the stored history instead of recomputing it.

After the LLM generates a response:

1. The response is converted to **audio using Text-to-Speech (TTS)**.
2. **Visemes** are generated from the speech output.
3. The visemes are used to animate a **digital avatar** that delivers the response.


## Project Structure
├── main.py  # FastAPI application and API endpoints
├── db.py  # SQLite models and database session management
├── yardhouse.db # SQLite database file
|── pipeline
|   |──session_manger.py  # creates unique session id for each user 
|   |──client_services.py # contains the class that has all the processing (text,image and voice)
|   └──scripts
|       |──audio_generation.py 
|       |──build_vism_file.py
|       |──map_phonemes_to_visemes.py
|       |──phoneme_to_viseme.py
|       |──text_alignment.py
|       └──text_to_phoneme.py
├── client/ # Frontend application (Vite + React)
│ ├── src/
│ └── dist/ # Production build output
├── Dockerfile # Multi-stage build for frontend and backend
├── docker-compose.yml # Container orchestration with Redis
└── README.md

## Remaining

The generated outputs, such as **viseme files** and **audio responses**, are stored in the `media/output/` directory. For each chat interaction, a **unique UUID** is created, and a corresponding folder is generated:
media/output/<uuid>/

This directory contains all the generated artifacts for that specific query, including the **audio file**, **viseme data**, and other related outputs.

Additionally, the `media/output/` directory contains a file named: `question_result_path.json`


This file maintains a mapping between each **user question** and the **path to the directory** where its generated outputs (audio, visemes, etc.) are stored.  

By maintaining this mapping, the system can **reuse previously generated outputs** if the same question is asked again, avoiding redundant computation and improving response time.

## Quick contract (inputs/outputs)

- GET /menu
  - Returns: JSON array of menu items
  - Item shape: { id, category, name, price, description }
  - Source: SQLite `menu_items` table (ORM model `MenuItem` in `db.py`).

- WebSocket `/ws/media`
  - Purpose: Receive audio chunks and save them to disk.
  - Protocol: JSON text messages.
  - Message Format:
    ```json
    {
      "type": "audio_chunk",
      "payload": {
        "audio": {
          "data": "<base64_encoded_bytes>",
          "format": "opus",
          "sample_rate": 48000
        }scipy
      }
    }
    ```
  - Behavior: Decodes Base64 audio data and appends it to `media/audio/audio.pcm`.
  - Note: The current frontend implementation sends **WebM (Opus)** audio data. The saved file `audio.pcm` contains WebM binary data.

- WebSocket `/ws/connect`
  - Purpose: Handle client connection and session management.
  - Protocol: JSON text messages.
  - Message Format:
    ```json
    {
      "type": "connect",
      "token": "<optional_token>"
    }
    ```

**NOTE** 
 Ensure that the required **environment variables** are configured before running the project.

- The **`client/.env`** file should contain the environment variables required by **Vite**.
- The **`pipeline/.env`** file should include the necessary API keys, such as:
  - **ElevenLabs API Key**
  - **Groq API Key**

Make sure these `.env` files are properly set up so that the frontend and backend services can access the required configurations and external APIs. 

## Run (recommended: Docker Compose)

1. Ensure the ffmpeg is installed  
2. Ensure Docker and Docker Compose (or `docker compose`) are installed.
3. From the repository root run (Windows `cmd.exe`):

```cmd
docker compose up --build
```

This will:
- start a Redis container,
- build the frontend and Python image,
- run the FastAPI app on port 8000 (container binds host `8000:8000`).

Verify:
- Open `http://localhost:8000/menu` in your browser or run:

```cmd
curl http://localhost:8000/menu
```

- If static frontend served by container, visit `http://localhost:8000/` to see built frontend assets (depending on routing/setup).

## Run locally without Docker (development)

Backend:

```cmd
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```cmd
cd client
npm ci
npm run dev
```

By default Vite dev server runs on port 5173. Configure the frontend to call the backend at `http://localhost:8000` (or use a proxy in `client/vite.config.js`).

## Files of interest

- `main.py` — FastAPI app, websocket `/ws/media`, `GET /menu`, Redis caching on startup.
- `db.py` — SQLAlchemy models and `get_db()` dependency. Uses SQLite `yardhouse.db`.
- `Dockerfile` — multi-stage: builds frontend, then sets up Python runtime and copies `client/dist` into `static`.
- `docker-compose.yml` — defines `redis` and `app` services and mounts `yardhouse.db` + `media` into container.
- `client/` — Vite + React frontend (`client/package.json`, `client/src/`).
- `menu.json` — sample menu data (copied into container by Dockerfile).

## Verification steps

- GET /menu should return an array (possibly empty) consistent with the SQLite DB.
- Start Docker Compose and check Redis logs to ensure Redis is healthy. The app will fallback to no-caching if Redis isn't available.
- For WebSocket, use a client capable of sending JSON messages with Base64 encoded audio.
- Saved files will appear in `media/audio/audio.webm`.


## Screenshots

### Backend Implementation
![Backend Code](docs_imgs/backend_snapshot.png)
*The `audio_stream` WebSocket endpoint in `main.py` handling incoming audio chunks.*

### Frontend Demo
![Frontend Demo](docs_imgs/client_snapshot.png)
*The React frontend recording audio and sending Opus chunks via WebSockets, with the Network tab showing the JSON messages.*

### Server Logs
![Terminal Output](docs_imgs/apis_snapshot)
*Server terminal showing successful receipt and saving of audio chunks.*

## Final Commands 

Ensure the Docker service is running and the packages are proprely installed, then run the following commands to start the application:

### Installing dependencies for backend
active the virtual environment before executing the following commands
``` cmd
pip install -r requirements.txt
```
### Installing dependencies for frontend

``` cmd
cd client
npm install
```


### Start the docker container for redis and backend server


``` cmd
docker compose up -d
```

### Start the docker container for redis and backend server after changes in the backend


``` cmd
docker compose up -d --build
```
### Start the fastapi backend server

``` cmd
uvicorn main:app --reload 
``` 
### Start the frontend server

``` cmd 
cd client
npm run dev
```
## How to connect to the backend server from the frontend


- Go the following client folder and a .env file with the following info
  
  ```bash
	VITE_BACKEND_URL=https://18vz8r08zb3p4g-80.proxy.runpod.net/api
	VITE_WEBSOCKET_URL=wss://18vz8r08zb3p4g-80.proxy.runpod.net/ws
  ```

- Go the following path
	client > src > app.jsx

	#### Copy the important function are.

	- handleAddMessageToChat - To add the text message in the container
	- handleSendMessage -To send the message to the backend via web sockets
	- First useEffect ( to setup the WebSocket connection )
  - const WS_URL = import.meta.env.VITE_WEBSOCKET_URL + "/media"

- Refer App.jsx if you encounter any error or ask me for help
