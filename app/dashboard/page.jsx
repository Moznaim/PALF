"use client";
import {useEffect,useState,useRef,useCallback} from "react";
import {useRouter} from "next/navigation";
import {getSession,signOut} from "../../lib/auth";
import {MODE,validateImage,validateMoisture,classify,
        saveInspection,getInspections,deleteInspection,GRADES} from "../../lib/inspection";
import {generateInspectionPDF} from "../../lib/pdfReport";
import {CAMERA_MODE,startWebcam,captureImage,stopWebcam} from "../../lib/camera";
import {readMoisture,hasSensor,DEVICE_MODE} from "../../lib/sensor";

/* ── small reusable pieces ─────────────────────────────────────── */
const Card=({title,right,children,className=""})=>(
  <section className={`card overflow-hidden ${className}`}>
    <header className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-slate-50">
      <h2 className="font-head text-sm font-semibold">{title}</h2>{right}
    </header>
    <div className="p-4">{children}</div>
  </section>);

const StatCard=({label,value,sub,accent="text-emerald-700"})=>(
  <div className="card p-4 flex flex-col gap-1">
    <span className="text-xs text-slate-500 font-medium">{label}</span>
    <span className={`num text-2xl font-bold ${accent}`}>{value}</span>
    {sub&&<span className="text-xs text-slate-400">{sub}</span>}
  </div>);

/* ── main component ─────────────────────────────────────────────── */
export default function Dashboard(){
  const router=useRouter();
  const [user,setUser]=useState(null);
  const [tab,setTab]=useState("overview");
  const [dbReady,setDbReady]=useState(false);

  /* inspection state */
  const [state,setState]=useState("IDLE");
  const [file,setFile]=useState(null);
  const [fileName,setFileName]=useState("N/A");
  const [preview,setPreview]=useState(null);
  const [moisture,setMoisture]=useState("");
  const [err,setErr]=useState({});
  const [result,setResult]=useState(null);
  const [history,setHistory]=useState([]);

  /* camera state */
  const videoRef   = useRef(null);                 // <video> DOM element
  const streamRef  = useRef(null);                 // active MediaStream
  const [cameraOn,setCameraOn]       = useState(false);
  const [cameraErr,setCameraErr]     = useState(null);
  const [capturing,setCapturing]     = useState(false);

  /* sensor state */
  const [sensorBusy,setSensorBusy]   = useState(false);
  const [sensorErr,setSensorErr]     = useState(null);

  /* ── load session + history ─────────────────────────────────── */
  useEffect(()=>{
    const s=getSession();
    if(!s){router.replace("/login");return;}
    setUser(s);
    getInspections(s.email).then(rows=>{setHistory(rows);setDbReady(true);});
  },[router]);

  /* cleanup: revoke preview URL + stop camera on unmount */
  useEffect(()=>()=>{
    if(preview) URL.revokeObjectURL(preview);
    stopWebcam(streamRef.current);
  },[]);

  if(!user) return null;

  /* ── derived ────────────────────────────────────────────────── */
  const totalInspections = history.length;
  const lastGrade        = history[0]?.grade??"—";
  const gradeCounts      = GRADES.reduce((a,g)=>({...a,[g]:history.filter(h=>h.grade===g).length}),{});
  const busy             = ["VALIDATING","PROCESSING","CLASSIFYING"].includes(state);
  const sim              = MODE.model==="MOCK"||MODE.device==="MOCK";

  /* ── camera handlers ────────────────────────────────────────── */
  async function openCamera(){
    setCameraErr(null);
    try{
      const stream = await startWebcam(videoRef.current);
      streamRef.current = stream;
      setCameraOn(true);
      setState("ACQUIRING");
    }catch(e){
      setCameraErr("Could not open camera: "+e.message);
    }
  }

  function closeCamera(){
    stopWebcam(streamRef.current);
    streamRef.current=null;
    setCameraOn(false);
    if(state==="ACQUIRING") setState("IDLE");
  }

  async function handleCapture(){
    setCapturing(true);
    setCameraErr(null);
    try{
      const {blob,name} = await captureImage(videoRef.current);

      /* validate the captured blob just like an uploaded file */
      const mockFile = new File([blob], name, {type:"image/jpeg"});
      const m = validateImage(mockFile);
      if(m){setCameraErr(m);setCapturing(false);return;}

      /* build preview URL */
      if(preview) URL.revokeObjectURL(preview);
      const url = URL.createObjectURL(blob);
      setPreview(url);
      setFile(mockFile);
      setFileName(name);
      setResult(null);
      setState(moisture?"MOISTURE_READY":"IMAGE_READY");

      /* stop stream after capture (saves resources) */
      closeCamera();
    }catch(e){
      setCameraErr("Capture failed: "+e.message);
    }finally{
      setCapturing(false);
    }
  }

  /* ── image upload handler ───────────────────────────────────── */
  function pickImage(f){
    const m=validateImage(f);setErr(e=>({...e,image:m}));
    if(m)return;
    if(preview) URL.revokeObjectURL(preview);
    setFile(f);setFileName(f.name);setPreview(URL.createObjectURL(f));setResult(null);
    setState(moisture?"MOISTURE_READY":"IMAGE_READY");
    closeCamera(); // close live feed if open
  }

  /* ── moisture sensor read ───────────────────────────────────── */
  async function handleReadSensor(){
    setSensorBusy(true);setSensorErr(null);
    try{
      const val = await readMoisture();
      if(val===null){setSensorErr("Sensor returned no value.");return;}
      setMoisture(String(val.toFixed(1)));
      setErr(x=>({...x,moisture:null}));
      if(file&&state==="IMAGE_READY") setState("MOISTURE_READY");
    }catch(e){
      setSensorErr(e.message);
    }finally{
      setSensorBusy(false);
    }
  }

  /* ── classify ───────────────────────────────────────────────── */
  async function run(){
    setState("VALIDATING");
    const er={image:validateImage(file),moisture:validateMoisture(moisture)};setErr(er);
    if(er.image||er.moisture)return setState("ERROR");
    try{
      setState("CLASSIFYING");
      const r=await classify({file,moisture});
      const dbId=await saveInspection({
        userEmail:user.email,result:r,imageName:fileName,imageBlob:file,
      });
      const record={...r,id:dbId,imageName:fileName,imageBlob:file};
      setResult(record);
      setHistory(h=>[record,...h]);
      setState("RESULT");
    }catch(x){setErr({form:x.message});setState("ERROR");}
  }

  async function removeInspection(id){
    await deleteInspection(id);
    setHistory(h=>h.filter(x=>x.id!==id));
  }

  /* ── render ─────────────────────────────────────────────────── */
  return(
    <div className="min-h-screen">

      {/* ── top nav ── */}
      <header className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-slate-200 px-4 md:px-6 h-14 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-head font-bold">PALF-Vision AI</span>
          {sim&&<span className="chip border-amber-200 bg-amber-50 text-amber-800">Simulation</span>}
        </div>
        <nav className="hidden sm:flex items-center gap-1">
          {["overview","inspect"].map(t=>(
            <button key={t} onClick={()=>setTab(t)}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors
                ${tab===t?"bg-emerald-600 text-white":"text-slate-600 hover:bg-slate-100"}`}>
              {t==="overview"?"Overview":"New Inspection"}
            </button>))}
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden sm:inline text-slate-600">{user.name}</span>
          <button className="btn-s !py-1" onClick={()=>{signOut();stopWebcam(streamRef.current);router.push("/login")}}>
            Sign out
          </button>
        </div>
      </header>

      {/* ── mobile tab bar ── */}
      <div className="sm:hidden flex border-b border-slate-200 bg-white">
        {["overview","inspect"].map(t=>(
          <button key={t} onClick={()=>setTab(t)}
            className={`flex-1 py-2.5 text-xs font-semibold transition-colors
              ${tab===t?"border-b-2 border-emerald-600 text-emerald-700":"text-slate-500"}`}>
            {t==="overview"?"Overview":"New Inspection"}
          </button>))}
      </div>

      <main className="p-4 md:p-6 max-w-screen-xl mx-auto">

        {/* ════════════════ OVERVIEW TAB ════════════════ */}
        {tab==="overview"&&(
          <div className="grid gap-4">

            {/* welcome banner */}
            <div className="card p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <p className="font-head font-bold text-lg">Welcome back, {user.name} 👋</p>
                <p className="text-sm text-slate-500 mt-0.5">
                  {new Date().toLocaleDateString("en-PH",{weekday:"long",year:"numeric",month:"long",day:"numeric"})}
                </p>
              </div>
              <button className="btn-p self-start sm:self-center whitespace-nowrap" onClick={()=>setTab("inspect")}>
                + New Inspection
              </button>
            </div>

            {/* stat row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="Total inspections" value={totalInspections}
                sub={dbReady?"Persisted offline":"Loading…"}/>
              <StatCard label="Last grade" value={lastGrade}
                sub={history[0]?new Date(history[0].timestamp).toLocaleTimeString():"No inspections yet"}/>
              <StatCard label="Camera" value={CAMERA_MODE} accent="text-slate-700" sub="Image source"/>
              <StatCard label="Sensor" value={DEVICE_MODE} accent={DEVICE_MODE==="MOCK"?"text-amber-600":"text-emerald-700"} sub="Moisture input"/>
            </div>

            {/* grade breakdown + history */}
            <div className="grid md:grid-cols-3 gap-4">
              <Card title="Grade breakdown" className="md:col-span-1">
                {totalInspections===0
                  ?<p className="text-xs text-slate-500">No inspections yet. Run one to see the breakdown.</p>
                  :<dl className="space-y-2">
                    {GRADES.map(g=>{
                      const pct=Math.round((gradeCounts[g]||0)/totalInspections*100);
                      return(<div key={g}>
                        <div className="flex justify-between text-xs mb-0.5">
                          <dt className="font-medium">{g}</dt>
                          <dd className="num text-slate-500">{gradeCounts[g]||0} ({pct}%)</dd>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full transition-all" style={{width:`${pct}%`}}/>
                        </div>
                      </div>);})}
                  </dl>}
              </Card>

              <Card title="Inspection history" className="md:col-span-2"
                right={totalInspections>0&&
                  <span className="num text-xs text-slate-500">
                    {totalInspections} record{totalInspections!==1?"s":""}
                  </span>}>
                {!dbReady
                  ?<p className="text-xs text-slate-500 animate-pulse">Loading from database…</p>
                  :totalInspections===0
                    ?(<div className="text-center py-6">
                        <p className="text-sm text-slate-500 mb-3">No inspections recorded yet.</p>
                        <button className="btn-p" onClick={()=>setTab("inspect")}>Start first inspection</button>
                      </div>)
                    :(<div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead><tr className="text-left text-xs text-slate-500">
                            <th className="pb-1.5">Time</th>
                            <th>Grade</th><th>Moisture</th><th>Confidence</th>
                            <th>Image</th><th>Source</th><th></th>
                          </tr></thead>
                          <tbody>{history.map(h=>(
                            <tr key={h.id} className="border-t border-slate-100 num">
                              <td className="py-1.5">{new Date(h.timestamp).toLocaleTimeString()}</td>
                              <td className="font-sans font-semibold">{h.grade}</td>
                              <td>{h.moisture}%</td>
                              <td>{h.confidence??"—"}</td>
                              <td className="max-w-[120px] truncate font-sans text-slate-500 text-xs">{h.imageName??"—"}</td>
                              <td>{h.simulated?"simulated":h.model}</td>
                              <td className="py-1 text-right">
                                <div className="flex items-center justify-end gap-1.5">
                                  <button
                                    className="text-xs text-emerald-700 border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 rounded px-2 py-0.5 transition-colors"
                                    onClick={()=>generateInspectionPDF({result:h,user,imageName:h.imageName||"N/A"})}>
                                    ↓ PDF
                                  </button>
                                  <button
                                    className="text-xs text-red-600 border border-red-200 bg-red-50 hover:bg-red-100 rounded px-2 py-0.5 transition-colors"
                                    onClick={()=>{if(confirm("Delete this inspection record?"))removeInspection(h.id);}}>
                                    ✕
                                  </button>
                                </div>
                              </td>
                            </tr>))}
                          </tbody>
                        </table>
                      </div>)}
              </Card>
            </div>

            {/* system status */}
            <Card title="System status">
              <div className="grid sm:grid-cols-4 gap-3 text-sm">
                {[
                  {label:"Auth & Storage", value:"OFFLINE_DB",       ok:true,  note:"IndexedDB — persists offline"},
                  {label:"Camera",         value:CAMERA_MODE,        ok:true,  note:CAMERA_MODE==="WEBCAM"?"getUserMedia (webcam/V4L2)":"RPi picamera2 backend"},
                  {label:"Moisture sensor",value:DEVICE_MODE,        ok:DEVICE_MODE!=="MOCK",
                   note:DEVICE_MODE==="MOCK"?"Manual input (no sensor)":
                        DEVICE_MODE==="ESP32_SERIAL"?"ESP32 via USB serial":
                        "ESP32 via WiFi HTTP"},
                  {label:"AI classifier",  value:MODE.model==="MOCK"?"Mock model":"PyTorch",
                   ok:MODE.model!=="MOCK", note:MODE.model==="MOCK"?"Random grades returned":"Real model active"},
                ].map(s=>(
                  <div key={s.label} className="flex items-start gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200">
                    <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${s.ok?"bg-emerald-500":"bg-amber-400"}`}/>
                    <div>
                      <p className="font-medium">{s.label}</p>
                      <p className="num text-xs text-slate-500">{s.value}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{s.note}</p>
                    </div>
                  </div>))}
              </div>
            </Card>
          </div>
        )}

        {/* ════════════════ INSPECT TAB ════════════════ */}
        {tab==="inspect"&&(
          <div className="grid gap-4 md:grid-cols-8 xl:grid-cols-12">

            {/* ── image / camera card ── */}
            <Card className="md:col-span-8 xl:col-span-7" title="Inspection image"
              right={<span className="chip border-slate-300 bg-white text-slate-700 num" aria-live="polite">{state}</span>}>

              {/* viewport: shows live camera feed OR captured/uploaded image */}
              <div className="aspect-[16/9] bg-[#020617] border border-slate-800 rounded-lg flex items-center justify-center overflow-hidden relative">

                {/* live video feed (shown when camera is open, hidden when not) */}
                <video
                  ref={videoRef}
                  className={`w-full h-full object-contain ${cameraOn?"block":"hidden"}`}
                  playsInline muted
                  aria-label="Live camera feed"
                />

                {/* static image preview */}
                {!cameraOn&&preview&&(
                  <img src={preview} alt="Inspection image" className="w-full h-full object-contain"/>)}

                {/* idle placeholder */}
                {!cameraOn&&!preview&&(
                  <p className="text-sm text-slate-400">No image acquired</p>)}

                {/* camera mode badge (top-right corner) */}
                <span className="absolute top-2 right-2 chip border-slate-600 bg-black/60 text-slate-300">
                  {CAMERA_MODE}
                </span>
              </div>

              {/* action buttons */}
              <div className="mt-3 flex flex-wrap items-center gap-2">

                {/* ── Upload (file picker) ── */}
                <label className="btn-s cursor-pointer">
                  Upload image
                  <input type="file" accept="image/jpeg,image/png" className="sr-only"
                    onChange={e=>pickImage(e.target.files[0])}/>
                </label>

                {/* ── Camera open/close ── */}
                {!cameraOn
                  ?<button className="btn-s" onClick={openCamera}>
                      📷 Open camera
                    </button>
                  :<button className="btn-s !border-red-300 !text-red-600 hover:!bg-red-50"
                      onClick={closeCamera}>
                      ✕ Close camera
                    </button>}

                {/* ── Capture (only when camera is on) ── */}
                {cameraOn&&(
                  <button className="btn-cv" onClick={handleCapture} disabled={capturing}>
                    {capturing?"Capturing…":"⊙ Capture"}
                  </button>)}

                {/* camera mode hint */}
                <span className="text-xs text-slate-400 w-full mt-1">
                  {CAMERA_MODE==="WEBCAM"
                    ?"Webcam via getUserMedia — on RPi set NEXT_PUBLIC_CAMERA_MODE=PICAMERA for libcamera."
                    :"RPi camera (picamera2 mode) — calls /api/capture on the backend."}
                </span>
              </div>

              {/* camera errors */}
              {cameraErr&&<p role="alert" className="text-xs text-red-700 mt-2">{cameraErr}</p>}
              {err.image&&<p role="alert" className="text-xs text-red-700 mt-2">{err.image}</p>}
            </Card>

            <div className="md:col-span-8 xl:col-span-5 grid gap-4 content-start">

              {/* ── moisture telemetry card ── */}
              <Card title="Moisture telemetry"
                right={
                  <span className={`chip ${DEVICE_MODE==="MOCK"
                    ?"border-amber-200 bg-amber-50 text-amber-800"
                    :"border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
                    {DEVICE_MODE==="MOCK"?"Manual entry":
                     DEVICE_MODE==="ESP32_SERIAL"?"ESP32 serial":
                     "ESP32 HTTP"}
                  </span>}>

                <label htmlFor="mc" className="block text-xs font-medium text-slate-700 mb-1">
                  Moisture reading (%)
                </label>
                <input id="mc" inputMode="decimal" className="field num text-2xl" value={moisture}
                  placeholder="--.-"
                  onChange={e=>{
                    setMoisture(e.target.value);
                    setErr(x=>({...x,moisture:null}));
                    setSensorErr(null);
                    if(file&&state==="IMAGE_READY") setState("MOISTURE_READY");
                  }}/>

                {err.moisture&&<p role="alert" className="text-xs text-red-700 mt-1">{err.moisture}</p>}
                {sensorErr&&<p role="alert" className="text-xs text-red-700 mt-1">{sensorErr}</p>}

                {/* Read from sensor button — shown only when a real sensor is configured */}
                {hasSensor()&&(
                  <button className="btn-s mt-2 w-full" onClick={handleReadSensor} disabled={sensorBusy}>
                    {sensorBusy?"Reading sensor…":"↻ Read from sensor"}
                  </button>)}

                {/* sensor mode hint */}
                <p className="text-xs text-slate-400 mt-2">
                  {DEVICE_MODE==="MOCK"
                    ?"Set NEXT_PUBLIC_DEVICE_MODE=ESP32_SERIAL or ESP32_HTTP to enable auto-read."
                    :DEVICE_MODE==="ESP32_SERIAL"
                    ?"Reading via backend /api/moisture (USB serial from ESP32)."
                    :`Reading directly from ESP32 at ${process.env.NEXT_PUBLIC_ESP32_URL||"(set NEXT_PUBLIC_ESP32_URL)"}.`}
                </p>
              </Card>

              {/* ── classification card ── */}
              <Card title="Classification"
                right={result&&<span className={`chip ${result.simulated
                  ?"border-amber-200 bg-amber-50 text-amber-800"
                  :"border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
                  {result.simulated?"Simulated":"Model output"}</span>}>

                <button className="btn-p w-full" onClick={run} disabled={busy||!file}>
                  {busy?"Classifying…":"Classify fiber"}
                </button>
                {err.form&&<p role="alert" className="text-xs text-red-700 mt-2">{err.form}</p>}

                {result?(<>
                    <dl className="mt-4 grid grid-cols-2 gap-y-2 text-sm">
                      <dt className="text-slate-500">Predicted grade</dt>
                      <dd className="font-head font-bold text-lg">{result.grade}</dd>
                      <dt className="text-slate-500">Confidence</dt>
                      <dd className="num">{result.confidence??"Not provided"}</dd>
                      <dt className="text-slate-500">Moisture</dt>
                      <dd className="num">{result.moisture}%</dd>
                      <dt className="text-slate-500">Image</dt>
                      <dd className="num text-xs truncate">{result.imageName}</dd>
                      <dt className="text-slate-500">Model</dt>
                      <dd className="num">{result.model}</dd>
                      <dt className="text-slate-500">Time</dt>
                      <dd className="num">{new Date(result.timestamp).toLocaleString()}</dd>
                      <dt className="text-slate-500">Saved</dt>
                      <dd className="num text-emerald-700 text-xs">✓ offline</dd>
                    </dl>
                    <div className="mt-4 flex flex-col gap-2">
                      <button className="btn-p w-full"
                        onClick={()=>generateInspectionPDF({result,user,imageName:fileName})}>
                        ↓ Save as PDF
                      </button>
                      <button className="btn-s w-full" onClick={()=>setTab("overview")}>
                        ← Back to overview
                      </button>
                    </div>
                  </>)
                  :<p className="text-xs text-slate-500 mt-3">
                    Add an image and a moisture reading, then click Classify.
                  </p>}
              </Card>
            </div>
          </div>
        )}

      </main>
    </div>);
}
