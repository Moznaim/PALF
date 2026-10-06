#!/usr/bin/env python3
"""
scripts/camera_service.py
Lightweight HTTP service for Raspberry Pi IMX219 camera using Picamera2.

Endpoints:
  GET /stream   - Live MJPEG stream (multipart/x-mixed-replace)
  GET /capture  - Instant JPEG frame from memory (zero spin-up latency)
  GET /health   - Health check endpoint

Runs internally on 127.0.0.1:5001. Proxied by Next.js /api/stream and /api/capture.
"""

import io
import sys
import logging
from threading import Condition
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
except ImportError:
    print("[ERROR] picamera2 is not installed. Run: sudo apt install -y python3-picamera2")
    sys.exit(1)

HOST = "127.0.0.1"
PORT = 5001
WIDTH = 1280
HEIGHT = 720
FPS = 20

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

output = StreamingOutput()
picam2 = None

class StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception:
                pass  # Client disconnected normally

        elif self.path == '/capture':
            with output.condition:
                frame = output.frame
            if frame is None:
                self.send_error(503, "Camera warming up, no frame ready yet")
                return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(frame)

        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        # Silence access logging to keep terminal/PM2 output clean
        return

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    global picam2
    logging.basicConfig(level=logging.INFO, format="[camera-service] %(message)s")
    logging.info(f"Starting Picamera2 at {WIDTH}x{HEIGHT} ({FPS} fps)...")

    picam2 = Picamera2()
    video_config = picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT)})
    picam2.configure(video_config)

    encoder = JpegEncoder()
    picam2.start_recording(encoder, output)
    logging.info(f"Camera active. Service listening on http://{HOST}:{PORT}")

    server = ThreadedHTTPServer((HOST, PORT), StreamingHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        logging.info("Stopping camera service...")
        picam2.stop_recording()
        picam2.close()

if __name__ == '__main__':
    main()
