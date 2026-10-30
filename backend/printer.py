
"""
backend/printer.py

Plain-text thermal receipt printer service for PALF-Vision AI on Raspberry Pi.

Formats inspection results into a temporary TXT file and submits it to
the configured CUPS printer queue. This bypasses the browser print dialog
and uses the working Generic Text-Only Printer queue.
"""

import os
import re
import logging
import tempfile
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("palf_printer")

# Existing CUPS queue confirmed to print readable text.
DEFAULT_PRINTER_QUEUE = os.getenv("PRINTER_QUEUE", "PrintReceipt")


def _safe_text(value: Any) -> str:
    """Keep receipt values on a single line."""
    return str(value).replace("\r", " ").replace("\n", " ")


def _to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert values to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def print_receipt_escpos(
    result: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
    image_name: str = "N/A",
    device_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a plain-text inspection receipt and sends it to CUPS.

    The device_path argument is retained for compatibility with existing
    callers. The actual printer is selected through the CUPS queue.
    """

    target_queue = DEFAULT_PRINTER_QUEUE

    # 1. Extract inspection fields
    grade = _safe_text(result.get("grade", "UNKNOWN")).upper()
    confidence = _to_float(result.get("confidence", 0.0))
    moisture = _to_float(result.get("moisture", 0.0))
    model_name = _safe_text(result.get("model", "PALF-Vision AI"))

    probs = result.get("probabilities", {})

    user_name = _safe_text(
        (user.get("name") if user else None) or "Inspector"
    )
    user_email = _safe_text(
        (user.get("email") if user else None) or ""
    )
    image_name = _safe_text(image_name)

    # 2. Format timestamp
    raw_ts = result.get("timestamp")

    try:
        if raw_ts:
            dt = datetime.fromisoformat(
                str(raw_ts).replace("Z", "+00:00")
            )
            formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            formatted_date = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    except Exception:
        formatted_date = str(
            raw_ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    # 3. Build receipt as plain text (32-character receipt width)
    width = 32
    separator = "-" * width

    receipt_lines = [
        "PALF-VISION AI".center(width),
        "Fiber Quality Inspection".center(width),
        separator,
        f"Date:      {formatted_date}",
        f"Inspector: {user_name}",
    ]

    if user_email:
        receipt_lines.append(f"Email:     {user_email}")

    receipt_lines.extend([
        f"Sample:    {image_name}",
        f"Moisture:  {moisture:.1f}%",
        separator,
        "",
        "CLASSIFICATION RESULT".center(width),
        grade.center(width),
        f"Confidence: {confidence * 100:.2f}%",
        separator,
    ])

    # 4. Add classification probabilities
    if isinstance(probs, dict) and probs:
        receipt_lines.append("Probabilities:")

        for class_name, probability in probs.items():
            pct = _to_float(probability) * 100
            class_name = _safe_text(class_name)
            receipt_lines.append(
                f"  {class_name:<10}: {pct:>8.2f}%"
            )

        receipt_lines.append(separator)

    # 5. Footer
    receipt_lines.extend([
        f"Model: {model_name}",
        "",
        "=" * width,
        "*** END OF INSPECTION SLIP ***".center(width),
        "",
        "",
        "",
    ])

    receipt_text = "\n".join(receipt_lines)

    # 6. Save receipt temporarily as TXT and submit it to CUPS
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            errors="replace",
            newline="\n",
            suffix=".txt",
            prefix="palf_receipt_",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(receipt_text)

        logger.info(
            "Submitting text receipt to CUPS queue '%s'...",
            target_queue,
        )

        completed = subprocess.run(
            ["lp", "-d", target_queue, temp_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        # Extract the CUPS job ID from the command output.
        match = re.search(
            r"request id is (\S+)",
            completed.stdout,
        )
        job_id = match.group(1) if match else None

        logger.info(
            "Receipt successfully submitted to CUPS. Job ID: %s",
            job_id or "unknown",
        )

        return {
            "status": "printed",
            "queue_status": "queued",
            "device": target_queue,
            "queue": target_queue,
            "driver": "cups-text",
            "job_id": job_id,
            "timestamp": formatted_date,
        }

    except subprocess.CalledProcessError as e:
        error_message = (e.stderr or e.stdout or str(e)).strip()
        logger.error("CUPS printing failed: %s", error_message)

        raise RuntimeError(
            f"Failed to submit receipt to CUPS queue "
            f"'{target_queue}': {error_message}"
        ) from e

    except subprocess.TimeoutExpired as e:
        logger.error("CUPS printing timed out.")

        raise RuntimeError(
            "Timed out while submitting the receipt to CUPS."
        ) from e

    except FileNotFoundError as e:
        logger.error("CUPS 'lp' command was not found.")

        raise RuntimeError(
            "CUPS printing command 'lp' was not found. "
            "Ensure CUPS client utilities are installed."
        ) from e

    finally:
        # 7. Remove temporary TXT file after submission
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as e:
                logger.warning(
                    "Could not remove temporary receipt file: %s",
                    e,
                )
