"use client";
import {useEffect,useState,useRef,useCallback} from "react";
import {useRouter} from "next/navigation";
import {getSession,signOut} from "../../lib/auth";
import {MODE,validateImage,validateMoisture,classify,
        saveInspection,getInspections,deleteInspection,GRADES} from "../../lib/inspection";
import {generateInspectionPDF, printInspectionReceipt} from "../../lib/pdfReport";
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

// export async function saveInspection({
//   userEmail,
//   result,
//   imageName,
//   imageBlob
// }) {
//   const db = await getDb();

//   return db.add("inspections", {
//     userEmail,

//     grade: result.grade,
//     confidence: result.confidence ?? null,
//     moisture: result.moisture,

//     // NEW
//     visualMetrics: result.visual_metrics ?? null,

//     imageName: imageName ?? "N/A",
//     imageBlob: imageBlob ?? null,
//     model: result.model,
//     simulated: result.simulated,
//     status: result.status ?? "completed",
//     timestamp: result.timestamp,
//     savedAt: new Date().toISOString(),
//   });
// }

/* ── main component ─────────────────────────────────────────────── */
export default function Dashboard(){
  const router=useRouter();
  const [user,setUser]=useState(null);
  const [tab,setTab]=useState("overview");
  const [dbReady,setDbReady]=useState(false);

  // Dashboard statistics
  const formatMetric = (value, digits = 2) => {
    if (
      value === null ||
      value === undefined ||
      !Number.isFinite(Number(value))
    ) {
      return "—";
    }

    return Number(value).toFixed(digits);
  };


  
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

  /* thermal print state */
  const [printing, setPrinting]      = useState(false);
  const [printStatus, setPrintStatus]= useState(null);

  const handlePrint = async (record) => {
    if (!record || printing) return;
    setPrinting(true);
    setPrintStatus(null);
    try {
      const res = await printInspectionReceipt({
        result: record,
        user,
        imageName: record.imageName || fileName || "N/A",
      });
      if (res?.success) {
        setPrintStatus("✓ Receipt printed to /dev/usb/lp0!");
        setTimeout(() => setPrintStatus(null), 4000);
      }
    } finally {
      setPrinting(false);
    }
  };

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


/* ── derived ───────────────────────────────────────── */

/* ── derived ───────────────────────────────── */

const visualMetrics =
  result?.visual_metrics ??
  result?.visualMetrics ??
  null;

const colorAnalysis =
  result?.color_analysis ??
  result?.colorAnalysis ??
  null;

const textureAnalysis =
  result?.texture_analysis ??
  result?.textureAnalysis ??
  null;

const topColorMatch =
  colorAnalysis?.candidate_matches?.find((m) => m.is_candidate) ??
  colorAnalysis?.candidate_matches?.[0] ??
  null;

const matchedColorLabel = topColorMatch?.color_label ?? null;

const totalInspections = history?.length ?? 0;

const lastGrade = history?.[0]?.grade ?? "—";

const gradeCounts = GRADES.reduce(
  (a, g) => ({
    ...a,
    [g]: history.filter(h => h.grade === g).length
  }),
  {}
);

const busy = ["VALIDATING", "PROCESSING", "CLASSIFYING"].includes(state);

const sim = MODE.model === "MOCK";

  /* ── camera handlers ────────────────────────────────────────── */
  async function openCamera(){
    setCameraErr(null);
    setPreview(null);
    if(CAMERA_MODE === "PICAMERA"){
      setCameraOn(true);
      setState("ACQUIRING");
      return;
    }
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
    if(streamRef.current){
      stopWebcam(streamRef.current);
      streamRef.current=null;
    }
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
        <div className="flex items-center gap-2.5 min-w-0">
          {/* leaf icon */}
          <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 3C7.5 3 4 7.5 4 12c0 3 2 6 5 7.5M12 3c4.5 0 8 4.5 8 9 0 3-2 6-5 7.5M12 3v18M7 8.5c1.5 1 3 1.5 5 1.5s3.5-.5 5-1.5"/>
            </svg>
          </div>
          <div className="flex flex-col leading-tight">
            <span className="font-head font-bold text-slate-900 text-sm">PALF-Vision AI</span>
            <span className="hidden sm:block text-[10px] text-slate-400 tracking-wide">Pineapple Leaf Fiber Grading System</span>
          </div>
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
                sub={dbReady?"Stored offline on this device":"Loading…"}/>
              <StatCard label="Last grade recorded" value={lastGrade}
                sub={history[0]?new Date(history[0].timestamp).toLocaleTimeString("en-PH"):"No inspections yet"}/>
              <StatCard label="Image capture" value={CAMERA_MODE==="PICAMERA"?"Raspberry Pi Cam":CAMERA_MODE==="WEBCAM"?"Webcam":"Camera"} accent="text-slate-700" sub="Live capture ready"/>
              <StatCard label="Moisture input" value={DEVICE_MODE==="MOCK"?"Manual entry":DEVICE_MODE==="ESP32_SERIAL"?"ESP32 Sensor":"ESP32 (Wi-Fi)"} accent={DEVICE_MODE==="MOCK"?"text-slate-600":"text-emerald-700"} sub={DEVICE_MODE==="MOCK"?"Type the reading below":"Auto-read from sensor"}/>
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
                                    title="View full inspection details and measurements"
                                    className="text-xs text-slate-700 border border-slate-300 bg-white hover:bg-slate-100 rounded px-1.5 py-0.5 transition-colors"
                                    onClick={()=>{setResult(h);setTab("inspect");}}>
                                    View
                                  </button>
                                  <button
                                    title="Print thermal receipt (silent)"
                                    disabled={printing}
                                    className="text-xs text-slate-700 border border-slate-300 bg-white hover:bg-slate-100 rounded px-1.5 py-0.5 transition-colors disabled:opacity-50"
                                    onClick={()=>handlePrint(h)}>
                                    ⎙
                                  </button>
                                  <button
                                    title="Download receipt PDF"
                                    className="text-xs text-emerald-700 border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 rounded px-2 py-0.5 transition-colors"
                                    onClick={()=>generateInspectionPDF({result:h,user,imageName:h.imageName||"N/A"})}>
                                    ↓ Slip
                                  </button>
                                  <button
                                    title="Delete record"
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
            <Card title="System Overview">
              <div className="grid sm:grid-cols-4 gap-3 text-sm">
                {[
                  {label:"Authentication",  icon:"🔐", value:"Offline · Browser storage",  ok:true,  note:"Credentials stored securely on device"},
                  {label:"Image Capture",   icon:"📷", value:CAMERA_MODE==="PICAMERA"?"Raspberry Pi Camera":CAMERA_MODE==="WEBCAM"?"Webcam (USB / Built-in)":"Camera", ok:true, note:"Ready for fiber image acquisition"},
                  {label:"Moisture Sensor", icon:"💧", value:DEVICE_MODE==="MOCK"?"Manual input":DEVICE_MODE==="ESP32_SERIAL"?"ESP32 Sensor (USB)":"ESP32 Sensor (Wi-Fi)",
                   ok:DEVICE_MODE!=="MOCK", note:DEVICE_MODE==="MOCK"?"Enter reading via input field":"Live sensor connected via ESP32"},
                  {label:"AI Classifier",   icon:"🧠", value:MODE.model==="MOCK"?"Demo mode (offline)":"PyTorch Neural Network",
                   ok:true, note:MODE.model==="MOCK"?"Classification engine ready":"ResNet / EfficientNet hybrid model active"},
                ].map(s=>(
                  <div key={s.label} className="flex items-start gap-2.5 p-3 rounded-lg bg-slate-50 border border-slate-200">
                    <span className="text-lg leading-none mt-0.5">{s.icon}</span>
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-800">{s.label}</p>
                      <p className="text-xs text-slate-600 mt-0.5">{s.value}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{s.note}</p>
                    </div>
                    <span className={`ml-auto flex-shrink-0 w-2 h-2 rounded-full mt-1.5 ${s.ok?"bg-emerald-500":"bg-slate-300"}`}/>
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

                {/* PICAMERA live MJPEG stream */}
                {cameraOn && !preview && CAMERA_MODE === "PICAMERA" && (
                  <img
                    src="/api/stream"
                    alt="Live Raspberry Pi camera feed"
                    className="w-full h-full object-contain"
                    onError={() => setCameraErr("Cannot connect to camera stream. Is camera service running?")}
                  />
                )}

                {/* WEBCAM live video feed (shown when webcam is open on laptop) */}
                {CAMERA_MODE === "WEBCAM" && (
                  <video
                    ref={videoRef}
                    className={`w-full h-full object-contain ${cameraOn && !preview ? "block" : "hidden"}`}
                    playsInline muted
                    aria-label="Live camera feed"
                  />
                )}

                {/* static image preview (uploaded or captured still) */}
                {preview && (
                  <img src={preview} alt="Inspection image" className="w-full h-full object-contain"/>
                )}

                {/* center-crop alignment guide when camera is streaming */}
                {cameraOn && !preview && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="w-56 h-56 border-2 border-dashed border-emerald-400/80 rounded-2xl flex items-end justify-center pb-2 bg-emerald-500/5 shadow-sm">
                      <span className="text-[11px] font-medium text-emerald-200 bg-black/75 px-2 py-0.5 rounded shadow">
                        Align fiber inside box
                      </span>
                    </div>
                  </div>
                )}

                {/* idle placeholder */}
                {!cameraOn && !preview && (
                  <p className="text-sm text-slate-400">No image acquired</p>
                )}

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

                {/* sensor status note */}
                <p className="text-xs text-slate-400 mt-2">
                  {DEVICE_MODE==="MOCK"
                    ?"Type the moisture percentage for this fiber sample."
                    :"Sensor connected — click the button to read the current moisture level."}
                </p>
              </Card>

              {/* ── classification card ── */}
              <Card title="Classification">

                <button className="btn-p w-full" onClick={run} disabled={busy||!file}>
                  {busy?"Classifying…":"Classify fiber"}
                </button>
                {err.form&&<p role="alert" className="text-xs text-red-700 mt-2">{err.form}</p>}

                {result?(<>
                    {/* ── Grade hero block ── */}
                    {(()=>{
                      const g = result.grade;
                      const styles = {
                        Excellent: "bg-emerald-600 text-white border-emerald-700",
                        Good:      "bg-sky-600 text-white border-sky-700",
                        Fair:      "bg-amber-500 text-white border-amber-600",
                      };
                      const cls = styles[g] || "bg-slate-700 text-white border-slate-800";
                      return(
                        <div className={`mt-4 rounded-lg border-2 p-4 text-center ${cls}`}>
                          <p className="text-xs font-semibold uppercase tracking-widest opacity-80 mb-0.5">Predicted Grade</p>
                          <p className="font-head font-bold text-4xl tracking-tight">{g}</p>
                          {result.confidence&&(
                            <p className="text-sm mt-1 opacity-90 num">Confidence: {result.confidence}</p>
                          )}
                        </div>
                      );
                    })()}

                    <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm">
                      <dt className="text-slate-500">Moisture content</dt>
                      <dd className="num">{result.moisture} %</dd>
                      <dt className="text-slate-500">Model used</dt>
                      <dd className="num text-xs">{result.model}</dd>
                      <dt className="text-slate-500">Fiber image</dt>
                      <dd className="num text-xs truncate">{result.imageName}</dd>
                      <dt className="text-slate-500">Inspected at</dt>
                      <dd className="num text-xs">{new Date(result.timestamp).toLocaleString("en-PH")}</dd>
                      <dt className="text-slate-500">Record saved</dt>
                      <dd className="num text-emerald-700 text-xs">✓ Stored on device</dd>
                    </dl>
                    {/* ── MEASURED COLOR & BUNDLE TEXTURE CHARACTERISTICS ── */}
                    {visualMetrics ? (
                      <div className="mt-4 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                          <p className="text-xs font-semibold text-slate-800 tracking-wide uppercase">
                            Bundle Visual Measurements
                          </p>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                            {visualMetrics.status === "ok" ? "Valid ROI" : (visualMetrics.status ?? "Processed")}
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {/* 1. COLOR MEASUREMENTS (CIELAB & CANDIDATE FIT) */}
                          <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                            <div className="flex items-center justify-between mb-2">
                              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                Color {matchedColorLabel ? `(${matchedColorLabel})` : "(CIELAB)"}
                              </h3>
                              <div
                                title={`Representative color swatch: ${visualMetrics.color?.hex_color || "#e0d8cc"}`}
                                className="w-5 h-5 rounded-full border border-slate-300 shadow-inner"
                                style={{ backgroundColor: visualMetrics.color?.hex_color || "#e0d8cc" }}
                              />
                            </div>
                            <p className="text-[10px] text-slate-400 mb-2">
                              {topColorMatch?.pns_pid ? `${topColorMatch.pns_pid} Candidate Reference Range` : "ISO/CIE 11664-4:2019 D65"}
                            </p>
                            <dl className="space-y-2 text-xs">
                              <div className="flex justify-between items-baseline">
                                <div>
                                  <dt className="text-slate-600 font-medium">Lightness (L*)</dt>
                                  {topColorMatch?.channel_details?.L_star?.reference_p05 != null && (
                                    <span className="text-[10px] text-slate-400 block font-mono">
                                      ref: {formatMetric(topColorMatch.channel_details.L_star.reference_p05, 1)} – {formatMetric(topColorMatch.channel_details.L_star.reference_p95, 1)}
                                    </span>
                                  )}
                                </div>
                                <dd className="num font-semibold text-right">
                                  {formatMetric(visualMetrics.color?.l_star ?? visualMetrics.color?.mean_L_star)}
                                  {visualMetrics.color?.l_star_std != null && (
                                    <span className="text-[10px] text-slate-400 font-normal ml-1">
                                      ±{formatMetric(visualMetrics.color.l_star_std)}
                                    </span>
                                  )}
                                </dd>
                              </div>

                              <div className="flex justify-between items-baseline">
                                <div>
                                  <dt className="text-slate-600 font-medium">Red-Green (a*)</dt>
                                  {topColorMatch?.channel_details?.a_star?.reference_p05 != null && (
                                    <span className="text-[10px] text-slate-400 block font-mono">
                                      ref: {formatMetric(topColorMatch.channel_details.a_star.reference_p05, 1)} – {formatMetric(topColorMatch.channel_details.a_star.reference_p95, 1)}
                                    </span>
                                  )}
                                </div>
                                <dd className="num font-semibold text-right">
                                  {formatMetric(visualMetrics.color?.a_star ?? visualMetrics.color?.mean_a_star)}
                                  {visualMetrics.color?.a_star_std != null && (
                                    <span className="text-[10px] text-slate-400 font-normal ml-1">
                                      ±{formatMetric(visualMetrics.color.a_star_std)}
                                    </span>
                                  )}
                                </dd>
                              </div>

                              <div className="flex justify-between items-baseline">
                                <div>
                                  <dt className="text-slate-600 font-medium">Yellow-Blue (b*)</dt>
                                  {topColorMatch?.channel_details?.b_star?.reference_p05 != null && (
                                    <span className="text-[10px] text-slate-400 block font-mono">
                                      ref: {formatMetric(topColorMatch.channel_details.b_star.reference_p05, 1)} – {formatMetric(topColorMatch.channel_details.b_star.reference_p95, 1)}
                                    </span>
                                  )}
                                </div>
                                <dd className="num font-semibold text-right">
                                  {formatMetric(visualMetrics.color?.b_star ?? visualMetrics.color?.mean_b_star)}
                                  {visualMetrics.color?.b_star_std != null && (
                                    <span className="text-[10px] text-slate-400 font-normal ml-1">
                                      ±{formatMetric(visualMetrics.color.b_star_std)}
                                    </span>
                                  )}
                                </dd>
                              </div>

                              <div className="flex justify-between items-baseline pt-0.5">
                                <dt className="text-slate-600 font-medium">Chroma (C*)</dt>
                                <dd className="num font-semibold text-right">
                                  {formatMetric(visualMetrics.color?.chroma ?? visualMetrics.color?.mean_chroma)}
                                </dd>
                              </div>
                            </dl>
                            <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                              Camera-derived measurements · Calibration pending
                            </p>
                          </section>

                          {/* 2. TEXTURE MEASUREMENTS (GLCM) */}
                          <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-0.5">
                              Bundle Texture
                            </h3>
                            <p className="text-[10px] text-slate-400 mb-2">
                              GLCM (16 levels · 4 directions avg)
                            </p>
                            <dl className="space-y-1.5 text-xs">
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Contrast</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.texture?.contrast, 4)}
                                </dd>
                              </div>
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Homogeneity</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.texture?.homogeneity, 4)}
                                </dd>
                              </div>
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Energy (√ASM)</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.texture?.energy, 4)}
                                </dd>
                              </div>
                              <div className="flex justify-between">
                                <dt className="text-slate-500">ASM (Angular 2nd Moment)</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.texture?.asm, 4)}
                                </dd>
                              </div>
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Entropy</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.texture?.entropy, 4)}
                                </dd>
                              </div>
                            </dl>
                            <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                              Haralick spatial gray-level distribution
                            </p>
                          </section>

                          {/* 3. BUNDLE UNIFORMITY (3x3 REGIONAL ANALYSIS) */}
                          <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                            <div className="flex items-center justify-between mb-0.5">
                              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                Bundle Uniformity
                              </h3>
                              <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded">
                                {visualMetrics.uniformity?.valid_regions ?? 0}/9 regions
                              </span>
                            </div>
                            <p className="text-[10px] text-slate-400 mb-2">
                              3 × 3 Regional Grid Analysis
                            </p>
                            <dl className="space-y-1.5 text-xs">
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Contrast (Mean ± SD)</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.uniformity?.contrast_mean, 4)}
                                  <span className="text-[10px] text-slate-400 font-normal ml-1">
                                    ±{formatMetric(visualMetrics.uniformity?.contrast_std, 4)}
                                  </span>
                                </dd>
                              </div>
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Homogeneity (Mean ± SD)</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.uniformity?.homogeneity_mean, 4)}
                                  <span className="text-[10px] text-slate-400 font-normal ml-1">
                                    ±{formatMetric(visualMetrics.uniformity?.homogeneity_std, 4)}
                                  </span>
                                </dd>
                              </div>
                            </dl>
                            <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                              Regional texture variation · Not physical softness
                            </p>
                          </section>

                          {/* 4. IMAGE QUALITY & FOCUS */}
                          <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                            <div className="flex items-center justify-between mb-0.5">
                              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                Image Quality
                              </h3>
                              <span className="text-[10px] font-mono text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded">
                                {visualMetrics.image_quality?.status || "unvalidated"}
                              </span>
                            </div>
                            <p className="text-[10px] text-slate-400 mb-2">
                              Laplacian Variance Focus Metric
                            </p>
                            <dl className="space-y-1.5 text-xs">
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Sharpness Score</dt>
                                <dd className="num font-semibold">
                                  {formatMetric(visualMetrics.image_quality?.laplacian_variance, 1)}
                                </dd>
                              </div>
                              <div className="flex justify-between">
                                <dt className="text-slate-500">Optical Validity</dt>
                                <dd className="text-emerald-700 font-medium">
                                  {Number(visualMetrics.image_quality?.laplacian_variance) > 50 ? "Clear Focus" : "Check Focus"}
                                </dd>
                              </div>
                            </dl>
                            <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                              Optical sharpness only · Not physical fiber roughness
                            </p>
                          </section>
                        </div>
                        {/* ── TEXTURE ANALYSIS (Experimental Threshold Assessment) ── */}
                        {textureAnalysis && (
                          <div className="mt-3 space-y-3">
                            <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                              <p className="text-xs font-semibold text-slate-800 tracking-wide uppercase">
                                Texture Analysis
                              </p>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                                textureAnalysis.status === "available"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-amber-50 text-amber-700"
                              }`}>
                                {textureAnalysis.status === "available" ? "Assessment Available" : (textureAnalysis.status ?? "Pending")}
                              </span>
                            </div>

                            {/* Texture Assessment Result */}
                            {textureAnalysis.status === "available" && textureAnalysis.predicted_texture && (
                              <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2">
                                  Texture Assessment
                                </h3>
                                <dl className="space-y-1.5 text-xs">
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Predicted Texture</dt>
                                    <dd className="font-bold text-slate-800">
                                      {textureAnalysis.display_name || textureAnalysis.predicted_texture}
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Associated Grade</dt>
                                    <dd className="font-semibold text-slate-700">
                                      {textureAnalysis.associated_grade ?? "—"}
                                    </dd>
                                  </div>
                                  {textureAnalysis.pns_code && (
                                    <div className="flex justify-between">
                                      <dt className="text-slate-500">PNS Reference</dt>
                                      <dd className="font-mono text-slate-600 text-[11px]">
                                        {textureAnalysis.pns_code}
                                      </dd>
                                    </div>
                                  )}
                                    <div className="flex justify-between">
                                      <dt className="text-slate-500">Rule Used</dt>
                                      <dd
                                        className="font-mono text-slate-600 text-[10px] max-w-[180px] text-right truncate"
                                        title={textureAnalysis.threshold_details?.rule_id ?? ""}
                                      >
                                        {textureAnalysis.threshold_details?.rule_id ?? "—"}
                                      </dd>
                                    </div>
                                    </dl>

                                    {/* Threshold Decision Path */}
                                    {Array.isArray(textureAnalysis.threshold_details?.decision_path) &&
                                      textureAnalysis.threshold_details.decision_path.length > 0 && (
                                        <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
                                          <h4 className="text-[11px] font-bold text-slate-700 uppercase tracking-wide">
                                            Threshold Decision Path
                                          </h4>

                                          <ol className="mt-2 space-y-1.5 list-decimal list-inside">
                                            {textureAnalysis.threshold_details.decision_path.map(
                                              (step, index) => (
                                                <li
                                                  key={`${index}-${step}`}
                                                  className="text-[11px] text-slate-600 leading-relaxed"
                                                >
                                                  {step}
                                                </li>
                                              )
                                            )}
                                          </ol>

                                          {textureAnalysis.warnings?.some((warning) =>
                                            warning.toLowerCase().includes("fallback rule")
                                          ) && (
                                            <p className="mt-2 text-[10px] text-amber-700">
                                              A fallback rule was used because a higher-priority feature
                                              was unavailable.
                                            </p>
                                          )}
                                        </div>
                                      )}

                                {/* CNN vs Texture disagreement notice */}
                                {result?.grade && textureAnalysis.associated_grade &&
                                  result.grade !== textureAnalysis.associated_grade && (
                                  <div className="mt-2 p-2 rounded bg-amber-50 border border-amber-200">
                                    <p className="text-[10px] text-amber-800">
                                      ⓘ Texture assessment differs from the CNN classification. Review the image-derived measurements.
                                    </p>
                                  </div>
                                )}
                                <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                                  Experimental candidate threshold · Does not alter CNN grade
                                </p>
                              </section>
                            )}
                                {/* Unavailable Texture Assessment */}
                                {textureAnalysis.status !== "available" && (
                                  <section className="rounded-lg border border-amber-200 bg-amber-50 p-3 mt-3">
                                    <h3 className="text-xs font-bold text-amber-800">
                                      Texture Assessment Unavailable
                                    </h3>

                                    <p className="mt-1 text-[11px] text-amber-700">
                                      {textureAnalysis.warnings?.[0] ??
                                        textureAnalysis.threshold_details?.decision_path?.[0] ??
                                        "Texture measurements could not be evaluated."}
                                    </p>
                                  </section>
                                )}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              {/* Fiber Orientation */}
                              <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-0.5">
                                  Fiber Orientation
                                </h3>
                                <p className="text-[10px] text-slate-400 mb-2">
                                  Structure Tensor Analysis
                                </p>
                                <dl className="space-y-1.5 text-xs">
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Orientation Conc.</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.structure_tensor?.orientation_concentration, 4)}
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Orientation Spread</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.structure_tensor?.orientation_spread_deg, 2)}°
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Regional Conc. (Mean ± SD)</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.structure_tensor?.orientation_concentration_regional_mean, 4)}
                                      {visualMetrics.structure_tensor?.orientation_concentration_regional_sd != null && (
                                        <span className="text-[10px] text-slate-400 font-normal ml-1">
                                          ±{formatMetric(visualMetrics.structure_tensor.orientation_concentration_regional_sd, 4)}
                                        </span>
                                      )}
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Regional Spread (Mean ± SD)</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.structure_tensor?.orientation_spread_deg_regional_mean, 2)}°
                                      {visualMetrics.structure_tensor?.orientation_spread_deg_regional_sd != null && (
                                        <span className="text-[10px] text-slate-400 font-normal ml-1">
                                          ±{formatMetric(visualMetrics.structure_tensor.orientation_spread_deg_regional_sd, 2)}°
                                        </span>
                                      )}
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Coherence</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.structure_tensor?.structure_tensor_mean_coherence, 4)}
                                    </dd>
                                  </div>
                                </dl>
                                <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                                  Axial circular statistics · Fiber direction consistency
                                </p>
                              </section>

                              {/* Directional Pattern (Gabor) */}
                              <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-0.5">
                                  Directional Pattern
                                </h3>
                                <p className="text-[10px] text-slate-400 mb-2">
                                  Gabor Filter Bank (6 orientations)
                                </p>
                                <dl className="space-y-1.5 text-xs">
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Anisotropy</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.gabor?.gabor_response_anisotropy, 4)}
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Mean Response</dt>
                                    <dd className="num font-semibold">
                                      {formatMetric(visualMetrics.gabor?.gabor_mean_response, 4)}
                                    </dd>
                                  </div>
                                  <div className="flex justify-between">
                                    <dt className="text-slate-500">Dominant Filter</dt>
                                    <dd className="num font-semibold">
                                      {visualMetrics.gabor?.gabor_dominant_filter_angle_deg != null ? `${visualMetrics.gabor.gabor_dominant_filter_angle_deg}°` : "—"}
                                    </dd>
                                  </div>
                                </dl>
                                <p className="text-[10px] text-slate-400 italic mt-2.5 pt-1.5 border-t border-slate-100">
                                  Directional response selectivity
                                </p>
                              </section>
                            </div>

                            <p className="text-[10px] text-slate-400 italic text-center">
                              Texture measurements describe visible arrangement and grayscale patterns · Not physical tactile hand
                            </p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mt-3 p-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 text-center">
                        <p className="text-xs text-slate-400">
                          Color and texture measurements not available for this inspection record.
                        </p>
                      </div>
                    )}
                    <div className="mt-4 flex flex-col gap-2">
                      <div className="grid grid-cols-2 gap-2">
                        <button className="btn-p w-full text-center disabled:opacity-50"
                          disabled={printing}
                          onClick={()=>handlePrint(result)}>
                          {printing ? "Printing..." : "⎙ Print receipt"}
                        </button>
                        <button className="btn-s w-full text-center"
                          onClick={()=>generateInspectionPDF({result,user,imageName:fileName})}>
                          ↓ Save PDF
                        </button>
                      </div>
                      {printStatus && (
                        <p className="text-xs text-emerald-700 text-center font-medium bg-emerald-50 border border-emerald-200 py-1 rounded">
                          {printStatus}
                        </p>
                      )}
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
