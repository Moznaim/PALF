/**
 * inspection.js  –  Validation, classification adapter, and
 *                   IndexedDB persistence for inspections.
 */

import {getDb} from "./db";

export const STATES=[
  "IDLE","ACQUIRING","IMAGE_READY","MOISTURE_READY",
  "VALIDATING","PROCESSING","CLASSIFYING","RESULT","ERROR",
];
export const GRADES=["Excellent","Good","Fair"];

// Placeholder limits — real values come from sensor calibration.
export const CONFIG={
  moistureMin : 0,
  moistureMax : 100,
  maxImageMB  : 10,
  types       : ["image/jpeg","image/png"],
};

export const MODE={
  device : process.env.NEXT_PUBLIC_DEVICE_MODE || "MOCK",
  model  : process.env.NEXT_PUBLIC_MODEL_MODE  || "PYTORCH",
};

/* ── validation ───────────────────────────────────────────────── */
export function validateImage(f){
  if(!f)                            return "No image selected.";
  if(!CONFIG.types.includes(f.type))return "Use a JPEG or PNG image.";
  if(f.size>CONFIG.maxImageMB*1048576)return `Image exceeds ${CONFIG.maxImageMB} MB.`;
  return null;
}

export function validateMoisture(v){
  if(v===""||v==null)               return "Moisture reading is missing.";
  const n=Number(v);
  if(!Number.isFinite(n))           return "Moisture must be a number.";
  if(n<CONFIG.moistureMin||n>CONFIG.moistureMax)
    return `Moisture must be ${CONFIG.moistureMin}–${CONFIG.moistureMax}.`;
  return null;
}

/* ── classifier adapter ───────────────────────────────────────── */
// REAL: POST image + moisture to Express → Python service.
export async function classify({file, moisture}){
  if(MODE.model==="MOCK"){
    await new Promise(r=>setTimeout(r,900));
    return {
      grade     : GRADES[Math.floor(Math.random()*3)],
      confidence: null,
      moisture  : Number(moisture),
      timestamp : new Date().toISOString(),
      model     : "MOCK_MODEL",
      status    : "completed",
      simulated : true,
    };
  }
  const fd = new FormData();
  fd.append("image", file);
  fd.append("moisture", String(moisture));
  fd.append("moisture_pct", String(moisture));

  // Post to Next.js internal /api/classify route (which proxies server-side to FastAPI :4000)
  const r = await fetch("/api/classify", { method: "POST", body: fd });
  if (!r.ok) {
    const errData = await r.json().catch(() => ({}));
    throw new Error(errData.detail || `Classification service error (${r.status})`);
  }
  const d = await r.json();
  if (!GRADES.includes(d.grade)) throw new Error("Model returned an unsupported grade: " + d.grade);
  return { ...d, simulated: false };
}

/* ── IndexedDB persistence ────────────────────────────────────── */

/**
 * Save a completed inspection to IndexedDB.
 * @param {object} opts
 * @param {string}      opts.userEmail
 * @param {object}      opts.result      – object returned by classify()
 * @param {string}      opts.imageName   – original file name
 * @param {Blob|null}   opts.imageBlob   – image file (stored as Blob)
 * @returns {Promise<number>} the auto-generated DB id
 */
export async function saveInspection({userEmail, result, imageName, imageBlob}){
  const db = await getDb();
  return db.add("inspections",{
    userEmail,
    grade     : result.grade,
    confidence: result.confidence ?? null,
    moisture  : result.moisture,
    imageName : imageName ?? "N/A",
    imageBlob : imageBlob ?? null,   // native Blob — no base64 encoding needed
    model     : result.model,
    simulated : result.simulated,
    status    : result.status ?? "completed",
    timestamp : result.timestamp,
    savedAt   : new Date().toISOString(),
  });
}

/**
 * Load all inspections for a user, newest first.
 * @param {string} userEmail
 * @returns {Promise<Array>}
 */
export async function getInspections(userEmail){
  const db  = await getDb();
  const all = await db.getAllFromIndex("inspections","userEmail",userEmail);
  return all.sort((a,b)=>new Date(b.timestamp)-new Date(a.timestamp));
}

/**
 * Delete a single inspection record by its DB id.
 * @param {number} id
 */
export async function deleteInspection(id){
  const db = await getDb();
  return db.delete("inspections", id);
}
