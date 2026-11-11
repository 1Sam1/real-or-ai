// Set this to the deployed API origin after the backend is configured.
const API_BASE = "";
const $ = (id) => document.getElementById(id);
let mode = "upload";
function chooseMode(next){mode=next;$("uploadPanel").hidden=next!=="upload";$("linkPanel").hidden=next!=="link";$("uploadTab").classList.toggle("active",next==="upload");$("linkTab").classList.toggle("active",next==="link");validate();}
$("uploadTab").addEventListener("click",()=>chooseMode("upload"));
$("linkTab").addEventListener("click",()=>chooseMode("link"));
$("videoFile").addEventListener("change",()=>{$("fileName").textContent=$("videoFile").files[0]?.name||"";validate();});
$("videoUrl").addEventListener("input",validate);
function validate(){$("analyseBtn").disabled=mode==="upload"?!$("videoFile").files.length:!$("videoUrl").value.trim();}
const key=()=>{const d=new Date();return "real-or-ai-demo-"+d.getFullYear()+"-"+(d.getMonth()+1)+"-"+d.getDate();};
function updateLimit(){const used=Number(localStorage.getItem(key())||0);$("usageText").textContent=Math.max(0,3-used)+" of 3 demo checks remaining today · No account needed";if(used>=3)$("analyseBtn").disabled=true;}
updateLimit();
$("analyseBtn").addEventListener("click",async()=>{
 const used=Number(localStorage.getItem(key())||0);
 if(used>=3){$("status").textContent="You have reached the three-check demo limit for today.";return;}
 if(!API_BASE){$("status").textContent="The website interface is ready. The secure analysis service still needs to be deployed and connected; no detection result has been guessed.";return;}
 $("analyseBtn").disabled=true;$("status").textContent="Sending video for analysis…";
 try{
  const body=new FormData();
  if(mode==="upload")body.append("video",$("videoFile").files[0]);else body.append("url",$("videoUrl").value.trim());
  const res=await fetch(API_BASE+"/api/analyse",{method:"POST",body});
  const data=await res.json();
  if(!res.ok)throw new Error(data.error||"Analysis could not be completed.");
  localStorage.setItem(key(),String(used+1));updateLimit();
  $("status").textContent="Assessment: "+(data.verdict||"Uncertain")+" · Confidence: "+(data.confidence??"not provided")+"%. "+(data.explanation||"");
 }catch(e){$("status").textContent=e.message;}
 finally{validate();if(Number(localStorage.getItem(key())||0)>=3)$("analyseBtn").disabled=true;}
});