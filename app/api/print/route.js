import { NextResponse } from "next/server";

/**
 * app/api/print/route.js
 *
 * Next.js server-side route for direct thermal printing.
 * Forwards receipt data to the Python FastAPI backend (/api/print),
 * which transmits ESC/POS commands directly to /dev/usb/lp0 on the Raspberry Pi.
 * Completely skips the browser print dialog.
 */
export async function POST(request) {
  try {
    const payload = await request.json();
    const apiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:4000";

    const backendRes = await fetch(`${apiUrl}/api/print`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await backendRes.json().catch(() => ({}));

    if (!backendRes.ok) {
      return NextResponse.json(
        { detail: data.detail || `Thermal printing failed with status ${backendRes.status}` },
        { status: backendRes.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("[/api/print error]:", error);
    return NextResponse.json(
      { detail: `Could not connect to printer backend: ${error.message}` },
      { status: 502 }
    );
  }
}

