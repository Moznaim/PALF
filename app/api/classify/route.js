import { NextResponse } from "next/server";

/**
 * app/api/classify/route.js
 *
 * Next.js server-side proxy route for AI fiber grading.
 * Forwards client multipart form requests to the local Python FastAPI backend (port 4000).
 * Prevents CORS issues and allows clients connecting via local network IP to reach the API.
 */
export async function POST(request) {
  try {
    const formData = await request.formData();
    const apiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:4000";

    const backendRes = await fetch(`${apiUrl}/api/classify`, {
      method: "POST",
      body: formData,
    });

    if (!backendRes.ok) {
      const err = await backendRes.json().catch(() => ({}));
      return NextResponse.json(
        { detail: err.detail || `FastAPI backend error (${backendRes.status})` },
        { status: backendRes.status }
      );
    }

    const data = await backendRes.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("[/api/classify proxy error]:", error);
    return NextResponse.json(
      { detail: `Could not connect to PyTorch backend on port 4000: ${error.message}` },
      { status: 502 }
    );
  }
}

