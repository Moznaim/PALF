"use client";
import {useState} from "react";
import {useRouter} from "next/navigation";
import {validate, register, signIn} from "../../lib/auth";

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
      if(reg){ await register(v); } else { await signIn(v); }
      router.push("/dashboard");
    } catch(err){
      setErrs({form: err.message});
      setBusy(false);
    }
  }

  return(
    <main className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-slate-50 to-emerald-50/40">
      <div className="w-full max-w-[420px]">

        {/* Logo / Brand header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-emerald-600 shadow-lg mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 3C7.5 3 4 7.5 4 12c0 3 2 6 5 7.5M12 3c4.5 0 8 4.5 8 9 0 3-2 6-5 7.5M12 3v18M7 8.5c1.5 1 3 1.5 5 1.5s3.5-.5 5-1.5"/>
            </svg>
          </div>
          <h1 className="font-head text-2xl font-bold text-slate-900">PALF-Vision AI</h1>
          <p className="text-sm text-slate-500 mt-1">Pineapple Leaf Fiber Quality Grading System</p>
        </div>

        <div className="card p-7 shadow-md">
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
            {reg&&<Field id="name"    label="Full name"         error={errs.name}     autoComplete="name"/>}
            <Field id="email"         type="email" label="Email address" error={errs.email}  autoComplete="email" placeholder="name@example.com"/>
            <Field id="password"      type="password" label="Password" error={errs.password}
              autoComplete={reg?"new-password":"current-password"}/>
            {reg&&<Field id="confirm" type="password" label="Confirm password" error={errs.confirm}
              autoComplete="new-password"/>}

            {errs.form&&(
              <div className="rounded bg-red-50 border border-red-200 px-3 py-2">
                <p role="alert" className="text-xs text-red-700">{errs.form}</p>
              </div>)}

            <button className="btn-p w-full py-2.5" disabled={busy}>
              {busy?(reg?"Creating account…":"Signing in…"):reg?"Create account":"Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-slate-400">
          Credentials are stored securely in your local browser · No internet required
        </p>
      </div>
    </main>);
}
