/**
 * auth.js  –  Offline-first authentication backed by IndexedDB.
 *
 * Passwords are hashed with SHA-256 via the browser's built-in
 * Web Crypto API — no extra library needed.
 *
 * Session (name + email) is kept in localStorage so the page can
 * restore it synchronously on load without hitting the DB first.
 */

import {getDb} from "./db";

const SESSION_KEY = "palf_session";
export const authMode = "OFFLINE_DB";

/* ── password hashing ─────────────────────────────────────────── */
async function hashPassword(password){
  const data = new TextEncoder().encode(password);
  const buf  = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map(b=>b.toString(16).padStart(2,"0")).join("");
}

/* ── validation (unchanged from before) ──────────────────────── */
export function validate({email,password,name,confirm}, register){
  const e={};
  if(register && !name?.trim())         e.name     = "Enter your full name.";
  if(!/^\S+@\S+\.\S+$/.test(email||""))e.email    = "Enter a valid email address.";
  if(!password||password.length<8)      e.password = "Password must be at least 8 characters.";
  if(register && password!==confirm)    e.confirm  = "Passwords do not match.";
  return e;
}

/* ── register ─────────────────────────────────────────────────── */
export async function register({email, name, password}){
  const db = await getDb();
  const existing = await db.getFromIndex("users","email",email.toLowerCase().trim());
  if(existing) throw new Error("An account with this email already exists.");

  const passwordHash = await hashPassword(password);
  const newUser = {
    email       : email.toLowerCase().trim(),
    name        : name.trim(),
    passwordHash,
    createdAt   : new Date().toISOString(),
  };
  const id = await db.add("users", newUser);
  const session = {id, email:newUser.email, name:newUser.name};
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

/* ── sign in ──────────────────────────────────────────────────── */
export async function signIn({email, password}){
  const db   = await getDb();
  const user = await db.getFromIndex("users","email",email.toLowerCase().trim());
  if(!user) throw new Error("No account found with this email address.");

  const hash = await hashPassword(password);
  if(hash !== user.passwordHash) throw new Error("Incorrect password.");

  const session = {id:user.id, email:user.email, name:user.name};
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

/* ── session helpers ──────────────────────────────────────────── */
export const getSession = ()=>{
  try{return JSON.parse(localStorage.getItem(SESSION_KEY));}
  catch{return null;}
};

export const signOut = ()=>localStorage.removeItem(SESSION_KEY);
