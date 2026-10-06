/**
 * camera.js  –  Camera adapter for PALF-Vision AI
 *
 * ┌─────────────────────────────────────────────────────────────────┐
 * │  MODE SWITCHING                                                  │
 * │                                                                  │
 * │  WEBCAM  (default / dev laptop)                                  │
 * │    Uses browser getUserMedia().  Works on:                       │
 * │      • Any laptop/desktop with a USB or built-in webcam          │
 * │      • Raspberry Pi 4 if the camera module is registered as a    │
 * │        V4L2 device (/dev/video0) via:                            │
 * │           sudo modprobe bcm2835-v4l2          (legacy camera)    │
 * │           OR libcamera-v4l2 bridge            (camera module v3) │
 * │                                                                  │
 * │  PICAMERA  (Raspberry Pi — picamera2 backend)                    │
 * │    Calls the Express backend /api/capture endpoint which runs    │
 * │    libcamera-still or picamera2 server-side.                     │
 * │    Set NEXT_PUBLIC_CAMERA_MODE=PICAMERA in .env.local            │
 * │                                                                  │
 * │  To swap modes, change NEXT_PUBLIC_CAMERA_MODE in .env.local     │
 * └─────────────────────────────────────────────────────────────────┘
 */

export const CAMERA_MODE =
  process.env.NEXT_PUBLIC_CAMERA_MODE || "WEBCAM"; // "WEBCAM" | "PICAMERA"

/* ──────────────────────────────────────────────────────────────────
   WEBCAM MODE  (getUserMedia — laptop dev + RPi V4L2)
   ────────────────────────────────────────────────────────────────── */

/**
 * Opens the camera stream and binds it to a <video> element.
 *
 * On a laptop  → opens the default webcam.
 * On RPi + V4L2 → opens /dev/video0 (same API, browser handles it).
 *
 * @param {HTMLVideoElement} videoEl  – the <video> element to stream into
 * @returns {Promise<MediaStream>}    – the active stream (keep to stop later)
 */
export async function startWebcam(videoEl) {
  if (CAMERA_MODE !== "WEBCAM") return null;

  const constraints = {
    video: {
      width:  { ideal: 1280 },
      height: { ideal: 720  },
      facingMode: "environment", // rear camera on mobile / RPi HAT orientation

      // ── RASPBERRY PI V4L2 (uncomment on RPi if you have multiple cameras) ──
      // deviceId: { exact: "<device-id-from-enumerateDevices>" },
    },
    audio: false,
  };

  const stream = await navigator.mediaDevices.getUserMedia(constraints);
  videoEl.srcObject = stream;
  await videoEl.play();
  return stream;
}

/**
 * Captures a single frame from the active video stream and returns it
 * as a JPEG Blob (ready to store in IndexedDB or POST to the classifier).
 *
 * @param {HTMLVideoElement} videoEl – the live <video> element
 * @param {number} [quality=0.92]   – JPEG quality 0–1
 * @returns {Promise<Blob>}
 */
export async function captureFrameFromWebcam(videoEl, quality = 0.92) {
  const canvas = document.createElement("canvas");
  canvas.width  = videoEl.videoWidth;
  canvas.height = videoEl.videoHeight;
  canvas.getContext("2d").drawImage(videoEl, 0, 0);
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error("Canvas capture failed.")),
      "image/jpeg",
      quality
    )
  );
}

/**
 * Stops all tracks on the stream (turns off the camera LED).
 * @param {MediaStream|null} stream
 */
export function stopWebcam(stream) {
  stream?.getTracks().forEach(t => t.stop());
}


/* ──────────────────────────────────────────────────────────────────
   PICAMERA MODE  (Raspberry Pi — picamera2 / libcamera backend)
   ──────────────────────────────────────────────────────────────────
   HOW TO ENABLE ON RASPI 4:
     1. Set NEXT_PUBLIC_CAMERA_MODE=PICAMERA in .env.local
     2. Create a backend endpoint (Express or FastAPI) that runs:
          libcamera-still -o /tmp/capture.jpg --nopreview -t 200
        or uses the picamera2 Python library.
     3. The endpoint returns the image as multipart/form-data or
        application/octet-stream (see backend template below).
   ────────────────────────────────────────────────────────────────── */

/**
 * Calls the Express /api/capture endpoint which triggers libcamera
 * on the Raspberry Pi and returns the captured JPEG as a Blob.
 *
 * Backend endpoint template (Express + picamera2):
 * ─────────────────────────────────────────────────
 *   // backend/routes/capture.js
 *   const {execSync} = require("child_process");
 *   const fs         = require("fs");
 *   const path       = "/tmp/palf_capture.jpg";
 *
 *   router.post("/api/capture", (req, res) => {
 *     // libcamera-still (camera module v2/v3):
 *     execSync(`libcamera-still -o ${path} --nopreview -t 200`);
 *
 *     // ── OR picamera2 Python script ──
 *     // execSync(`python3 /home/pi/capture.py ${path}`);
 *
 *     res.sendFile(path);
 *   });
 * ─────────────────────────────────────────────────
 *
 * @returns {Promise<Blob>} JPEG image blob from RPi camera
 */
export async function captureFromPiCamera() {
  // ── UNCOMMENT ON RASPBERRY PI (set NEXT_PUBLIC_CAMERA_MODE=PICAMERA) ──
  //
  // const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";
  // const res = await fetch(`${apiUrl}/api/capture`, { method: "POST" });
  // if (!res.ok) throw new Error("RPi camera capture failed.");
  // return res.blob();

  // Placeholder until backend is ready:
  throw new Error(
    "PICAMERA mode is not yet active. " +
    "Set up the /api/capture backend endpoint on the Raspberry Pi, " +
    "then uncomment the fetch call in lib/camera.js."
  );
}


/* ──────────────────────────────────────────────────────────────────
   UNIFIED CAPTURE  (used by the dashboard — auto-selects mode)
   ────────────────────────────────────────────────────────────────── */

/**
 * High-level capture function.  The dashboard calls this.
 * In WEBCAM mode it reads from the passed <video> element.
 * In PICAMERA mode it calls the RPi backend.
 *
 * @param {HTMLVideoElement|null} videoEl – only needed in WEBCAM mode
 * @returns {Promise<{blob: Blob, name: string}>}
 */
export async function captureImage(videoEl = null) {
  if (CAMERA_MODE === "PICAMERA") {
    const blob = await captureFromPiCamera();
    return { blob, name: `capture_${Date.now()}.jpg` };
  }

  // Default: WEBCAM
  if (!videoEl) throw new Error("No video element provided for webcam capture.");
  const blob = await captureFrameFromWebcam(videoEl);
  return { blob, name: `capture_${Date.now()}.jpg` };
}
