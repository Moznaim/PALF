/**
 * app/api/capture/route.js
 *
 * Next.js App Router API route — captures a JPEG from the RPi camera.
 *
 * Strategy:
 * 1. Fast Path: Queries internal Picamera2 daemon (http://127.0.0.1:5001/capture).
 *    Captures from memory in < 5ms with zero hardware spin-up latency.
 * 2. Fallback: If daemon is not running, executes rpicam-still/libcamera-still.
 */

import { NextResponse } from "next/server";
import { exec }         from "child_process";
import { promisify }    from "util";
import fs               from "fs/promises";
import path             from "path";
import os               from "os";

const execAsync = promisify(exec);

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
  // ── Strategy 1: Fast in-memory capture from camera_service.py daemon ───────
  try {
    const serviceRes = await fetch("http://127.0.0.1:5001/capture", {
      signal: AbortSignal.timeout(2000), // 2s max
      cache: "no-store",
    });

    if (serviceRes.ok) {
      const arrayBuffer = await serviceRes.arrayBuffer();
      return new NextResponse(Buffer.from(arrayBuffer), {
        status: 200,
        headers: {
          "Content-Type": "image/jpeg",
          "Content-Disposition": "inline",
          "Cache-Control": "no-store",
          "X-Capture-Source": "picamera2-daemon",
        },
      });
    }
  } catch {
    // Daemon not running or timed out; fall through to standalone command
  }

  // ── Strategy 2: Standalone rpicam-still fallback ─────────────────────────
  const outputPath = path.join(os.tmpdir(), `palf_${Date.now()}.jpg`);

  try {
    const cmd = await getCameraCmd();
    if (!cmd) {
      return NextResponse.json(
        {
          error: "No camera command found.",
          detail: "Neither camera service on :5001 nor rpicam-still is active.",
          hint: "Run 'python3 scripts/camera_service.py' or check rpicam-apps installation.",
        },
        { status: 500 }
      );
    }

    await execAsync(
      `${cmd} --output "${outputPath}" --nopreview -t 1 --width 1280 --height 720`,
      { timeout: 15_000 }
    );

    const buffer = await fs.readFile(outputPath);

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": "image/jpeg",
        "Content-Disposition": "inline",
        "Cache-Control": "no-store",
        "X-Capture-Source": cmd,
      },
    });

  } catch (err) {
    console.error("[/api/capture] Error:", err.message);
    return NextResponse.json(
      {
        error: "Camera capture failed.",
        detail: err.message,
        hint: "Make sure no other process is holding the camera exclusively.",
      },
      { status: 500 }
    );
  } finally {
    await fs.unlink(outputPath).catch(() => {});
  }
}
