# PALF-Vision AI

> **Pineapple Leaf Fiber (PALF) Grading System** — an offline-capable web application that captures fiber images, reads moisture telemetry from an ESP32 sensor, and classifies fiber quality using a multimodal PyTorch deep learning model, deployed on a Raspberry Pi 4.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Laptop Development Setup](#laptop-development-setup)
- [Raspberry Pi 4 Deployment Setup](#raspberry-pi-4-deployment-setup)
- [Model Checkpoint & Architecture](#model-checkpoint--architecture)
- [API Reference](#api-reference)
- [Updating the App (Git Pull)](#updating-the-app-git-pull)
- [Environment Variables](#environment-variables)
- [Hardware Wiring](#hardware-wiring)
- [Roadmap & Progress](#roadmap--progress)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT BROWSER                                 │
│  Next.js 15 (React 19) + Tailwind CSS + IndexedDB Storage (Offline-first)    │
│  - Live Viewfinder (<img src="/api/stream" />)                             │
│  - Inspection Dashboard, PDF Receipts (jsPDF)                               │
└───────────────────────┬───────────────────────────────┬─────────────────────┘
                        │ HTTP :3000                    │ HTTP :4000
                        ▼                               ▼
┌───────────────────────────────────┐   ┌─────────────────────────────────────┐
│     Next.js Web Server (:3000)     │   │      FastAPI Backend (:4000)        │
│  (Managed by PM2: palf-vision)    │   │      (Managed by PM2: palf-api)      │
│                                   │   │                                     │
│  - /api/stream  (proxies :5001)   │   │  - GET  /health                     │
│  - /api/capture (proxies :5001)   │   │  - POST /api/classify               │
│  - /api/moisture (ESP32 serial)   │   │    - Image (224x224 RGB, ImageNet)  │
└─────────────────┬─────────────────┘   │    - Moisture (stats normalization) │
                  │                     │    - EfficientNet-B0 + Attention    │
                  ▼                     │    - Grade + Confidence output      │
┌───────────────────────────────────┐   └──────────────────┬──────────────────┘
│   Picamera2 Service (:5001)       │                      │
│   (Managed by PM2: palf-camera)   │                      ▼
│   - IMX219 CSI Camera Module      │             checkpoint (.pt)
│   - Live 20 fps MJPEG stream      │   backend/models/efficientnet_b0_...pt
│   - Instant in-memory snapshot    │
└───────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Description |
|---|---|---|
| **Frontend** | Next.js 15 (App Router), React 19, Tailwind CSS | Responsive SPA with client-side routing |
| **Local Database** | IndexedDB via `idb` | Complete offline persistence for inspections, user accounts, and image Blobs |
| **PDF Generation** | jsPDF | Client-side grading certificate and receipt generation |
| **Camera (Dev)** | Web API `getUserMedia()` | Laptop webcam feed and capture |
| **Camera (RPi)** | Picamera2 daemon (`scripts/camera_service.py`) | Hardware-accelerated 20 fps MJPEG live feed and zero-delay capture |
| **Backend API** | FastAPI, Uvicorn | High-performance Python REST API on port `4000` |
| **AI Model** | PyTorch, Torchvision | Multimodal `EfficientNet-B0 + Attention Fusion` (Image + Moisture $\rightarrow$ Grade) |
| **Process Manager**| PM2 | Multi-process daemon (`palf-vision`, `palf-camera`, `palf-api`) with auto-reboot |
| **Target Hardware**| Raspberry Pi 4 Model B (Bookworm 64-bit), IMX219 Camera Module, ESP32 |

---

## Project Structure

```
webapppineapplefiber/
├── app/
│   ├── layout.jsx                # Root HTML layout & fonts
│   ├── page.jsx                  # Root redirect (/ -> /login)
│   ├── login/page.jsx            # User registration & login (IndexedDB auth)
│   ├── dashboard/page.jsx        # Overview stats, inspection tool, live camera feed
│   └── api/
│       ├── capture/route.js      # Server snapshot endpoint (proxies :5001 with fallback)
│       ├── stream/route.js       # Live MJPEG stream proxy (proxies :5001)
│       └── moisture/route.js     # ESP32 serial reader endpoint
│
├── backend/
│   ├── main.py                   # FastAPI service (endpoints: /health, /api/classify)
│   ├── inference.py              # Image transform, moisture normalization & forward pass
│   ├── inference_models.py       # Exact PyTorch architecture (EfficientNetAttentionModel)
│   ├── schemas.py                # Pydantic request/response validation schemas
│   ├── requirements.txt          # Python dependencies (torch, torchvision, fastapi, etc.)
│   └── models/
│       ├── README.md             # Model placement guide
│       └── efficientnet_b0_attention_best.pt  # Trained model checkpoint (~20.1 MB)
│
├── lib/
│   ├── auth.js                   # Client-side IndexedDB authentication (SHA-256)
│   ├── db.js                     # IndexedDB schema (users, inspections)
│   ├── inspection.js             # Classifier adapter (MOCK vs PYTORCH API) & DB persistence
│   ├── camera.js                 # Camera adapter (WEBCAM vs PICAMERA)
│   ├── sensor.js                 # Moisture adapter (MOCK, ESP32_SERIAL, ESP32_HTTP)
│   └── pdfReport.js              # jsPDF inspection receipt generator
│
├── scripts/
│   ├── camera_service.py         # Picamera2 HTTP daemon (port 5001)
│   ├── setup-raspi.sh            # Automated one-shot RPi setup script
│   └── deploy.sh                 # Git pull + build + restart script
│
├── ecosystem.config.js           # PM2 configuration for all 3 services
├── .env.example                  # Environment variable reference
└── .env.local                    # Local environment configuration
```

---

## Laptop Development Setup

Run the full stack locally on your computer with a webcam:

### 1. Frontend Setup
```bash
# Clone the repository
git clone https://github.com/Moznaim/PALF.git
cd PALF

# Install Node.js dependencies
npm install
```

### 2. Backend Setup
```bash
# Install Python dependencies (from project root)
pip install -r backend/requirements.txt
```

### 3. Model Checkpoint Placement
Ensure `efficientnet_b0_attention_best.pt` is inside `backend/models/`:
```text
backend/models/efficientnet_b0_attention_best.pt
```

### 4. Configure `.env.local`
Create `.env.local` in the project root:
```env
NEXT_PUBLIC_CAMERA_MODE=WEBCAM
NEXT_PUBLIC_DEVICE_MODE=MOCK
NEXT_PUBLIC_MODEL_MODE=PYTORCH
NEXT_PUBLIC_API_URL=http://localhost:4000
```

### 5. Start Services

Open **two terminals**:

* **Terminal 1 (Backend API):**
  ```bash
  python backend/main.py
  ```
  *(Verify at [http://localhost:4000/health](http://localhost:4000/health))*

* **Terminal 2 (Next.js Frontend):**
  ```bash
  npm run dev
  ```
  *(Open [http://localhost:3000](http://localhost:3000))*

---

## Raspberry Pi 4 Deployment Setup

### Option A: Automated Setup (Recommended)
On a fresh Raspberry Pi OS (Bookworm 64-bit) installation:
```bash
cd ~
git clone https://github.com/Moznaim/PALF.git
cd PALF
bash scripts/setup-raspi.sh
```

---

### Option B: Step-by-Step Manual Setup

#### 1. System packages & camera prerequisites
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-picamera2 python3-pip python3-venv build-essential libudev-dev

# Enable camera interface
sudo raspi-config nonint do_camera 0
```

#### 2. Install Node.js 20 LTS & PM2
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pm2
```

#### 3. Clone and install dependencies
```bash
git clone https://github.com/Moznaim/PALF.git ~/PALF
cd ~/PALF

# Frontend dependencies
npm install

# Backend dependencies inside virtual environment
python3 -m venv --system-site-packages backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

#### 4. Copy the Model Checkpoints
Transfer the trained model checkpoint(s) from your laptop to the Raspberry Pi using `scp` (or via a USB drive):
```bash
# Run from your laptop terminal (replace <pi-ip> with your Raspberry Pi's IP address):
scp backend/models/efficientnet_b0_attention_best.pt pi@<pi-ip>:~/PALF/backend/models/
scp backend/models/resnet50_concat_best.pt pi@<pi-ip>:~/PALF/backend/models/
```
Both models can reside side-by-side in `~/PALF/backend/models/`.

#### 5. Configure `.env.local` on the Pi
```bash
nano .env.local
```
Set the Raspberry Pi production settings:
```env
# ── Hardware Camera (Picamera2 daemon via CSI ribbon) ────────────
NEXT_PUBLIC_CAMERA_MODE=PICAMERA

# ── Moisture Sensor (MOCK or ESP32_SERIAL) ───────────────────────
NEXT_PUBLIC_DEVICE_MODE=MOCK

# ── AI Classifier (Calls local Python FastAPI backend) ───────────
NEXT_PUBLIC_MODEL_MODE=PYTORCH
NEXT_PUBLIC_API_URL=http://localhost:4000

# ── Active AI Model Checkpoint (efficientnet or resnet) ──────────
MODEL_NAME=resnet
```

#### 6. Build and start with PM2
```bash
# Build the Next.js production bundle
npm run build

# Start all 3 daemon services (frontend, camera service, and PyTorch API)
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

The application will be live on your local network:
- **Web App Dashboard:** `http://<raspberry-pi-ip>:3000`
- **FastAPI Backend & Swagger UI:** `http://<raspberry-pi-ip>:4000/docs`
- **Health Check:** `http://<raspberry-pi-ip>:4000/health`

#### 7. Useful PM2 Commands on the Pi
```bash
# Check service status (palf-vision, palf-camera, palf-api)
pm2 status

# View live real-time inference and prediction logs
pm2 logs palf-api

# Restart the model backend after changing MODEL_NAME in .env.local
pm2 restart palf-api

# View camera daemon logs
pm2 logs palf-camera
```

---

## Model Checkpoints & Architecture

The backend supports modular multimodal architectures combining RGB visual features with ESP32 moisture telemetry:

| Model | File | Size | Val Macro F1 | Best Use Case |
|---|---|:---:|:---:|---|
| **ResNet-50 + Concat** | `resnet50_concat_best.pt` | ~96.5 MB | **0.9969** | High feature capacity, robust classification |
| **EfficientNet-B0 + Attention** | `efficientnet_b0_attention_best.pt` | ~20.1 MB | **0.9918** | Lightweight, fast inference on Raspberry Pi |

### Switching Active Models
You can switch models at any time **without modifying code**:

1. **Via `.env.local`:**
   Change `MODEL_NAME=resnet` or `MODEL_NAME=efficientnet`, then run:
   ```bash
   pm2 restart palf-api
   ```
2. **Via Dynamic API (Zero Downtime):**
   Send a POST request to switch models live without restarting:
   ```bash
   curl -X POST "http://localhost:4000/models/switch" -F "filename=resnet50_concat_best.pt"
   ```
   Or visit the interactive Swagger UI at `http://<raspberry-pi-ip>:4000/docs`.

### Input & Output Pipeline Specifications
* **Input 1 (Image):** RGB image resized to $224 \times 224$, normalized with standard ImageNet statistics:
  * Mean: `[0.485, 0.456, 0.406]`, Std: `[0.229, 0.224, 0.225]`
* **Input 2 (Moisture):** Scaled using the checkpoint's stored training statistics:
  $$\text{moisture\_norm} = \frac{\text{moisture\_pct} - \mu}{\sigma}$$
* **Output:** Softmax probabilities across 3 target grades:
  * `0`: **Excellent**
  * `1`: **Good**
  * `2`: **Fair**

---

## API Reference

### Backend API (Port 4000)

#### `GET /health`
Returns system status, active model, device, and training metadata:
```json
{
  "status": "ready",
  "model": "efficientnet_b0_attention",
  "device": "cpu",
  "class_names": ["Excellent", "Good", "Fair"],
  "best_epoch": 9,
  "best_val_macro_f1": 0.9918
}
```

#### `POST /api/classify`
* **Content-Type:** `multipart/form-data`
* **Form fields:**
  * `image`: Binary image file (JPEG or PNG)
  * `moisture_pct` or `moisture`: Numeric moisture percentage (e.g., `11.0`)
* **Response:**
```json
{
  "model": "efficientnet_b0_attention",
  "grade": "Excellent",
  "confidence": 0.9712,
  "probabilities": {
    "Excellent": 0.9712,
    "Good": 0.0215,
    "Fair": 0.0073
  },
  "moisture": 11.0,
  "timestamp": "2026-10-10T08:00:00.000Z",
  "status": "completed"
}
```

---

## Updating the App (Git Pull)

Whenever you push new code from your laptop:

On the Raspberry Pi, run:
```bash
cd ~/PALF
bash scripts/deploy.sh
```

`deploy.sh` automatically executes:
1. `git pull`
2. `npm install`
3. `npm run build`
4. `pm2 startOrRestart ecosystem.config.js` (restarts web server, camera service, and backend API)
5. `pm2 save`

---

## Environment Variables

| Variable | Development (Laptop) | Production (RPi 4) | Description |
|---|---|---|---|
| `NEXT_PUBLIC_CAMERA_MODE` | `WEBCAM` | `PICAMERA` | Image source (`WEBCAM` = `getUserMedia`, `PICAMERA` = Picamera2 daemon) |
| `NEXT_PUBLIC_DEVICE_MODE` | `MOCK` | `MOCK` or `ESP32_SERIAL` | Moisture sensor input mode |
| `NEXT_PUBLIC_MODEL_MODE` | `PYTORCH` | `PYTORCH` | Classifier mode (`MOCK` = random, `PYTORCH` = FastAPI backend) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:4000` | `http://localhost:4000` | Backend inference service URL |
| `NEXT_PUBLIC_ESP32_URL` | `http://192.168.1.100` | ESP32 IP | ESP32 WiFi HTTP server address |

---

## Hardware Wiring

```
Capacitive Moisture Sensor
  OUT ────────► ESP32 GPIO34 (ADC1)
  VCC ────────► ESP32 3.3V
  GND ────────► ESP32 GND

ESP32
  USB ────────► Raspberry Pi 4 USB port (/dev/ttyUSB0)
  OR Connect via local WiFi LAN (HTTP mode)

RPi Camera Module (IMX219)
  CSI Ribbon ─► Raspberry Pi 4 Camera Port (CAM/DISP0)
```

---

## Roadmap & Progress

- [x] User registration & login with offline IndexedDB and SHA-256 password hashing
- [x] Offline inspection history database with native image Blob persistence
- [x] Client-side branded PDF receipt and inspection certificate generator (jsPDF)
- [x] Development camera integration via browser `getUserMedia()`
- [x] Raspberry Pi IMX219 hardware integration with Picamera2 streaming daemon
- [x] Live MJPEG camera preview viewfinder (`/api/stream`) on dashboard
- [x] Fast in-memory JPEG snapshot capture (`/api/capture`) with `rpicam-still` fallback
- [x] FastAPI model inference backend on port `4000`
- [x] PyTorch `EfficientNet-B0 + Attention Fusion` multimodal model integration
- [x] Dynamic moisture statistics normalization from checkpoint
- [x] Automated PM2 process manager configuration for all 3 services (`palf-vision`, `palf-camera`, `palf-api`)
- [ ] Physical ESP32 hardware moisture calibration
- [ ] Retrain model on real PALF dataset (post-proof-of-concept phase)
