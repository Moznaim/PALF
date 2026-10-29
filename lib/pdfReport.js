/**
 * pdfReport.js
 * Generates a PALF-Vision AI inspection receipt formatted for POS/Thermal receipt printers (80mm width).
 * Uses jsPDF (client-side only — no server required).
 */

import { jsPDF } from "jspdf";

/**
 * Generates an 80mm thermal receipt inspection slip.
 * @param {object} opts
 * @param {object} opts.result      – classification result object
 * @param {object} opts.user        – session user { name, email }
 * @param {string} [opts.imageName] – original file name, if any
 * @param {boolean} [opts.print]    – if true, triggers browser print dialog immediately
 */
export function generateInspectionPDF({ result, user = {}, imageName = "N/A", print = false }) {
  const isSim = Boolean(result.simulated);
  // 80mm roll width; height sized to fit all rows on a single continuous slip
  const pageHeight = isSim ? 160 : 138;
  const doc = new jsPDF({
    unit: "mm",
    format: [80, pageHeight],
  });

  const W = 80;
  const margin = 5;
  const contentW = W - margin * 2; // 70mm printable width

  // Crisp black dividers for thermal print heads
  const line = (y, dashed = true) => {
    doc.setDrawColor(0, 0, 0);
    doc.setLineWidth(dashed ? 0.2 : 0.35);
    if (dashed) {
      doc.setLineDashPattern([1, 1], 0);
    } else {
      doc.setLineDashPattern([], 0);
    }
    doc.line(margin, y, W - margin, y);
    doc.setLineDashPattern([], 0);
  };

  const kv = (label, val, y, isBold = false) => {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7.5);
    doc.setTextColor(0, 0, 0);
    doc.text(label, margin, y);
    doc.setFont("helvetica", isBold ? "bold" : "normal");
    doc.text(String(val), W - margin, y, { align: "right" });
  };

  let y = 7;

  // ── Header ────────────────────────────────────────────────────────
  doc.setFont("helvetica", "bold");
  doc.setFontSize(13);
  doc.setTextColor(0, 0, 0);
  doc.text("PALF-VISION AI", W / 2, y, { align: "center" });
  y += 4.5;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  doc.text("Pineapple Leaf Fiber Grading Slip", W / 2, y, { align: "center" });
  y += 3.8;

  doc.setFontSize(6.5);
  doc.setFont("helvetica", "italic");
  doc.text("Official Edge Inspection Report", W / 2, y, { align: "center" });
  y += 4;

  line(y, true);
  y += 4.5;

  // ── Metadata ──────────────────────────────────────────────────────
  const rawTs = result.timestamp || new Date().toISOString();
  const receiptNo = "INS-" + String(rawTs).replace(/\D/g, "").slice(0, 14);
  const dateStr = new Date(rawTs).toLocaleString("en-PH");
  const inspectorName = (user && user.name) || "Field Inspector";
  const deviceMode = (typeof window !== "undefined" && process.env.NEXT_PUBLIC_DEVICE_MODE) || "Raspberry Pi Edge";

  kv("Receipt No:", receiptNo, y);
  y += 3.8;
  kv("Date & Time:", dateStr, y);
  y += 3.8;
  kv("Inspector:", inspectorName, y);
  y += 3.8;
  kv("Station:", deviceMode, y);
  y += 4;

  line(y, true);
  y += 3;

  // ── Prominent Grade Box (High-contrast solid block for thermal) ───
  doc.setFillColor(0, 0, 0);
  doc.rect(margin, y, contentW, 15, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(7);
  doc.text("CLASSIFICATION RESULT", W / 2, y + 4.2, { align: "center" });

  doc.setFontSize(13.5);
  const gradeText = "GRADE: " + String(result.grade || "N/A").toUpperCase();
  doc.text(gradeText, W / 2, y + 11.5, { align: "center" });
  y += 18;

  // ── Inspection Metrics ────────────────────────────────────────────
  doc.setTextColor(0, 0, 0);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(7.5);
  doc.text("INSPECTION METRICS", margin, y);
  y += 2.2;
  line(y, false);
  y += 3.8;

  const moistureVal = result.moisture != null ? `${result.moisture} %` : "—";
  const confidenceVal = result.confidence != null ? String(result.confidence) : "Not provided";
  const modelVal = result.model || "Hybrid Model";
  const sourceVal = isSim ? "Simulated (Mock)" : "Real PyTorch Model";
  const safeImage = imageName && imageName !== "N/A"
    ? (imageName.length > 22 ? imageName.slice(0, 19) + "..." : imageName)
    : "No image recorded";

  kv("Moisture Content:", moistureVal, y, true);
  y += 3.8;
  kv("AI Confidence:", confidenceVal, y, true);
  y += 3.8;
  kv("Model Architecture:", modelVal, y);
  y += 3.8;
  kv("Inference Source:", sourceVal, y);
  y += 3.8;
  kv("Fiber Image:", safeImage, y);
  y += 4.5;

  line(y, true);
  y += 3.5;

  // ── Grading Reference Legend ──────────────────────────────────────
  doc.setFont("helvetica", "bold");
  doc.setFontSize(6.5);
  doc.text("PHILFIDA QUALITY STANDARD", W / 2, y, { align: "center" });
  y += 3.2;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(6);
  doc.text("EXCELLENT : Clean, white/creamy, high tensile strength", margin, y);
  y += 2.8;
  doc.text("GOOD      : Slight discoloration, standard textile grade", margin, y);
  y += 2.8;
  doc.text("FAIR      : Dark/coarse fiber, non-woven & cordage", margin, y);
  y += 3.5;

  // ── Simulation Warning Box (if simulated) ─────────────────────────
  if (isSim) {
    line(y, true);
    y += 2.5;
    doc.setDrawColor(0, 0, 0);
    doc.setLineWidth(0.3);
    doc.rect(margin, y, contentW, 11);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(6.5);
    doc.text("** SIMULATION NOTICE **", W / 2, y + 3.2, { align: "center" });
    doc.setFont("helvetica", "normal");
    doc.setFontSize(5.5);
    doc.text("Generated using mock model data. Not for commercial trade.", W / 2, y + 6.7, { align: "center" });
    doc.text("Ensure backend API is active for certified grading.", W / 2, y + 9.7, { align: "center" });
    y += 13.5;
  }

  line(y, true);
  y += 3.5;

  // ── Footer / Tear-off ─────────────────────────────────────────────
  doc.setFont("helvetica", "normal");
  doc.setFontSize(6.5);
  doc.text("PALF-Vision Quality Assurance", W / 2, y, { align: "center" });
  y += 3.2;
  doc.setFont("helvetica", "bold");
  doc.setFontSize(6.5);
  doc.text("*** END OF INSPECTION SLIP ***", W / 2, y, { align: "center" });

  // ── Print or Download ─────────────────────────────────────────────
  const safeDate = new Date(rawTs).toISOString().slice(0, 16).replace(/[:T]/g, "-");
  const fileName = `PALF_Receipt_${safeDate}.pdf`;

  if (print && typeof window !== "undefined") {
    doc.autoPrint();
    const blobUrl = doc.output("bloburl");
    window.open(blobUrl, "_blank");
  } else {
    doc.save(fileName);
  }
}

/**
 * Direct ESC/POS hardware receipt printer.
 * Transmits the formatted inspection slip to the Raspberry Pi thermal printer
 * (/dev/usb/lp0) via the Python backend, skipping the browser print dialog completely.
 *
 * @param {object} opts
 * @param {object} opts.result      – classification result object
 * @param {object} opts.user        – session user { name, email }
 * @param {string} [opts.imageName] – original file name, if any
 */
export async function printInspectionReceipt({ result, user = {}, imageName = "N/A" }) {
  try {
    const res = await fetch("/api/print", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result, user, imageName }),
    });

    const data = await res.json().catch(() => ({}));

    if (res.ok && data.status === "printed") {
      return { success: true, ...data };
    }

    const errorMsg = data.detail || `Printer error (${res.status})`;
    console.warn("[Thermal Print Error]:", errorMsg);
    alert(`Thermal Printer Notice:\n${errorMsg}`);
    return { success: false, detail: errorMsg };
  } catch (err) {
    console.error("[Thermal Print Error]:", err);
    alert(`Thermal Printer Connection Error:\n${err.message}`);
    return { success: false, detail: err.message };
  }
}
