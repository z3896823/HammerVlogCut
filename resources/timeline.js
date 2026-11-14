"use strict";
// Keep the next source positioned at its in-point while the current shot plays.
class TimelinePlayer {
  constructor(root, onShot, onError){
    this.root=root;
    this.onShot=onShot;
    this.onError=onError;
    this.screens=root.querySelector(".screens");
    this.slider=root.querySelector("input");
    this.toggle=root.querySelector(".toggle");
    this.screens.onclick=this.toggle.onclick=()=>{
      if(this.running)this.pause();
      else if(this.position>=this.duration)this.seek(0,true);
      else this.play();
    };
    this.slider.oninput=()=>this.seek(Number(this.slider.value),this.running);
    root.querySelector(".full").onclick=()=>document.fullscreenElement?
      document.exitFullscreen():root.requestFullscreen();
  }
  release(slot){
    if(!slot)return;
    slot.video.onloadedmetadata=slot.video.onerror=null;
    slot.video.onended=slot.video.ontimeupdate=null;
    slot.video.pause(); slot.video.removeAttribute("src"); slot.video.load(); slot.video.remove();
  }
  clear(){
    this.pause();
    this.release(this.active); this.release(this.next);
    this.active=this.next=null;
  }
  load(clips,position=0,playing=false){
    this.clear();
    this.duration=0;
    this.clips=clips.map(clip=>{
      const at=this.duration;
      this.duration+=clip.out-clip.in;
      return {...clip,at};
    });
    this.slider.max=this.duration;
    this.seek(position,playing);
  }
  prepare(i,offset=0){
    if(i>=this.clips.length)return null;
    const clip=this.clips[i], video=document.createElement("video");
    const slot={i,video};
    video.hidden=true; video.playsInline=true; video.preload="auto";
    video.onloadedmetadata=()=>{video.currentTime=clip.in+offset;};
    video.onerror=()=>{
      if(slot===this.active){this.pause();this.onError("无法播放原片："+clip.label);}
    };
    video.src=clip.url;
    this.screens.append(video);
    return slot;
  }
  seek(position,playing){
    if(!this.clips.length)return;
    this.clear();
    position=Math.min(this.duration,Math.max(0,position));
    const i=this.clips.findLastIndex(clip=>clip.at<=position);
    this.active=this.prepare(i,position-this.clips[i].at);
    this.activate(position);
    if(playing && position<this.duration)this.play();
  }
  activate(position){
    const {video,i}=this.active;
    video.hidden=false;
    video.onended=()=>this.advance();
    video.ontimeupdate=()=>this.tick();
    this.next=this.prepare(i+1);
    this.onShot(this.clips[i],i);
    this.display(position);
  }
  display(position){
    this.position=position;
    this.slider.value=position;
    this.root.querySelector("output").textContent=clock(position)+" / "+clock(this.duration);
  }
  pause(){
    this.running=false;
    cancelAnimationFrame(this.frame);
    this.active?.video.pause();
    this.toggle.textContent="播放";
  }
  play(){
    const slot=this.active;
    if(!slot)return;
    this.running=true; this.toggle.textContent="暂停";
    slot.video.play().then(()=>this.tick()).catch(error=>{
      if(slot!==this.active || error.name==="AbortError")return;
      this.pause(); this.onError("无法开始播放："+this.clips[slot.i].label);
    });
  }
  tick(){
    cancelAnimationFrame(this.frame);
    if(!this.running || !this.active)return;
    const {video,i}=this.active, clip=this.clips[i];
    if(video.readyState>=2 && !video.seeking){
      if(video.currentTime>=clip.out){this.advance();return;}
      this.display(clip.at+Math.max(0,video.currentTime-clip.in));
    }
    this.frame=requestAnimationFrame(()=>this.tick());
  }
  advance(){
    if(!this.running)return;
    if(!this.next){
      this.pause(); this.display(this.duration);
      const clip=this.clips[this.active.i];
      this.active.video.currentTime=clip.out;
      return;
    }
    const previous=this.active;
    this.active=this.next;
    this.release(previous);
    this.activate(this.clips[this.active.i].at);
    this.play();
  }
}
