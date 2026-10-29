"""
backend/printer.py

Direct thermal receipt printer service for PALF-Vision AI on Raspberry Pi.
Formats inspection results into ESC/POS thermal printer commands and transmits
them directly to the printer character device node (defaults to /dev/usb/lp0),
bypassing the browser print dialog completely.
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("palf_printer")

DEFAULT_PRINTER_DEVICE = os.getenv("PRINTER_DEV", "/dev/usb/lp0")

try:
    from escpos.printer import File as EscposFile
    HAS_ESCPOS = True
except ImportError:
    HAS_ESCPOS = False
    logger.info("python-escpos not imported; using high-speed raw ESC/POS binary driver.")


def print_receipt_escpos(
    result: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
    image_name: str = "N/A",
    device_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends inspection slip directly to the USB thermal printer node (/dev/usb/lp0).
    Skips the OS / browser print dialog entirely.
    """
    target_device = device_path or DEFAULT_PRINTER_DEVICE

    # 1. Verify printer device existence
    if not os.path.exists(target_device):
        logger.warning(f"Thermal printer device node '{target_device}' does not exist.")
        raise FileNotFoundError(
            f"Thermal printer not detected at '{target_device}'. "
            "Ensure printer is powered on and plugged into the Raspberry Pi USB port."
        )

    # 2. Extract inspection fields
    grade = str(result.get("grade", "UNKNOWN")).upper()
    confidence = float(result.get("confidence", 0.0))
    moisture = float(result.get("moisture", 0.0))
    model_name = str(result.get("model", "PALF-Vision AI"))
    probs = result.get("probabilities", {})
    user_name = (user.get("name") if user else None) or "Inspector"
    user_email = (user.get("email") if user else None) or ""

    raw_ts = result.get("timestamp")
    try:
        if raw_ts:
            dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        formatted_date = str(raw_ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 3. Print using python-escpos if available
    if HAS_ESCPOS:
        try:
            logger.info(f"Printing receipt to '{target_device}' via python-escpos...")
            printer = EscposFile(target_device)

            # Header
            printer.set(align="center", bold=True, double_height=True, double_width=True)
            printer.text("PALF-VISION AI\n")
            printer.set(align="center", bold=False, double_height=False, double_width=False)
            printer.text("Fiber Quality Inspection\n")
            printer.text("--------------------------------\n")

            # Metadata
            printer.set(align="left")
            printer.text(f"Date:      {formatted_date}\n")
            printer.text(f"Inspector: {user_name}\n")
            if user_email:
                printer.text(f"Email:     {user_email}\n")
            printer.text(f"Sample:    {image_name}\n")
            printer.text(f"Moisture:  {moisture:.1f}%\n")
            printer.text("--------------------------------\n")

            # Classification Grade
            printer.set(align="center")
            printer.text("CLASSIFICATION RESULT\n")
            printer.set(align="center", bold=True, double_height=True, double_width=True)
            printer.text(f"{grade}\n")
            printer.set(align="left", bold=False, double_height=False, double_width=False)
            printer.text(f"Confidence:  {confidence * 100:.2f}%\n")
            printer.text("--------------------------------\n")

            # Probabilities breakdown
            if probs and isinstance(probs, dict):
                printer.text("Probabilities:\n")
                for c_name, p_val in probs.items():
                    pct = float(p_val) * 100
                    printer.text(f"  {c_name:<10}: {pct:>8.2f}%\n")
                printer.text("--------------------------------\n")

            # Footer
            printer.text(f"Model: {model_name}\n")
            printer.set(align="center")
            printer.text("================================\n")
            printer.text("*** END OF INSPECTION SLIP ***\n\n\n\n")

            try:
                printer.cut()
            except Exception:
                pass

            printer.close()
            logger.info("Receipt successfully printed via python-escpos.")
            return {
                "status": "printed",
                "device": target_device,
                "driver": "python-escpos",
                "timestamp": formatted_date,
            }
        except Exception as e:
            logger.warning(f"python-escpos printing encountered '{e}'; attempting raw ESC/POS fallback...")

    # 4. Fallback: Raw binary ESC/POS stream writer
    logger.info(f"Writing raw ESC/POS binary stream to '{target_device}'...")
    ESC = b"\x1b"
    GS = b"\x1d"

    INIT = ESC + b"@"
    ALIGN_LEFT = ESC + b"a\x00"
    ALIGN_CENTER = ESC + b"a\x01"
    BOLD_ON = ESC + b"E\x01"
    BOLD_OFF = ESC + b"E\x00"
    DOUBLE_SIZE = GS + b"!\x11"
    NORMAL_SIZE = GS + b"!\x00"
    FEED_CUT = GS + b"V\x41\x10"

    buf = bytearray()
    buf.extend(INIT)

    # Header
    buf.extend(ALIGN_CENTER + BOLD_ON + DOUBLE_SIZE + b"PALF-VISION AI\n")
    buf.extend(NORMAL_SIZE + BOLD_OFF + b"Fiber Quality Inspection\n")
    buf.extend(b"--------------------------------\n")

    # Metadata
    buf.extend(ALIGN_LEFT)
    buf.extend(f"Date:      {formatted_date}\n".encode("utf-8", "replace"))
    buf.extend(f"Inspector: {user_name}\n".encode("utf-8", "replace"))
    if user_email:
        buf.extend(f"Email:     {user_email}\n".encode("utf-8", "replace"))
    buf.extend(f"Sample:    {image_name}\n".encode("utf-8", "replace"))
    buf.extend(f"Moisture:  {moisture:.1f}%\n".encode("utf-8", "replace"))
    buf.extend(b"--------------------------------\n")

    # Result
    buf.extend(ALIGN_CENTER + b"CLASSIFICATION RESULT\n")
    buf.extend(BOLD_ON + DOUBLE_SIZE + f"{grade}\n".encode("utf-8", "replace"))
    buf.extend(NORMAL_SIZE + BOLD_OFF + ALIGN_LEFT)
    buf.extend(f"Confidence:  {confidence * 100:.2f}%\n".encode("utf-8", "replace"))
    buf.extend(b"--------------------------------\n")

    # Probabilities
    if probs and isinstance(probs, dict):
        buf.extend(b"Probabilities:\n")
        for c_name, p_val in probs.items():
            pct = float(p_val) * 100
            buf.extend(f"  {c_name:<10}: {pct:>8.2f}%\n".encode("utf-8", "replace"))
        buf.extend(b"--------------------------------\n")

    # Footer
    buf.extend(f"Model: {model_name}\n".encode("utf-8", "replace"))
    buf.extend(ALIGN_CENTER)
    buf.extend(b"================================\n")
    buf.extend(b"*** END OF INSPECTION SLIP ***\n\n\n\n")
    buf.extend(FEED_CUT)

    with open(target_device, "wb") as f:
        f.write(buf)
        f.flush()

    logger.info("Receipt successfully printed via raw ESC/POS driver.")
    return {
        "status": "printed",
        "device": target_device,
        "driver": "raw-escpos",
        "timestamp": formatted_date,
    }

