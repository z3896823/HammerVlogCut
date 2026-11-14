"use strict";
const id = name => document.getElementById(name);

const clock = t => Math.floor(t/60)+":"+String(Math.floor(t%60)).padStart(2,"0");
const project = new URLSearchParams(location.search).get("project");
const prefix = "p/"+encodeURIComponent(project)+"/";
let stories=[], current, active=-1, buttons=[], catalog;
let editing=-1, saving=false, removing=false;
const raw=id("source");
function range(i){
  const clip=current.clips[i];
  return [clip.in,clip.out];
}
function rangeLabel(i){
  const clip=current.clips[i], [a,b]=range(i);
  return clip.source+" · "+a+"–"+b+" 秒";
}
const junction=id("junction"), track=id("track"), handles=[id("entry"),id("exit")];
const storyPlayer=new TimelinePlayer(id("story-deck"),(_,i)=>sync(i),text=>id("message").textContent=text);
const cutPlayer=new TimelinePlayer(junction,clip=>id("trim-error").textContent=clip.label,text=>id("trim-error").textContent=text);
let pair, duration, pendingSeek;
function timeline(){
  return current.clips.map((clip,i)=>{
    const [start,end]=range(i);
    return {...clip,in:start,out:end,url:prefix+catalog.assets[clip.source]+"/source"};
  });
}
const stamp=t=>clock(t)+"."+String(Math.floor((t%1)*100+0.00001)).padStart(2,"0");
function resetContext(){
  cutPlayer.clear(); junction.hidden=true; raw.hidden=false;
  id("trim-error").textContent="";
}
function paint(){
  const positions=pair.map(t=>100*t/duration);
  handles.forEach((h,i)=>{
    h.style.left=positions[i]+"%";
    h.setAttribute("aria-valuemin",i?pair[0]+.04:0);
    h.setAttribute("aria-valuemax",i?duration:Math.max(0,pair[1]-.04));
    h.setAttribute("aria-valuenow",pair[i]);
    h.setAttribute("aria-valuetext",stamp(pair[i]));
  });
  id("selection").style.left=positions[0]+"%";
  id("selection").style.width=(positions[1]-positions[0])+"%";
  id("in-time").value=stamp(pair[0]); id("out-time").value=stamp(pair[1]);
}
function seekSource(){
  if(raw.readyState>=1 && !raw.seeking && Math.abs(raw.currentTime-pendingSeek)>.001)
    raw.currentTime=pendingSeek;
}
let stopFrame=0, audition=null;
function pauseSource(){
  audition=null;
  cancelAnimationFrame(stopFrame);
  raw.pause();
}
function checkEnd(){
  cancelAnimationFrame(stopFrame);
  if(!audition?.started)return;
  if(!raw.seeking && raw.currentTime>=audition.end){
    const end=audition.end;
    pauseSource();
    raw.currentTime=end;
  }else if(!raw.paused){
    stopFrame=requestAnimationFrame(checkEnd);
  }
}
raw.addEventListener("playing",checkEnd);
raw.addEventListener("timeupdate",checkEnd);
function auditionSelection(atExit){
  pauseSource();
  const selection={end:pair[1]};
  audition=selection;
  pendingSeek=atExit?Math.max(pair[0],pair[1]-2):pair[0];
  seekSource();
  function playWhenReady(){
    if(audition!==selection || selection.started || raw.readyState<1 || raw.seeking)return;
    if(Math.abs(raw.currentTime-pendingSeek)>.035){
      seekSource();
      return;
    }
    selection.started=true;
    raw.play().catch(error=>{
      if(audition===selection && error.name!=="AbortError"){
        pauseSource();
        id("trim-error").textContent="无法自动试看，请点击播放器重试。";
      }
    });
  }
  selection.ready=playWhenReady;
  playWhenReady();
}
raw.addEventListener("seeked",()=>{
  if(audition)audition.ready();
  else if(handles.some(h=>h.matches(":active")))seekSource();
});
raw.addEventListener("loadeddata",()=>audition?.ready());
function openTrim(i){
  if(saving)return;
  storyPlayer.pause(); resetContext(); editing=i; pair=[...range(i)];
  const clip=current.clips[i], asset=catalog.assets[clip.source];
  duration=catalog.durations[asset]; pendingSeek=pair[0];
  id("trim-title").textContent=clip.label;
  id("trim-frames").replaceChildren(...[1,2,3,4].map(n=>{
    const img=new Image(); img.alt=""; img.src=prefix+asset+"/frame-"+n+".jpg"; return img;
  }));
  raw.onloadedmetadata=seekSource; raw.src=prefix+asset+"/source";
  paint(); id("trim").showModal();
}
function movePoint(i,value){
  const low=i?Math.min(duration,pair[0]+.04):0;
  const high=i?duration:Math.max(0,pair[1]-.04);
  pair[i]=Math.min(high,Math.max(low,Math.round(value*1000)/1000));
  resetContext(); pauseSource();
  pendingSeek=i?Math.max(pair[0],pair[1]-.02):pair[0];
  seekSource(); paint();
}
handles.forEach((h,i)=>{
  let drag=null;
  h.onpointerdown=e=>{
    if(drag || e.button!==0)return;
    resetContext(); pauseSource();
    h.setPointerCapture(e.pointerId); h.focus(); drag={id:e.pointerId,x:e.clientX,start:pair[i]};
  };
  h.onpointermove=e=>{
    if(drag?.id===e.pointerId)movePoint(i,drag.start+(e.clientX-drag.x)*duration/track.clientWidth);
  };
  h.onpointerup=e=>{
    if(drag?.id!==e.pointerId)return;
    drag=null;
    auditionSelection(i===1);
  };
  h.onlostpointercapture=()=>{drag=null;};
  h.onkeydown=e=>{
    if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;
    e.preventDefault();
    const step=e.shiftKey ? .4 : .04;
    movePoint(i,e.key==="Home"?0:e.key==="End"?duration:pair[i]+(e.key==="ArrowLeft"?-step:step));
  };
});
function previewCut(atExit){
  pauseSource();
  const clips=timeline();
  const selected=clips[editing];
  [selected.in,selected.out]=pair;
  const before=clips[editing-1], after=clips[editing+1];
  if(before)before.in=Math.max(before.in,before.out-3);
  if(after)after.out=Math.min(after.out,after.in+3);
  const offset=atExit?(before?before.out-before.in:0)+Math.max(0,selected.out-selected.in-3):0;
  raw.hidden=true; junction.hidden=false;
  cutPlayer.load([before,selected,after].filter(Boolean),offset,true);
}
id("trial").onclick=()=>previewCut(false);
id("trial-exit").onclick=()=>previewCut(true);
raw.onerror=()=>{
  if(!id("trim").open)return;
  if(audition && !audition.retried){
    audition.retried=true;
    audition.started=false;
    raw.load();
    return;
  }
  id("trim-error").textContent="无法读取这条原片。";
};
function edited(){
  if(editing<0)return false;
  const clip=current.clips[editing];
  return pair[0]!==clip.in || pair[1]!==clip.out;
}
function finish(remove=false){
  if(saving)return;
  if(!remove && !edited()){id("trim").close();return;}
  pauseSource();cutPlayer.pause();
  removing=remove;
  const label=current.clips[editing].label;
  id("question").textContent=remove?"从故事时间线移出「"+label+"」？":"应用「"+label+"」的入出点调整？";
  id("discard").hidden=remove;
  id("apply").textContent=remove?"确认移出":"应用";
  id("decision-error").textContent="";
  id("decision").showModal();
}
id("done").onclick=()=>finish();
id("remove").onclick=()=>finish(true);
id("trim").oncancel=e=>{e.preventDefault();finish();};
id("trim").onclose=()=>{editing=-1;pauseSource();resetContext();};
id("back").onclick=()=>id("decision").close();
id("discard").onclick=()=>{id("decision").close();id("trim").close();};
id("decision").oncancel=e=>{if(saving)e.preventDefault();};
id("apply").onclick=async()=>{
  if(saving)return;
  saving=true;
  const controls=id("decision").querySelectorAll("button");
  controls.forEach(button=>button.disabled=true);
  id("decision-error").textContent="正在应用…";
  const shot=storyPlayer.clips[editing];
  const oldPosition=storyPlayer.position;
  const offset=oldPosition-shot.at;
  const length=shot.out-shot.in;
  const newLength=removing?0:pair[1]-pair[0];
  let position=oldPosition;
  if(offset>=length)position+=newLength-length;
  else if(offset>=0)position=shot.at+Math.min(newLength,Math.max(0,shot.in+offset-pair[0]));
  const list=id("chapters"), scroll=list.scrollTop;
  const expanded=new Set([...list.querySelectorAll("details[open]")].map(d=>d.dataset.chapter));
  try{
    const response=await fetch(prefix+"stories/timeline",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({base:current.id,ranges:current.clips.map((_,i)=>!removing && i===editing?pair:range(i)),
        removed:removing?[editing]:[]})});
    const data=await response.json();
    if(!response.ok)throw Error(data.error || "保存失败，请重试。");
    await loadVersions(data.edition,position);
    list.querySelectorAll("details").forEach(d=>{if(expanded.has(d.dataset.chapter))d.open=true;});
    id("decision").close();id("trim").close();list.scrollTop=scroll;
    id("message").textContent=removing?"镜头已移出。":"镜头调整已应用。";
  }catch(e){id("decision-error").textContent=e.message;}
  finally{saving=false;controls.forEach(button=>button.disabled=false);}
};
window.onbeforeunload=e=>{if(saving || (id("trim").open && edited())){e.preventDefault();e.returnValue="";}};

async function read(url){
  const response=await fetch(url);
  if(!response.ok)throw Error("项目读取失败，请从素材审阅台重新打开。");
  return response.json();
}
function updateChapters(){
  buttons.forEach((button,i)=>{
    const clip=current.clips[i];
    if(!i || current.clips[i-1].chapter!==clip.chapter)
      button.closest("details").querySelector("summary").textContent=clock(storyPlayer.clips[i].at)+"　"+clip.chapter;
  });
}
function sync(i){
  if(active===i)return;
  if(active>=0)buttons[active].removeAttribute("aria-current");
  active=i;
  const clip=current.clips[i];
  buttons[i].setAttribute("aria-current","true");
  buttons[i].closest("details").open=true;
  id("playing").textContent=clip.chapter+" · "+clip.label;
}
function show(index,position=0){
  id("message").textContent="";
  current=stories[index];id("versions").value=index;
  drawStory(position);
}
function drawStory(position=0){
  active=-1;buttons=[];
  id("cut").hidden=false;
  document.querySelector("h1").textContent=current.title;
  id("chapters").replaceChildren();
  let group,chapter;
  for(const clip of current.clips){
    if(clip.chapter!==chapter){
      chapter=clip.chapter;group=document.createElement("details");group.dataset.chapter=chapter;
      const heading=document.createElement("summary");
      heading.textContent=clock(clip.at)+"　"+chapter;group.append(heading);id("chapters").append(group);
    }
    const button=document.createElement("button"),source=document.createElement("small");
    button.textContent=clip.label;
    const i=buttons.length;source.textContent=rangeLabel(i);
    button.append(source);buttons.push(button);
    const row=document.createElement("div"),trim=document.createElement("button");
    row.className="clip-row";trim.className="trim-open";trim.textContent="调整";
    trim.onclick=()=>openTrim(i);row.append(button,trim);group.append(row);
    button.onclick=()=>storyPlayer.seek(storyPlayer.clips[i].at,true);
  }
  id("story-deck").hidden=!buttons.length;
  if(!buttons.length){storyPlayer.clear();id("playing").textContent="时间线为空";return;}
  storyPlayer.load(timeline(),position); updateChapters();
}
async function loadVersions(selected,position=0){
  stories=await read(prefix+"stories");
  if(!stories.length){id("message").textContent="该项目还没有故事预览。";return;}
  id("versions").replaceChildren(...stories.map((s,i)=>new Option(s.version+" · "+clock(s.duration),i)));
  id("versions").hidden=false;
  show(Math.max(0,stories.findIndex(s=>s.id===selected)),position);
}
id("versions").onchange=e=>show(Number(e.target.value));
(async()=>{
  catalog=await read(prefix+"project");
  id("project").textContent=catalog.title;
  await loadVersions();
})().catch(e=>id("message").textContent=e.message);
