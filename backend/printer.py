"""
backend/printer.py

Compact thermal receipt printer service for PALF-Vision AI on Raspberry Pi.

Builds the inspection slip as a temporary text file containing plain text
and the ESC/POS formatting commands verified with the MP58Test CUPS raw queue.
The browser print dialog and PDF conversion are bypassed.
"""

import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("palf_printer")

# MP58Test is the raw CUPS queue used for the successful Font B test.
DEFAULT_PRINTER_QUEUE = os.getenv("PRINTER_QUEUE", "MP58Test")
RECEIPT_WIDTH = 42  # Approximate characters per line in ESC/POS Font B.

# ESC/POS commands
ESC = b"\x1b"
INIT = ESC + b"@"
FONT_B = ESC + b"M\x01"
LINE_SPACING_COMPACT = ESC + b"3\x18"  # 24-dot line spacing
ALIGN_LEFT = ESC + b"a\x00"
ALIGN_CENTER = ESC + b"a\x01"
BOLD_ON = ESC + b"E\x01"
BOLD_OFF = ESC + b"E\x00"
DEFAULT_LINE_SPACING = ESC + b"2"


def _safe_text(value: Any) -> str:
    """Convert a value to one printable line without embedded newlines."""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _encode_line(value: Any) -> bytes:
    """Encode receipt text safely for common ESC/POS printer code pages."""
    return _safe_text(value).encode("ascii", "replace") + b"\r\n"


def _wrap_text(value: Any, width: int = RECEIPT_WIDTH):
    """Wrap long values so they do not run beyond the paper width."""
    text = _safe_text(value)
    if not text:
        return [""]

    words = text.split()
    lines = []
    current = ""

    for word in words:
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]

        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def print_receipt_escpos(
    result: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
    image_name: str = "N/A",
    device_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a compact Font B receipt and submit it to the CUPS raw queue.

    device_path remains in the signature for compatibility with existing
    callers, but printing is handled by CUPS rather than direct device access.
    """
    target_queue = DEFAULT_PRINTER_QUEUE

    # 1. Extract inspection fields
    grade = _safe_text(result.get("grade", "UNKNOWN")).upper()
    confidence = _to_float(result.get("confidence", 0.0))
    moisture = _to_float(result.get("moisture", 0.0))
    model_name = _safe_text(result.get("model", "PALF-Vision AI"))
    probabilities = result.get("probabilities", {})

    user_name = _safe_text((user.get("name") if user else None) or "Inspector")
    user_email = _safe_text((user.get("email") if user else None) or "")
    sample_name = _safe_text(image_name or "N/A")

    # 2. Format timestamp
    raw_timestamp = result.get("timestamp")
    try:
        if raw_timestamp:
            parsed_timestamp = datetime.fromisoformat(
                str(raw_timestamp).replace("Z", "+00:00")
            )
            formatted_date = parsed_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        formatted_date = _safe_text(
            raw_timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    # 3. Build the receipt as text, with Font B and compact line spacing.
    separator = "-" * RECEIPT_WIDTH
    lines = []

    def add_line(value: Any = "") -> None:
        lines.extend(_wrap_text(value))

    def add_label_value(label: str, value: Any) -> None:
        prefix = f"{label:<10}: "
        available_width = RECEIPT_WIDTH - len(prefix)
        value_lines = _wrap_text(value, available_width)
        lines.append(prefix + value_lines[0])
        for continuation in value_lines[1:]:
            lines.append(" " * len(prefix) + continuation)

    # Header
    lines.append("PALF-VISION AI".center(RECEIPT_WIDTH))
    lines.append("Fiber Quality Inspection".center(RECEIPT_WIDTH))
    add_line(separator)

    # Inspection details
    add_label_value("Date", formatted_date)
    add_label_value("Inspector", user_name)
    if user_email:
        add_label_value("Email", user_email)
    add_label_value("Sample", sample_name)
    add_label_value("Moisture", f"{moisture:.1f}%")

    add_line(separator)
    lines.append("CLASSIFICATION RESULT".center(RECEIPT_WIDTH))
    lines.append(grade.center(RECEIPT_WIDTH))
    add_line(f"Confidence: {confidence * 100:.2f}%")
    add_line(separator)

    # Probabilities
    if isinstance(probabilities, dict) and probabilities:
        add_line("Probabilities:")
        for class_name, probability in probabilities.items():
            percentage = _to_float(probability) * 100
            add_line(f"  {_safe_text(class_name)}: {percentage:.2f}%")
        add_line(separator)

    # Footer
    add_line(f"Model: {model_name}")
    lines.append("=" * RECEIPT_WIDTH)
    lines.append("END OF INSPECTION SLIP".center(RECEIPT_WIDTH))

    # Build binary-compatible TXT content: ESC/POS commands plus receipt text.
    receipt = bytearray()
    receipt.extend(INIT)
    receipt.extend(FONT_B)
    receipt.extend(LINE_SPACING_COMPACT)
    receipt.extend(ALIGN_CENTER)
    receipt.extend(BOLD_ON)
    receipt.extend(_encode_line("PALF-VISION AI"))
    receipt.extend(BOLD_OFF)
    receipt.extend(_encode_line("Fiber Quality Inspection"))
    receipt.extend(ALIGN_LEFT)

    # Skip the two header lines already emitted above.
    for line in lines[2:]:
        if line == "CLASSIFICATION RESULT":
            receipt.extend(ALIGN_CENTER)
            receipt.extend(BOLD_ON)
            receipt.extend(_encode_line(line))
            receipt.extend(BOLD_OFF)
            receipt.extend(ALIGN_LEFT)
        elif line == grade.center(RECEIPT_WIDTH):
            receipt.extend(ALIGN_CENTER)
            receipt.extend(BOLD_ON)
            receipt.extend(_encode_line(grade))
            receipt.extend(BOLD_OFF)
            receipt.extend(ALIGN_LEFT)
        elif line == "END OF INSPECTION SLIP".center(RECEIPT_WIDTH):
            receipt.extend(ALIGN_CENTER)
            receipt.extend(_encode_line(line.strip()))
            receipt.extend(ALIGN_LEFT)
        else:
            receipt.extend(_encode_line(line))

    # Feed a small amount of paper at the end; no cut command is assumed.
    receipt.extend(b"\r\n")
    receipt.extend(DEFAULT_LINE_SPACING)

    temp_path = None
    try:
        # The .txt file contains ESC/POS control bytes as well as readable text.
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".txt",
            prefix="palf_receipt_",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(receipt)
            temp_file.flush()

        logger.info(
            "Submitting compact Font B receipt to CUPS raw queue '%s'...",
            target_queue,
        )

        completed = subprocess.run(
            ["lp", "-d", target_queue, "-o", "raw", temp_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        match = re.search(r"request id is (\S+)", completed.stdout or "")
        job_id = match.group(1) if match else None

        logger.info(
            "Receipt submitted to CUPS queue '%s'. Job ID: %s",
            target_queue,
            job_id or "unknown",
        )

        return {
            "status": "printed",
            "queue_status": "queued",
            "device": target_queue,
            "queue": target_queue,
            "driver": "cups-raw-escpos-font-b",
            "job_id": job_id,
            "timestamp": formatted_date,
        }

    except subprocess.CalledProcessError as exc:
        error_message = (exc.stderr or exc.stdout or str(exc)).strip()
        logger.error("CUPS printing failed: %s", error_message)
        raise RuntimeError(
            f"Failed to submit receipt to CUPS queue '{target_queue}': "
            f"{error_message}"
        ) from exc

    except subprocess.TimeoutExpired as exc:
        logger.error("CUPS printing timed out.")
        raise RuntimeError(
            "Timed out while submitting the receipt to CUPS."
        ) from exc

    except FileNotFoundError as exc:
        logger.error("The CUPS 'lp' command was not found.")
        raise RuntimeError(
            "CUPS printing command 'lp' was not found. "
            "Install the CUPS client utilities."
        ) from exc

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as exc:
                logger.warning(
                    "Could not remove temporary receipt file '%s': %s",
                    temp_path,
                    exc,
                )
