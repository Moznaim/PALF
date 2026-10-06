/**
 * pdfReport.js
 * Generates a PALF-Vision AI inspection receipt as a downloadable PDF.
 * Uses jsPDF (client-side only — no server required).
 */

import {jsPDF} from "jspdf";

// Brand colours (RGB)
const GREEN  = [5, 150, 105];   // emerald-600
const DARK   = [15, 23, 42];    // slate-900
const MID    = [71, 85, 105];   // slate-600
const LIGHT  = [148, 163, 184]; // slate-400
const BORDER = [226, 232, 240]; // slate-200
const BG     = [248, 250, 252]; // slate-50

/**
 * @param {object} opts
 * @param {object} opts.result      – classification result object
 * @param {object} opts.user        – session user { name, email }
 * @param {string} [opts.imageName] – original file name, if any
 */
export function generateInspectionPDF({result, user, imageName="N/A"}){
  const doc = new jsPDF({unit:"pt", format:"a4"});
  const W = doc.internal.pageSize.getWidth();
  const margin = 48;
  const colW = (W - margin * 2) / 2;
  let y = 0;

  // ── helpers ──────────────────────────────────────────────────────
  const line  = (x1,y1,x2,y2,color=BORDER)=>{doc.setDrawColor(...color);doc.line(x1,y1,x2,y2);};
  const rect  = (x,yy,w,h,fill)=>{doc.setFillColor(...fill);doc.rect(x,yy,w,h,"F");};
  const txt   = (text,x,yy,opts={})=>{
    doc.setFontSize(opts.size||10);
    doc.setFont("helvetica", opts.style||"normal");
    doc.setTextColor(...(opts.color||DARK));
    doc.text(String(text),x,yy,{align:opts.align||"left",...opts.textOpts});
  };

  // ── header band ──────────────────────────────────────────────────
  rect(0,0,W,72,GREEN);
  txt("PALF-Vision AI", margin, 30, {size:18, style:"bold", color:[255,255,255]});
  txt("Pineapple Leaf Fiber Inspection Report", margin, 48, {size:10, color:[167,243,208]});
  txt("palfvision.local", W-margin, 30, {size:9, color:[167,243,208], align:"right"});
  txt(new Date(result.timestamp).toLocaleDateString("en-PH",{year:"numeric",month:"long",day:"numeric"}),
    W-margin, 48, {size:9, color:[167,243,208], align:"right"});
  y = 88;

  // ── receipt meta row ─────────────────────────────────────────────
  rect(margin, y, W-margin*2, 36, BG);
  doc.setDrawColor(...BORDER); doc.rect(margin, y, W-margin*2, 36);
  txt("Receipt No.",  margin+10,  y+13, {size:8, color:MID});
  txt(`INS-${result.timestamp.replace(/\D/g,"").slice(0,14)}`, margin+10, y+27, {size:9, style:"bold"});
  txt("Generated",    W/2,        y+13, {size:8, color:MID});
  txt(new Date().toLocaleString("en-PH"), W/2, y+27, {size:9, style:"bold"});
  txt("Inspector",    W-margin-140,y+13, {size:8, color:MID});
  txt(user.name,      W-margin-140,y+27, {size:9, style:"bold"});
  y += 52;

  // ── section helper ───────────────────────────────────────────────
  function section(title){
    txt(title, margin, y, {size:8, style:"bold", color:MID});
    line(margin, y+4, W-margin, y+4, LIGHT);
    y += 16;
  }
  function row(label, value, highlight=false){
    if(highlight){
      rect(margin, y-12, W-margin*2, 18, [236,253,245]); // emerald-50
    }
    txt(label, margin+6,  y, {size:9, color:MID});
    txt(value, W-margin-6, y, {size:9, style:highlight?"bold":"normal",
                                color:highlight?GREEN:DARK, align:"right"});
    line(margin, y+4, W-margin, y+4);
    y += 20;
  }

  // ── classification result ────────────────────────────────────────
  section("CLASSIFICATION RESULT");
  row("Predicted Grade",   result.grade,                     true);
  row("Confidence",        result.confidence ?? "Not provided");
  row("Classification Source", result.simulated?"Simulated (Mock Model)":"Real model output");
  row("Model ID",          result.model);
  row("Status",            result.status ?? "completed");
  y += 8;

  // ── sensor / input data ──────────────────────────────────────────
  section("INPUT METRICS");
  row("Moisture Content",  `${result.moisture} %`);
  row("Image file",        imageName);
  row("Image accepted",    imageName!=="N/A"?"Yes":"No image on record");
  y += 8;

  // ── inspection context ───────────────────────────────────────────
  section("INSPECTION CONTEXT");
  row("Inspector name",  user.name);
  row("Inspector email", user.email ?? "—");
  row("Timestamp",       new Date(result.timestamp).toLocaleString("en-PH"));
  row("Device",          (typeof window!=="undefined"&&process.env.NEXT_PUBLIC_DEVICE_MODE)||"MOCK");
  y += 8;

  // ── grade legend ─────────────────────────────────────────────────
  section("GRADE LEGEND");
  [
    ["Excellent","Highest quality fiber — suitable for fine textile applications."],
    ["Good",     "Mid-grade fiber — suitable for standard industrial use."],
    ["Fair",     "Lower-grade fiber — may require additional processing."],
  ].forEach(([g,desc])=>{
    txt(`${g}:`, margin+6, y, {size:9, style:"bold"});
    txt(desc,    margin+60, y, {size:9, color:MID});
    y += 16;
  });
  y += 8;

  // ── simulation notice (if applicable) ───────────────────────────
  if(result.simulated){
    rect(margin, y, W-margin*2, 40, [255,251,235]); // amber-50
    doc.setDrawColor(217,119,6);
    doc.rect(margin, y, W-margin*2, 40);
    doc.setFillColor(217,119,6);
    doc.rect(margin, y, 4, 40,"F");
    txt("⚠  Simulation Notice", margin+12, y+14, {size:9, style:"bold", color:[146,64,14]});
    txt("This report was generated using a mock AI model. Values are randomised and",
        margin+12, y+26, {size:8, color:[146,64,14]});
    txt("do not reflect actual fiber analysis. Replace with the real model before use.",
        margin+12, y+38, {size:8, color:[146,64,14]});
    y += 56;
  }

  // ── footer ───────────────────────────────────────────────────────
  line(margin, y, W-margin, y, LIGHT);
  y += 14;
  txt("PALF-Vision AI  ·  Pineapple Leaf Fiber Grading System",
      W/2, y, {size:8, color:MID, align:"center"});
  txt("This document is for internal / development use only.",
      W/2, y+12, {size:7.5, color:LIGHT, align:"center"});

  // ── save ─────────────────────────────────────────────────────────
  const safeDate = new Date(result.timestamp).toISOString().slice(0,16).replace(/[:T]/g,"-");
  doc.save(`PALF_Inspection_${safeDate}.pdf`);
}
