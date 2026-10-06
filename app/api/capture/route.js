/**
 * app/api/capture/route.js
 *
 * Next.js App Router API route — runs server-side on the Raspberry Pi.
 * Triggers libcamera-still to capture a JPEG from the RPi Camera Module
 * and streams it back to the browser as an image/jpeg response.
 *
 * Enabled when: NEXT_PUBLIC_CAMERA_MODE=PICAMERA in .env.local
 *
 * Prerequisites on RPi OS:
 *   sudo raspi-config → Interface Options → Camera → Enable
 *   (libcamera-still is pre-installed on RPi OS Bookworm)
 *
 * Test from RPi terminal:
 *   libcamera-still -o /tmp/test.jpg --nopreview -t 200
 */

import { NextResponse } from "next/server";
import { exec }         from "child_process";
import { promisify }    from "util";
import fs               from "fs/promises";
import path             from "path";
import os               from "os";

const execAsync = promisify(exec);

export async function POST() {
  // Unique temp file per request to avoid race conditions
  const outputPath = path.join(os.tmpdir(), `palf_${Date.now()}.jpg`);

  try {
    // ── libcamera-still (RPi Camera Module v2 / v3 / HQ) ──────────────────
    // -t 1      : capture timeout ms (1 = immediate, raise if image is blurry)
    // --nopreview : don't open a preview window (headless / PM2)
    // --width / --height : resolution (adjust to your camera's max)
    await execAsync(
      `libcamera-still --output "${outputPath}" --nopreview -t 1 --width 1280 --height 720`,
      { timeout: 10_000 }   // kill if camera hangs after 10 s
    );

    // ── OR picamera2 Python one-liner (uncomment if libcamera-still is unavailable) ──
    // await execAsync(
    //   `python3 -c "
    // from picamera2 import Picamera2
    // cam = Picamera2()
    // cam.start()
    // cam.capture_file('${outputPath}')
    // cam.close()
    // "`,
    //   { timeout: 10_000 }
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
    return NextResponse.json(
      {
        error:   "Camera capture failed.",
        detail:  err.message,
        hint:    "Make sure the RPi camera is enabled (raspi-config) and libcamera-still is installed.",
      },
      { status: 500 }
    );

  } finally {
    // Clean up temp file regardless of success/failure
    await fs.unlink(outputPath).catch(() => {});
  }
}
