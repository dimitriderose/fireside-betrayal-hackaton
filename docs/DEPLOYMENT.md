# Fireside: Betrayal — Deployment Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| npm | 9+ | Frontend package manager |
| Google Cloud SDK (`gcloud`) | Latest | GCP services + deployment |
| Docker | 24+ | Container builds (production) |
| Terraform | 1.5+ | Infrastructure as code (optional, see Part 5) |
| Git | 2.x | Source control |

### GCP Services Required

| Service | Purpose | Free Tier? |
|---------|---------|------------|
| **Gemini API** | Narrator voice (native-audio), Traitor strategy (flash), TTS previews | Yes — generous free tier |
| **Cloud Firestore** | Real-time game state, player data, strategy intelligence | Yes — 1 GiB free |
| **Cloud Run** | Backend hosting (production) | Yes — 2M requests/month |
| **Cloud Build** | CI/CD pipeline (production) | Yes — 120 build-min/day |

---

## Part 1: Local Development

### 1.1 Clone the Repo

```bash
git clone https://github.com/dimitriderose/fireside-betrayal-hackaton.git
cd fireside-betrayal-hackaton
```

### 1.2 Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

**Dependencies installed:**
- `fastapi==0.109.0` + `uvicorn[standard]==0.27.0` — ASGI web framework
- `websockets==12.0` — Real-time game connections
- `google-cloud-firestore==2.14.0` — Firestore client
- `google-genai>=1.0.0` — Gemini API (narrator, traitor, TTS)
- `python-dotenv==1.0.0` — Environment variable loading
- `pydantic==2.5.3` + `pydantic-settings==2.1.0` — Settings management
- `httpx==0.26.0` — Async HTTP client

### 1.3 Environment Variables

```bash
cp .env.example .env
```

Edit `backend/.env`:

```env
# === REQUIRED ===
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GEMINI_API_KEY=your-gemini-api-key

# === AUTHENTICATION (pick one) ===
# Option A: Service account key file (local dev)
GOOGLE_APPLICATION_CREDENTIALS=./service-account.json

# Option B: ADC (if you've run `gcloud auth application-default login`)
# Leave GOOGLE_APPLICATION_CREDENTIALS empty

# === OPTIONAL ===
FIRESTORE_EMULATOR_HOST=          # Set to localhost:8080 for emulator
NARRATOR_MODEL=gemini-2.5-flash-native-audio-preview-12-2025
TRAITOR_MODEL=gemini-2.5-flash
NARRATOR_VOICE=Charon
DEBUG=true
```

**Getting credentials:**

1. **Gemini API Key:** Go to [Google AI Studio](https://aistudio.google.com/apikey) → Create API Key
2. **GCP Project:** `gcloud projects create fireside-betrayal` (or use existing)
3. **Service Account:**
   ```bash
   gcloud iam service-accounts create fireside-backend
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:fireside-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/datastore.user"
   gcloud iam service-accounts keys create service-account.json \
     --iam-account=fireside-backend@YOUR_PROJECT_ID.iam.gserviceaccount.com
   mv service-account.json backend/
   ```

### 1.4 Firestore Setup

**Option A: Live Firestore (simpler)**

```bash
gcloud firestore databases create --location=us-central1
```

No further config needed — the backend connects via `GOOGLE_CLOUD_PROJECT`.

**Option B: Firestore Emulator (offline dev)**

```bash
# Install the emulator
gcloud components install cloud-firestore-emulator

# Start it
gcloud emulators firestore start --host-port=localhost:8080
```

Then set in your `.env`:
```env
FIRESTORE_EMULATOR_HOST=localhost:8080
```

### 1.5 Start the Backend

```bash
cd backend
python main.py
```

This starts uvicorn on `http://localhost:8000` with hot-reload enabled. You should see:

```
🔥 Fireside: Betrayal backend starting up...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Verify: `curl http://localhost:8000/health`
→ `{"status": "ok", "service": "fireside-betrayal", "version": "0.1.0"}`

### 1.6 Frontend Setup

Open a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

This starts Vite on `http://localhost:5173` with HMR. The Vite config proxies:
- `/api/*` → `http://localhost:8000` (REST endpoints)
- `/ws/*` → `ws://localhost:8000` (WebSocket connections)

### 1.7 Test Locally

1. Open `http://localhost:5173` in your browser
2. Create a game → get a 6-character join code
3. Open a second browser tab/incognito → join with the code
4. Start the game as host

**Architecture (local dev):**
```
Browser :5173 ──Vite proxy──→ FastAPI :8000
                                 ├── /api/* (REST)
                                 ├── /ws/*  (WebSocket)
                                 ├── Gemini API (narrator voice, traitor AI)
                                 └── Firestore (game state)
```

---

## Part 2: Production Deployment (Cloud Run) — Manual

### 2.1 Architecture

In production, the backend serves both the API and the compiled frontend as static files from a single Cloud Run container:

```
Internet → Cloud Run :8000
             ├── /api/* → FastAPI routes
             ├── /ws/*  → WebSocket handler
             └── /*     → frontend/dist/ (static React app)
```

The `main.py` auto-mounts `frontend/dist/` if it exists at `../frontend/dist` relative to the backend.

### 2.2 Build the Docker Image

From the **repo root**:

```bash
docker build -t fireside-betrayal .
```

The root `Dockerfile` is a multi-stage build: Stage 1 compiles the React frontend with Node 18, Stage 2 installs Python deps and copies both `backend/` and the compiled `frontend/dist/` into the final image. No separate frontend build step is needed.

### 2.3 Test Docker Locally

```bash
docker run -p 8000:8000 \
  -e GOOGLE_CLOUD_PROJECT=your-project-id \
  -e GEMINI_API_KEY=your-key \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/sa.json \
  -v $(pwd)/backend/service-account.json:/app/sa.json:ro \
  fireside-betrayal
```

Visit `http://localhost:8000` — should serve the React app with the API on the same origin.

### 2.4 Deploy to Cloud Run

```bash
# Set your project
export PROJECT_ID=your-gcp-project-id
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com

# Build and push to Artifact Registry
gcloud builds submit \
  --tag gcr.io/$PROJECT_ID/fireside-betrayal \
  --timeout=600

# Deploy to Cloud Run
gcloud run deploy fireside-betrayal \
  --image gcr.io/$PROJECT_ID/fireside-betrayal \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --session-affinity \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GEMINI_API_KEY=your-key,EXTRA_ORIGIN=https://fireside-betrayal-HASH.run.app"
```

**Critical flags:**
- `--session-affinity` — Required for WebSocket connections. Without this, subsequent WS frames may route to a different instance.
- `--port 8000` — Matches Dockerfile `EXPOSE 8000`
- `EXTRA_ORIGIN` — Set this to your Cloud Run URL so CORS allows it. Get the URL after first deploy, then update.

### 2.5 Post-Deploy: Set CORS Origin

After deployment, Cloud Run gives you a URL like `https://fireside-betrayal-abc123-uc.a.run.app`. Update the env var:

```bash
gcloud run services update fireside-betrayal \
  --set-env-vars="EXTRA_ORIGIN=https://fireside-betrayal-abc123-uc.a.run.app"
```

### 2.6 Custom Domain (Optional)

```bash
gcloud run domain-mappings create \
  --service fireside-betrayal \
  --domain play.fireside.game \
  --region us-central1
```

Follow the DNS verification steps in the output.

---

## Part 3: Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Yes | `""` | GCP project ID for Firestore |
| `GEMINI_API_KEY` | Yes | `""` | Gemini API key for all AI agents |
| `GOOGLE_APPLICATION_CREDENTIALS` | Local only | `""` | Path to service account JSON |
| `FIRESTORE_EMULATOR_HOST` | No | `None` | Set to `localhost:8080` for emulator |
| `NARRATOR_MODEL` | No | `gemini-2.5-flash-native-audio-preview-12-2025` | Narrator voice model |
| `TRAITOR_MODEL` | No | `gemini-2.5-flash` | Traitor strategy model |
| `NARRATOR_PREVIEW_MODEL` | No | `gemini-2.5-flash-preview-tts` | TTS for narrator preset previews |
| `NARRATOR_VOICE` | No | `Charon` | Default narrator voice name |
| `ALLOWED_ORIGINS` | No | `localhost:5173,localhost:3000` | CORS origins (comma-separated) |
| `EXTRA_ORIGIN` | No | `""` | Production Cloud Run URL for CORS |
| `DEBUG` | No | `false` | Enable debug logging |

---

## Part 4: Project Structure

```
fireside-betrayal-hackaton/
├── Dockerfile                     # Multi-stage: Node build + Python runtime
├── .dockerignore                  # Excludes .git, secrets, node_modules
├── backend/
│   ├── agents/
│   │   ├── narrator_agent.py      # Gemini Live API voice narrator
│   │   ├── traitor_agent.py       # AI hidden player strategy
│   │   ├── game_master.py         # Deterministic game logic
│   │   ├── role_assigner.py       # Character generation + role dealing
│   │   ├── scene_agent.py         # Phase transition illustrations
│   │   ├── camera_vote.py         # Gemini Vision hand-counting
│   │   ├── audio_recorder.py      # Highlight reel recording
│   │   └── strategy_logger.py     # Cross-game AI learning
│   ├── models/                    # Pydantic data models
│   ├── routers/
│   │   ├── game_router.py         # REST: /api/games, /api/games/{id}/join, etc.
│   │   └── ws_router.py           # WebSocket: /ws/{gameId}?playerId={id}
│   ├── services/
│   │   └── firestore_service.py   # Firestore CRUD + order_by("joined_at")
│   ├── utils/
│   │   └── audio.py               # pcm_to_wav conversion
│   ├── config.py                  # Pydantic Settings (env var loading)
│   ├── main.py                    # FastAPI app + CORS + static mount
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/components/
│   │   ├── JoinLobby/             # Lobby + narrator preview + host badge
│   │   ├── Game/                  # GameScreen + day-hint + reactions
│   │   └── ...
│   ├── package.json               # React 18 + react-router-dom + Vite 5
│   ├── vite.config.js             # Proxy /api → :8000, /ws → ws://:8000
│   └── index.html
├── terraform/                     # Infrastructure as Code (Part 5)
│   ├── main.tf
│   ├── variables.tf
│   └── terraform.tfvars.example
└── docs/
    ├── PRD.md
    ├── TDD.md
    ├── DEPLOYMENT.md              # This file
    ├── architecture.mermaid
    ├── fireside-ui.jsx
    └── playtest-personas.md
```

---

## Part 5: Automated Deployment (Terraform)

> **Hackathon bonus:** This section demonstrates automated cloud deployment using infrastructure-as-code.

Instead of running the manual `gcloud` commands in Part 2, you can provision everything with a single `terraform apply`. The Terraform config in `terraform/` creates:

- All required GCP API enablements
- Cloud Firestore database
- Artifact Registry repository
- Cloud Run service with session affinity (WebSocket support)
- Public IAM policy (unauthenticated access)

### 5.1 Prerequisites

Install Terraform (v1.5+):

```bash
# macOS
brew install terraform

# Linux
sudo apt-get install -y terraform

# Or download from https://developer.hashicorp.com/terraform/downloads
```

Authenticate with GCP:

```bash
gcloud auth application-default login
```

### 5.2 Configure Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
project_id     = "your-gcp-project-id"
region         = "us-central1"
gemini_api_key = "your-gemini-api-key"
```

> **Never commit `terraform.tfvars`** — it contains your API key. It's already in `.gitignore`.

### 5.3 Build and Push the Docker Image

Terraform provisions the infrastructure but doesn't build your Docker image. Build and push it first:

```bash
# From repo root (the multi-stage Dockerfile handles the frontend build)
export PROJECT_ID=your-gcp-project-id
export IMAGE=us-central1-docker.pkg.dev/$PROJECT_ID/fireside/fireside-betrayal:latest

# Build and push
gcloud builds submit --tag $IMAGE --timeout=600
```

### 5.4 Deploy Everything

```bash
cd terraform
terraform init
terraform plan     # Review what will be created
terraform apply    # Provision all resources
```

Terraform outputs your Cloud Run URL:

```
Outputs:

service_url        = "https://fireside-betrayal-abc123-uc.a.run.app"
image_url          = "us-central1-docker.pkg.dev/your-project/fireside/fireside-betrayal:latest"
firestore_database = "(default)"
```

### 5.5 Post-Deploy: Set CORS

After the first deploy, update `EXTRA_ORIGIN` with the Cloud Run URL from the output:

```bash
gcloud run services update fireside-betrayal \
  --region us-central1 \
  --set-env-vars="EXTRA_ORIGIN=https://fireside-betrayal-abc123-uc.a.run.app"
```

### 5.6 Tear Down (if needed)

```bash
terraform destroy   # Removes all provisioned resources
```

### 5.7 What's in `terraform/`

| File | Purpose |
|------|---------|
| `main.tf` | All resource definitions (APIs, Firestore, Artifact Registry, Cloud Run, IAM) |
| `variables.tf` | Input variables (project_id, region, gemini_api_key) |
| `terraform.tfvars.example` | Template for your secret values |

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `CORS error` in browser | Backend doesn't recognize frontend origin | Add origin to `ALLOWED_ORIGINS` or set `EXTRA_ORIGIN` |
| `WebSocket disconnected` on Cloud Run | No session affinity | Redeploy with `--session-affinity` flag |
| `Could not pre-load intelligence brief` on startup | No prior games in Firestore (expected on first run) | Ignore — strategy logger populates after first completed game |
| `FIRESTORE_EMULATOR_HOST` set but emulator not running | Emulator not started | Run `gcloud emulators firestore start` first |
| `403 Forbidden` from Gemini API | API key invalid or project not enabled | Verify key at [AI Studio](https://aistudio.google.com/apikey), enable Generative AI API |
| Frontend shows blank page on Cloud Run | `frontend/dist/` not in the image | Rebuild with the root `Dockerfile` which includes the multi-stage frontend build |
| `--workers 1` in Dockerfile | Required — WebSocket state is per-process | Do not increase workers; scale via Cloud Run instances instead |
| `terraform plan` fails with auth error | Not authenticated with GCP | Run `gcloud auth application-default login` |
| `terraform apply` — image not found | Docker image not pushed yet | Build and push the image first (see §5.3), then `terraform apply` |
