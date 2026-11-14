"use strict";
const el=id=>document.getElementById(id);
const video=document.querySelector("video");
const sections=["画面内容","动作与变化","镜头表现","声音内容","情绪与氛围","剪辑用途"];
const kinds={visual:"画面观察",speech:"逐句 ASR",sound:"声音事件",inference:"模型推断",suggestion:"叙事建议",note:"人工备注"};
let project="", key="", catalog, record, busy=false;
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function report(e){el("error").textContent=e.message;}
async function request(url,init){
  const r=await fetch(url,init);
  if(!r.ok)throw Error(r.status===409?"记录已在另一处更新。请先复制当前文字，再刷新页面核对。":"读取或保存失败（"+r.status+"）");
  return r.json();
}
function path(id,k){return "p/"+id+"/"+k+"/";}
let editor=null;
function speechChanged(){return editor && editor.input.value!==editor.original;}
function contextChanged(){return el("context-dialog").open && el("context-text").value!==catalog.context.raw;}
function dirty(){return contextChanged() || speechChanged() || (record && el("note").value!=="");}
function leave(){return !dirty() || confirm("离开会放弃当前尚未保存的修改，继续吗？");}
function lock(on){busy=on;el("projects").disabled=on;el("context-open").disabled=on || !catalog;el("note").disabled=on;el("save").disabled=on;}
function seek(time){video.currentTime=time;video.play().catch(report);}
function resizeMedia(w,h){
  if(w && h){el("media").style.setProperty("--ratio",String(w/h));el("media").classList.toggle("portrait",h>w);}
}
function timestamp(seconds) {
  const minutes = Math.floor(seconds / 60);
  return String(minutes).padStart(2,"0")+":"+String(Math.floor(seconds)%60).padStart(2,"0");
}
let showSpeech=false;
function list(){
  el("count").textContent=Object.keys(catalog.assets).length;
  el("assets").replaceChildren();
  for(const [name,id] of Object.entries(catalog.assets)){
    const b=node("button"), img=node("img"), label=node("span");
    const clock=name.match(/^video_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.[^.]+$/);
    const line=node("span"), duration=node("span");
    line.className="asset-list-line";
    duration.className="asset-duration";
    const seconds=catalog.durations?.[id];
    if(Number.isFinite(seconds))duration.textContent=Math.round(seconds)+"s";
    line.append(node("strong",clock ? clock.slice(4,7).join(":") : name),duration);
    label.append(line,node("small",clock ? clock.slice(1,4).join(".")+"  ·  "+name.split(".").pop().toUpperCase() : ""));
    b.title=name; b.setAttribute("aria-label",[name,duration.textContent].filter(Boolean).join(" · "));
    img.src=path(project,id)+"frame-1.jpg";img.loading="lazy";img.alt="";
    b.setAttribute("aria-current",String(id===key));
    if(catalog.pending.includes(id))label.append(node("small","待处理"));
    b.append(img,label);b.onclick=()=>{if(!busy && id!==key && leave())open(project,id);};
    el("assets").append(b);
  }
}
function render(){
  const {asset:a,model:m,human,feedback}=record, prefix=path(project,key);
  el("detail").hidden=false;el("title").textContent=a.source;
  el("meta").textContent=a.duration.toFixed(2)+" 秒 · "+a.codec.toUpperCase();
  video.poster=prefix+a.frames[0].file;
  video.src=prefix+"source";
  video.onloadedmetadata=()=>resizeMedia(video.videoWidth,video.videoHeight);
  el("frames").replaceChildren(...a.frames.map((f,i)=>{
    const b=node("button"),img=node("img");
    img.alt="从 "+f.t+" 秒播放";
    if(i===0)img.onload=()=>{if(video.readyState<1 && img.isConnected)resizeMedia(img.naturalWidth,img.naturalHeight);};
    img.src=prefix+f.file;b.append(img,node("span",timestamp(f.t)));b.onclick=()=>seek(f.t);return b;
  }));
  renderBackground(feedback);
  el("status").textContent=[m.visual_status,m.audio_status,m.asr_status].join(" ｜ ");
  showSpeech=false;
  renderSegments();
}
function renderBackground(feedback){
  el("note").value="";
  el("state").textContent=feedback.pending?"已确认 · 待刷新":"";
  const history=feedback.history || [feedback.last_applied,feedback.pending].filter(Boolean);
  el("history").hidden=!history.length;
  el("history").querySelector("ol").replaceChildren(...history.map(text=>node("li",text)));
}
function sectionFor(s){
  if(sections.includes(s.topic))return s.topic;
  const legacy={"镜头与主体":"画面内容","动作与互动":"动作与变化","情绪":"情绪与氛围","场景与情绪":"情绪与氛围","故事用途":"剪辑用途"};
  return legacy[s.topic] || ({sound:"声音内容",inference:"情绪与氛围",suggestion:"剪辑用途"})[s.kind] || "画面内容";
}
function descriptionRows(segments){
  return sections.map(title=>{
    const card=node("article");
    card.append(node("h3",title));
    const rows=segments.filter(s=>sectionFor(s)===title);
    if(!rows.length)card.append(node("p","暂无相关记录"));
    for(const s of rows){
      const entry=node("div"), time=node("button",s.start.toFixed(2)+" – "+s.end.toFixed(2)+" s");
      time.onclick=()=>seek(s.start);
      entry.append(time,node("p",[s.role,s.text].filter(Boolean).join(" · ")));
      card.append(entry);
    }
    return card;
  });
}
function speechLine(segment, body){
  const line=node("button",segment.text || "（空）");
  line.className="speech-line";
  line.title="点击编辑对白";
  line.onclick=()=>{
    if(busy || (speechChanged() && !confirm("放弃上一句尚未保存的修改？")))return;
    if(editor)editor.close();
    const input=node("textarea"), save=node("button","保存"), cancel=node("button","取消");
    input.value=segment.text;
    input.setAttribute("aria-label","编辑这句对白");
    const actions=node("div");
    actions.className="speech-actions";
    actions.append(cancel,save);
    const close=()=>{body.replaceChildren(line);editor=null;};
    editor={input,original:segment.text,close};
    cancel.onclick=()=>{close();line.focus();};
    save.onclick=async()=>{
      if(busy)return;
      lock(true);
      input.disabled=cancel.disabled=save.disabled=true;
      el("error").textContent="";
      try{
        record.human=await request(path(project,key)+"correct",{method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({segment:{...segment,text:input.value},revision:record.human.revision,stamp:record.stamp})});
        renderSegments();
      }catch(e){report(e);}
      finally{lock(false);input.disabled=cancel.disabled=save.disabled=false;}
    };
    body.replaceChildren(input,actions);
    input.focus();
  };
  body.append(line);
}
function renderSegments(){
  editor=null;
  const {model:m,human}=record;
  el("visualTab").setAttribute("aria-pressed",String(!showSpeech));
  el("speechTab").setAttribute("aria-pressed",String(showSpeech));
  const segments=new Map(m.segments.map(s=>[s.id,s]));
  for(const s of Object.values(human.segments))segments.set(s.id,s);
  const visible=[...segments.values()].filter(s=>(s.kind==="speech")===showSpeech);
  if(!showSpeech){
    el("segments").replaceChildren(...descriptionRows(visible));return;
  }
  if(!visible.length){el("segments").replaceChildren(node("p",showSpeech?"暂无对白转写":"暂无片段描述"));return;}
  el("segments").replaceChildren(...visible.sort((a,b)=>a.start-b.start).map(s=>{
    const card=node("article"),time=node("button",s.start.toFixed(2)+" – "+s.end.toFixed(2)+" s"),body=node("div");
    time.onclick=()=>seek(s.start);
    if(s.kind==="speech")speechLine(s,body);
    else body.append(node("small",[human.segments[s.id]?"人工修订":"",kinds[s.kind],s.topic].filter(Boolean).join(" · ")),
      node("p",[s.role,s.speaker,s.text].filter(Boolean).join(" · ")));
    card.dataset.kind=s.kind;card.append(time,body);return card;
  }));
}
for(const [id,speech] of [["visualTab",false],["speechTab",true]]){
  el(id).onclick=()=>{
    if(busy || speech===showSpeech || (speechChanged() && !confirm("放弃尚未保存的对白修改？")))return;
    showSpeech=speech;renderSegments();
  };
}
function displayContext(){
  const state=catalog.context;
  el("context-preview").textContent=state.summary || (state.pending?"已保存 · 待提炼":"点击补充");
  el("context-open").title=state.summary || "编辑项目背景";
}
el("context-open").onclick=()=>{
  const state=catalog.context;
  el("context-text").value=state.raw;
  el("context-summary").textContent=state.summary;
  el("context-error").textContent="";
  el("context-dialog").showModal();
  el("context-text").focus();
};
el("context-cancel").onclick=()=>el("context-dialog").close();
el("context-dialog").oncancel=e=>{if(busy || (contextChanged() && !confirm("放弃未保存的项目背景？")))e.preventDefault();};
el("context-save").onclick=async()=>{
  if(busy)return;
  const controls=["context-save","context-text","context-cancel"].map(el);
  controls.forEach(c=>c.disabled=true);
  lock(true);
  try{
    catalog.context=await request("p/"+project+"/context",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({revision:catalog.context.revision,raw:el("context-text").value})});
    displayContext();
    el("context-dialog").close();
  }catch(e){el("context-error").textContent=e.message;}
  finally{controls.forEach(c=>c.disabled=false);lock(false);}
};
async function open(id,asset){
  lock(true);el("error").textContent="";
  try{
    const next=id===project?catalog:await request("p/"+id+"/project");
    const target=asset || Object.values(next.assets)[0];
    const d=target?await request(path(id,target)+"detail"):null;
    project=id;key=target;catalog=next;record=d;
    el("projects").value=id;el("story-open").href="story.html?project="+encodeURIComponent(id);displayContext();list();
    if(record)render();else el("detail").hidden=true;
    document.querySelector("main").scrollTop=0;
  }catch(e){el("projects").value=project;report(e);}finally{lock(false);}
}
el("projects").onchange=e=>{if(leave())open(e.target.value);else e.target.value=project;};
el("note").oninput=()=>{el("state").textContent=dirty()?"尚未保存":record.feedback.pending?"已确认 · 待刷新":"";};
el("feedback").onsubmit=async e=>{
  e.preventDefault();if(busy || !record || !el("note").value.trim())return;
  lock(true);el("error").textContent="";
  try{
    const note=await request(path(project,key)+"feedback",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({revision:record.feedback.revision,pending:el("note").value})});
    record.feedback=note;renderBackground(note);
    catalog.pending=catalog.pending.filter(k=>k!==key);if(note.pending)catalog.pending.push(key);
    el("history").open=true;list();
  }catch(e){report(e);}finally{lock(false);}
};
window.onbeforeunload=e=>{if(dirty()){e.preventDefault();e.returnValue="";}};
video.onerror=()=>report(Error("无法播放原片，请核实文件位置及浏览器编码支持。"));
(async()=>{
  const projects=await request("projects");
  for(const p of projects)el("projects").add(new Option(p.title,p.id));
  if(projects.length)await open(projects[0].id);
})().catch(report);
