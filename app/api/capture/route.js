/**
 * app/api/capture/route.js
 *
 * Next.js App Router API route — runs server-side on the Raspberry Pi.
 * Triggers rpicam-still (Bookworm) or libcamera-still (Bullseye) to
 * capture a JPEG from the RPi Camera Module and returns it as image/jpeg.
 *
 * This route runs INSIDE Next.js — no separate Express server needed.
 * PM2 only needs to manage one process (`next start` on port 3000).
 *
 * Enabled when: NEXT_PUBLIC_CAMERA_MODE=PICAMERA in .env.local
 *
 * Prerequisites on RPi OS:
 *   sudo raspi-config → Interface Options → Camera → Enable
 *   rpicam-still is pre-installed on RPi OS Bookworm (64-bit)
 *
 * Test from RPi terminal:
 *   rpicam-still -o /tmp/test.jpg --nopreview -t 200
 */

import { NextResponse } from "next/server";
import { exec }         from "child_process";
import { promisify }    from "util";
import fs               from "fs/promises";
import path             from "path";
import os               from "os";

const execAsync = promisify(exec);

/**
 * Detects whether this system uses `rpicam-still` (Bookworm+) or
 * the older `libcamera-still` (Bullseye).  Caches the result.
 */
let _cameraCmd = null;
async function getCameraCmd() {
  if (_cameraCmd) return _cameraCmd;
  try {
    await execAsync("rpicam-still --version", { timeout: 3000 });
    _cameraCmd = "rpicam-still";
  } catch {
    try {
      await execAsync("libcamera-still --version", { timeout: 3000 });
      _cameraCmd = "libcamera-still";
    } catch {
      _cameraCmd = null;
    }
  }
  return _cameraCmd;
}

export async function POST() {
  const outputPath = path.join(os.tmpdir(), `palf_${Date.now()}.jpg`);

  try {
    const cmd = await getCameraCmd();
    if (!cmd) {
      return NextResponse.json(
        {
          error:  "No camera command found.",
          detail: "Neither rpicam-still nor libcamera-still is installed.",
          hint:   "Install with: sudo apt install -y rpicam-apps (Bookworm) or libcamera-apps (Bullseye)",
        },
        { status: 500 }
      );
    }

    // ── Capture a single frame ───────────────────────────────────────────
    //  --nopreview : headless — no X11 display (required under PM2)
    //  -t 1        : minimal capture delay in ms (raise to 500+ if images are dark)
    //  --width / --height : 1280×720; adjust to your IMX219's supported modes
    //
    // Your IMX219 supports (from rpicam-hello --list-cameras):
    //   640x480, 1640x1232, 1920x1080, 3280x2464
    await execAsync(
      `${cmd} --output "${outputPath}" --nopreview -t 1 --width 1280 --height 720`,
      { timeout: 15_000 }   // 15 s max (first capture after boot can be slow)
    );

    // ── OR picamera2 Python fallback (uncomment if rpicam-still has issues) ──
    // await execAsync(
    //   `python3 -c "
    // from picamera2 import Picamera2
    // cam = Picamera2()
    // cam.start()
    // import time; time.sleep(0.5)
    // cam.capture_file('${outputPath}')
    // cam.close()
    // "`,
    //   { timeout: 15_000 }
    // );

    const buffer = await fs.readFile(outputPath);

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type":        "image/jpeg",
        "Content-Disposition": "inline",
        "Cache-Control":       "no-store",
      },
    });

  } catch (err) {
    console.error("[/api/capture] Error:", err.message);

    // Check for common RPi camera errors and give helpful hints
    let hint = "Make sure the RPi camera is enabled via raspi-config and the ribbon cable is seated.";
    if (err.message.includes("Camera is not available"))
      hint = "Run: sudo raspi-config → Interface Options → Camera → Enable, then reboot.";
    if (err.message.includes("ENOENT"))
      hint = "rpicam-still/libcamera-still not found. Run: sudo apt install -y rpicam-apps";

    return NextResponse.json(
      { error: "Camera capture failed.", detail: err.message, hint },
      { status: 500 }
    );

  } finally {
    await fs.unlink(outputPath).catch(() => {});
  }
}
