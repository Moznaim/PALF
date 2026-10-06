/**
 * app/api/stream/route.js
 *
 * Next.js App Router API route — proxies the live MJPEG stream from
 * the internal Picamera2 daemon (127.0.0.1:5001/stream) to client browsers.
 *
 * Displayed in the frontend via: <img src="/api/stream" />
 */

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch("http://127.0.0.1:5001/stream", {
      headers: {
        Accept: "multipart/x-mixed-replace",
      },
      cache: "no-store",
    });

    if (!res.ok) {
      return new Response("Camera stream unavailable from service", { status: 503 });
    }

    return new Response(res.body, {
      headers: {
        "Content-Type": "multipart/x-mixed-replace; boundary=FRAME",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        Pragma: "no-cache",
        Expires: "0",
        Connection: "keep-alive",
      },
    });
  } catch (err) {
    return new Response(
      `Camera stream offline (make sure scripts/camera_service.py is running on :5001). Error: ${err.message}`,
      { status: 503 }
    );
  }
}

