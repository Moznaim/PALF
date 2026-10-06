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
   PICAMERA MODE  (Raspberry Pi — libcamera / picamera2)
   ──────────────────────────────────────────────────────────────────
   HOW TO ENABLE ON RASPI 4:
     1. Enable the camera: sudo raspi-config → Interface Options → Camera
     2. Set NEXT_PUBLIC_CAMERA_MODE=PICAMERA in .env.local
     3. The Next.js API route app/api/capture/route.js handles the rest —
        no separate Express server needed.

   The route runs libcamera-still server-side and returns the JPEG.
   ────────────────────────────────────────────────────────────────── */

/**
 * Calls the built-in Next.js /api/capture route which triggers
 * libcamera-still on the Raspberry Pi and returns the JPEG as a Blob.
 *
 * The route lives at: app/api/capture/route.js
 * It runs entirely inside `next start` — no separate backend needed.
 *
 * @returns {Promise<Blob>} JPEG image blob from RPi Camera Module
 */
export async function captureFromPiCamera() {
  const res = await fetch("/api/capture", {
    method: "POST",
    signal: AbortSignal.timeout(12_000),  // 12 s max (camera warm-up)
  });

  if (!res.ok) {
    // Try to parse a JSON error body for a helpful message
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(
      "RPi camera capture failed: " + (body.detail || body.error || res.statusText)
    );
  }

  return res.blob();
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
