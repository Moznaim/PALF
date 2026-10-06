# PALF-Vision AI

> **Pineapple Leaf Fiber Grading System** — an offline-capable web application that captures fiber images, reads moisture from an ESP32 sensor, and classifies fiber quality using an AI model, all running on a Raspberry Pi 4.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Development Setup (Laptop)](#development-setup-laptop)
- [Raspberry Pi Deployment](#raspberry-pi-deployment)
- [Updating the App (git pull)](#updating-the-app-git-pull)
- [Environment Variables](#environment-variables)
- [Hardware Wiring](#hardware-wiring)
- [Roadmap](#roadmap)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, Tailwind CSS |
| PDF Export | jsPDF (client-side) |
| Camera | `getUserMedia()` (webcam/V4L2) or `libcamera` via backend |
| Database | IndexedDB (offline-first, browser-native via `idb`) |
| Session | `localStorage` |
| Backend (planned) | Express.js + Python (PyTorch) |
| Process manager | PM2 |
| Target hardware | Raspberry Pi 4 (2 GB+ RAM), RPi Camera Module, ESP32 |

---

## Project Structure

```
palf-vision/
├── app/
│   ├── layout.jsx          # Root layout
│   ├── page.jsx            # Redirects / → /login
│   ├── login/page.jsx      # Login + Register
│   └── dashboard/page.jsx  # Overview + Inspect tabs
├── lib/
│   ├── auth.js             # register, signIn, getSession, signOut
│   ├── db.js               # IndexedDB schema (users + inspections)
│   ├── inspection.js       # classify, saveInspection, getInspections
│   ├── camera.js           # Webcam (dev) / libcamera (RPi) adapter
│   ├── sensor.js           # Moisture sensor: mock / ESP32 serial / ESP32 HTTP
│   └── pdfReport.js        # PDF receipt generator
├── scripts/
│   ├── setup-raspi.sh      # One-shot RPi OS setup script
│   └── deploy.sh           # git pull + build + restart (run on RPi)
├── ecosystem.config.js     # PM2 process config
├── .env.example            # Environment variable template
└── .gitignore
```

---

## Development Setup (Laptop)

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/palf-vision.git
cd palf-vision

# 2. Install dependencies
npm install

# 3. Set up environment
cp .env.example .env.local
# Leave all values as MOCK for local development

# 4. Run the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

> **Auth note:** Register with any name/email/password (min 8 chars). Credentials are stored in your browser's IndexedDB — not on any server.

---

## Raspberry Pi Deployment

### First-time setup (run once on a fresh RPi OS)

```bash
# Download and run the setup script
curl -fsSL https://raw.githubusercontent.com/<your-username>/palf-vision/main/scripts/setup-raspi.sh | bash
```

Or manually:

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 3. Install PM2 globally (process manager — keeps app alive + auto-starts on boot)
sudo npm install -g pm2

# 4. Enable the RPi camera
sudo raspi-config nonint do_camera 0
# → or run: sudo raspi-config → Interface Options → Camera → Enable

# 5. Install picamera2 (for /api/capture backend later)
sudo apt install -y python3-picamera2

# 6. Clone the repo
git clone https://github.com/<your-username>/palf-vision.git
cd palf-vision

# 7. Install dependencies and build
npm install
cp .env.example .env.local
nano .env.local   # ← set CAMERA_MODE, DEVICE_MODE, etc. for RPi

# 8. Build and start with PM2
npm run build
pm2 start ecosystem.config.js

# 9. Save PM2 process list so it survives reboot
pm2 save
pm2 startup   # ← follow the printed command (sudo env PATH=...)
```

The app will now be available at `http://<raspi-ip>:3000` on your local network.

---

## Updating the App (git pull)

Whenever you push new changes from your laptop:

```bash
# On the Raspberry Pi — run this one command:
cd ~/palf-vision && bash scripts/deploy.sh
```

The deploy script does:
1. `git pull` — fetch latest code
2. `npm install` — update dependencies if needed
3. `npm run build` — rebuild Next.js
4. `pm2 restart palf-vision` — restart the running app with zero manual steps

---

## Environment Variables

Copy `.env.example` to `.env.local` and adjust:

| Variable | Default | RPi value | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_CAMERA_MODE` | `WEBCAM` | `WEBCAM` (V4L2) or `PICAMERA` | Camera source |
| `NEXT_PUBLIC_DEVICE_MODE` | `MOCK` | `ESP32_SERIAL` or `ESP32_HTTP` | Moisture sensor |
| `NEXT_PUBLIC_MODEL_MODE` | `MOCK` | `PYTORCH` (when model is ready) | AI classifier |
| `NEXT_PUBLIC_API_URL` | `http://localhost:4000` | `http://localhost:4000` | Express backend |
| `NEXT_PUBLIC_ESP32_URL` | `http://192.168.1.100` | Your ESP32's IP | ESP32 HTTP mode |

> **Never commit `.env.local`** — it is in `.gitignore`. Only `.env.example` goes into git.

---

## Hardware Wiring

```
Capacitive Moisture Sensor
  OUT → ESP32 GPIO34 (ADC1)
  VCC → ESP32 3.3V
  GND → ESP32 GND

ESP32
  USB → Raspberry Pi USB port   (serial mode → /dev/ttyUSB0)
  OR connect to same WiFi LAN   (HTTP mode)

RPi Camera Module
  CSI ribbon cable → RPi Camera port
  Enable via raspi-config → Interface Options → Camera
```

---

## Roadmap

- [x] User registration & login (IndexedDB, SHA-256 password hash)
- [x] Offline inspection history with image storage
- [x] PDF receipt export
- [x] Webcam capture (getUserMedia)
- [x] Camera adapter (webcam ↔ picamera2 switchable)
- [x] Moisture sensor adapter (mock ↔ ESP32 serial ↔ ESP32 HTTP)
- [ ] Express.js backend (`/api/classify`, `/api/capture`, `/api/moisture`)
- [ ] Python PyTorch fiber grading model
- [ ] ESP32 firmware (serial + HTTP modes)
- [ ] RPi Camera Module integration via libcamera backend
