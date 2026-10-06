"use client";
import {useState} from "react";
import {useRouter} from "next/navigation";
import {validate, register, signIn, authMode} from "../../lib/auth";

function Field({id,label,error,...p}){return(
  <div>
    <label htmlFor={id} className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
    <input id={id} name={id} className="field" aria-invalid={!!error}
      aria-describedby={error?id+"-e":undefined} {...p}/>
    {error&&<p id={id+"-e"} role="alert" className="text-xs text-red-700 mt-1">{error}</p>}
  </div>);}

export default function Login(){
  const router   = useRouter();
  const [mode,setMode]   = useState("login");
  const [errs,setErrs]   = useState({});
  const [busy,setBusy]   = useState(false);
  const reg = mode==="register";

  async function submit(e){
    e.preventDefault();
    const v = Object.fromEntries(new FormData(e.currentTarget));
    const er = validate(v, reg); setErrs(er);
    if(Object.keys(er).length) return;
    setBusy(true);
    try{
      if(reg){
        await register(v);
      } else {
        await signIn(v);
      }
      router.push("/dashboard");
    } catch(err){
      setErrs({form: err.message});
      setBusy(false);
    }
  }

  return(
    <main className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-[420px]">
        <div className="card p-8">
          <h1 className="font-head text-xl font-bold">PALF-Vision AI</h1>
          <p className="text-sm text-slate-500 mb-5">Pineapple leaf fiber grading system</p>

          {/* tab switcher */}
          <div role="tablist" className="grid grid-cols-2 p-1 mb-5 bg-slate-100 rounded">
            {["login","register"].map(m=>(
              <button key={m} role="tab" aria-selected={mode===m} type="button"
                onClick={()=>{setMode(m);setErrs({})}}
                className={`py-1.5 text-xs font-semibold rounded transition-colors
                  ${mode===m?"bg-white shadow-sm text-slate-800":"text-slate-500"}`}>
                {m==="login"?"Log in":"Register"}
              </button>))}
          </div>

          <form onSubmit={submit} noValidate className="space-y-3.5" key={mode}>
            {reg&&<Field id="name"    label="Full name"        error={errs.name}     autoComplete="name"/>}
            <Field id="email"         type="email" label="Email" error={errs.email}  autoComplete="email" placeholder="name@example.com"/>
            <Field id="password"      type="password" label="Password" error={errs.password}
              autoComplete={reg?"new-password":"current-password"}/>
            {reg&&<Field id="confirm" type="password" label="Confirm password" error={errs.confirm}
              autoComplete="new-password"/>}

            {errs.form&&(
              <div className="rounded bg-red-50 border border-red-200 px-3 py-2">
                <p role="alert" className="text-xs text-red-700">{errs.form}</p>
              </div>)}

            <button className="btn-p w-full" disabled={busy}>
              {busy?(reg?"Creating account…":"Signing in…"):reg?"Create account":"Sign in"}
            </button>
          </form>
        </div>

        {/* mode badge */}
        <p className="mt-3 text-center chip border-emerald-200 bg-emerald-50 text-emerald-800 w-full justify-center">
          {authMode} · data stored offline in your browser
        </p>
      </div>
    </main>);
}
