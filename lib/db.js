/**
 * db.js  –  IndexedDB setup via idb
 *
 * Database name : palf_vision
 * Version       : 1
 *
 * Object stores
 * ─────────────
 *  users
 *    keyPath        : id  (auto-increment)
 *    index          : email  (unique)
 *    fields         : id, email, name, passwordHash, createdAt
 *
 *  inspections
 *    keyPath        : id  (auto-increment)
 *    index          : userEmail, timestamp
 *    fields         : id, userEmail, grade, confidence, moisture,
 *                     imageName, imageBlob (Blob|null), model,
 *                     simulated, status, timestamp, savedAt
 */

import {openDB} from "idb";

const DB_NAME    = "palf_vision";
const DB_VERSION = 1;

let _db = null;

/** Returns a cached (or newly opened) database instance. */
export async function getDb(){
  if(_db) return _db;
  _db = await openDB(DB_NAME, DB_VERSION, {
    upgrade(db){
      /* ── users ── */
      if(!db.objectStoreNames.contains("users")){
        const users = db.createObjectStore("users",{keyPath:"id",autoIncrement:true});
        users.createIndex("email","email",{unique:true});
      }
      /* ── inspections ── */
      if(!db.objectStoreNames.contains("inspections")){
        const ins = db.createObjectStore("inspections",{keyPath:"id",autoIncrement:true});
        ins.createIndex("userEmail","userEmail");
        ins.createIndex("timestamp","timestamp");
      }
    },
  });
  return _db;
}
