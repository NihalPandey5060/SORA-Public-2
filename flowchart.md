```mermaid
flowchart TD

%% =====================================
%% COLOR DEFINITIONS
%% =====================================

classDef startEnd fill:#4CAF50,stroke:#1B5E20,color:#fff,stroke-width:3px;
classDef process fill:#42A5F5,stroke:#0D47A1,color:#fff,stroke-width:2px;
classDef decision fill:#FFB300,stroke:#E65100,color:#000,stroke-width:3px;
classDef database fill:#AB47BC,stroke:#4A148C,color:#fff,stroke-width:2px;
classDef success fill:#26A69A,stroke:#004D40,color:#fff,stroke-width:2px;
classDef warning fill:#EF5350,stroke:#B71C1C,color:#fff,stroke-width:2px;
classDef menu fill:#5C6BC0,stroke:#1A237E,color:#fff,stroke-width:2px;
classDef guest fill:#8D6E63,stroke:#3E2723,color:#fff,stroke-width:2px;

%% =====================================
%% MAIN SYSTEM FLOW
%% =====================================

A([Frontend Starts]):::startEnd

B[/Open WebSocket to /ws/media/]:::process

C[Send init message\nwith session_id]:::process

D[Backend creates\nClientSession]:::process

E([User starts\nvideo recording]):::startEnd

F[Frontend sends\nvideo_frame images]:::process

G[(Backend saves frame\nto media/video)]:::database

H[MTCNN detects face]:::process

I[FaceNet creates\n512-value embedding]:::process

J{Match found in\nface_encodings.json?}:::decision

%% =====================================
%% REGISTERED USER FLOW
%% =====================================

K([Welcome User Successfully]):::success

L[AI Assistant greets user\nand explains available options]:::menu

M{Select Menu Option}:::decision

N([Start Chat Session]):::menu

O([View Dashboard]):::menu

P([Access Features]):::menu

%% =====================================
%% UNREGISTERED USER FLOW
%% =====================================

Q([Face Not Recognized]):::warning

R{Choose an Option}:::decision

%% Registration Path
S[User enters\nname + 5 photos]:::process

T[(Backend saves photos)]:::database

U[Creates FaceNet embedding]:::process

V[(Updates\nface_encodings.json)]:::database

W([User Registered Successfully]):::success

X([Future Login\nRecognized Automatically]):::success

%% Guest Path
Y([Continue Without Registration]):::guest

Z[Limited Guest Access\nTemporary Session Created]:::guest

AA([Guest can chat\nwith restricted features]):::guest

%% =====================================
%% CONNECTIONS
%% =====================================

A --> B
B --> C
C --> D
D --> E
E --> F
F --> G
G --> H
H --> I
I --> J

%% Existing User Flow
J -->|YES| K
K --> L
L --> M

M --> N
M --> O
M --> P

%% New User Flow
J -->|NO| Q
Q --> R

%% Registration Branch
R -->|Register| S
S --> T
T --> U
U --> V
V --> W
W --> X

%% Guest Branch
R -->|Continue as Guest| Y
Y --> Z
Z --> AA

%% Future Login Loop
X -. Future Login .-> J
```

# 📦 Project Setup

## 1️⃣ Create Virtual Environment

```bash
python -m venv .venv
```

---

## 2️⃣ Activate Virtual Environment

### Windows

```bash
.\.venv\Scripts\activate
```

---

## 3️⃣ Install Required Dependencies

```bash
python -m pip install -r requirements-app.txt
```

# 🔑 Environment Variables

Create a `.env` file in the root directory:

```env
GROQ_API_KEY=your_groq_key
Elevens_lab_key=your_elevenlabs_key
```

# ▶️ Running the Project

## 🚀 Start Backend

```bash
cd d:\gpu-avatar-backend-pipeline-liva-x1
.\.venv\Scripts\python.exe main.py
```

## 💻 Start Frontend

```bash
cd d:\gpu-avatar-backend-pipeline-liva-x1\client
npm run dev
```

# 📌 Requirements

- Python 3.10 or above
- Node.js installed
- npm installed

# ⚠️ Important Notes

- Start backend before frontend
- Ensure `.env` is configured
- Install all dependencies successfully
