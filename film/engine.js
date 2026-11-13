/* Film engine — runs inside the stage page (film/stage.html).

   The real Venture Trader dashboard is loaded, untouched, in an <iframe>. This
   script is the "camera crew" around it: it moves a camera (pan / zoom / tilt on
   the wrapper), draws a cursor, shows captions, scrolls the app, and tells the
   recorder where the real mouse should be. A timeline (film/timeline.js) supplies
   the data; the recorder (film/record.mjs) calls __frame(t, dt) once per video
   frame, in order, and screenshots the result.

   Positions are never hard-coded pixels: cursor waypoints, camera targets and
   scroll targets are CSS selectors (or functions) resolved against the live page
   every frame, so the film follows the app's real layout whatever data it has. */
(function(){
  "use strict";
  const W=1280, H=720;                       // output frame
  const $=id=>document.getElementById(id);
  const clamp=x=>x<0?0:x>1?1:x;
  const outCubic=x=>1-Math.pow(1-x,3);
  const outBack=x=>{const c=1.9;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2);};
  const inOut=x=>x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2;
  const seg=(t,s,d)=>clamp((t-s)/d);
  const bump=(t,c,d)=>{const x=(t-c)/d;return (x>=0&&x<=1)?Math.sin(x*Math.PI):0;};
  const win=(t,a,b,fi,fo)=>clamp(Math.min(seg(t,a,fi||220),1-seg(t,b-(fo||220),fo||220)));
  const ease={clamp,outCubic,outBack,inOut,seg,bump,win};

  const frame=$("app"), cam=$("cam"), probe=$("probe");
  const AW=frame.width|0, AH=frame.height|0, S=W/AW;      // app viewport, and its full-bleed scale
  const appWin=()=>frame.contentWindow, appDoc=()=>frame.contentDocument;

  /* ---- resolving "where is this thing right now?" (app viewport coordinates) ---- */
  function find(spec){
    const d=appDoc(); if(!d||!d.body) return null;
    if(typeof spec==="string") return d.querySelector(spec);
    if(typeof spec==="function") return spec(d);
    if(spec&&spec.s) return typeof spec.s==="function"?spec.s(d):d.querySelector(spec.s);
    return null;
  }
  function point(spec){                       // -> [x,y] or null if not on screen yet
    if(Array.isArray(spec)) return spec;
    const el=find(spec); if(!el) return null;
    const r=el.getBoundingClientRect(); if(!r.width&&!r.height) return null;
    const o=(spec&&typeof spec==="object"&&!Array.isArray(spec))?spec:{};
    return [r.left+r.width*(o.ax??0.5)+(o.dx||0), r.top+r.height*(o.ay??0.5)+(o.dy||0)];
  }
  // eased walk through keyframes whose targets are resolved live; `mem` remembers the
  // last good position so a target that is not rendered yet doesn't make things jump
  function walk(K,t,mem,n){
    let i=0; while(i<K.length-1&&t>=K[i+1][0]) i++;
    const a=K[i], b=K[Math.min(i+1,K.length-1)];
    const pa=point(a[1])||mem.p, pb=(b===a?pa:point(b[1]))||pa;
    const e=b===a||t<=a[0]?0:inOut(clamp((t-a[0])/(b[0]-a[0])));
    const p=pa&&pb?[pa[0]+(pb[0]-pa[0])*e, pa[1]+(pb[1]-pa[1])*e]:(mem.p||[AW/2,AH/2]);
    mem.p=p; const out=[p[0],p[1]];
    for(let k=2;k<2+(n||0);k++) out.push((a[k]??0)+((b[k]??0)-(a[k]??0))*e);
    return out;
  }
  // scroll targets: a number, or {s, top} = put that element `top` px below the top of the
  // scrolling box. `box` is the app window, or an element that scrolls by itself (the popup).
  function scrollTarget(spec,box){
    if(typeof spec==="number") return spec;
    const el=find(spec); if(!el) return null;
    const r=el.getBoundingClientRect(); if(!r.width&&!r.height) return null;
    return box?box.scrollTop+r.top-box.getBoundingClientRect().top-(spec.top??150)
              :appWin().scrollY+r.top-(spec.top??150);
  }
  function scrollTrack(K,t,box,st){
    let i=0; while(i<K.length-1&&t>=K[i+1][0]) i++;
    const a=K[i], b=K[Math.min(i+1,K.length-1)];
    const ya=scrollTarget(a[1],box), yb=b===a?ya:scrollTarget(b[1],box);
    const A=ya==null?st.y:ya, Bv=yb==null?A:yb;
    const e=b===a||t<=a[0]?0:inOut(clamp((t-a[0])/(b[0]-a[0])));
    const max=box?box.scrollHeight-box.clientHeight:appDoc().documentElement.scrollHeight-AH;
    st.y=Math.min(Math.max(0,max),Math.max(0,A+(Bv-A)*e));
    if(box){ if(Math.abs(box.scrollTop-st.y)>0.4) box.scrollTop=st.y; }
    else if(Math.abs(appWin().scrollY-st.y)>0.4) appWin().scrollTo(0,st.y);
  }

  /* ---- CSS animations/transitions advance one video frame at a time ----
     The recorder fakes the JS clock; this does the same for CSS, so marquees,
     hover fades and the popup's fly-in play at film speed however long a frame
     takes to capture. */
  const seen=new WeakSet();
  function stepAnimations(doc,dt){
    if(!doc||!doc.getAnimations) return;
    for(const a of doc.getAnimations()){
      try{
        const tg=a.effect&&a.effect.target;
        if(tg&&a.animationName&&getComputedStyle(tg).animationPlayState.indexOf("paused")>=0) continue;   // the app paused it (e.g. ticker under the mouse)
        let cur;
        if(!seen.has(a)){ seen.add(a); a.pause(); cur=dt; } else cur=(a.currentTime||0)+dt;
        const end=a.effect?a.effect.getComputedTiming().endTime:Infinity;
        if(isFinite(end)&&cur>=end) a.finish(); else a.currentTime=cur;
      }catch(e){}
    }
  }

  const TL=window.__TIMELINE(ease, {AW,AH});          // the film's data
  const mem={cur:{},cam:{}}, scrollState={win:{y:0}};
  const clickTimes=(TL.actions||[]).filter(a=>a[1]==="click").map(a=>a[0]);
  const cursor=$("cursor"), ring=$("ring"), cap=$("cap"), captxt=$("captxt");

  function frameAt(t,dt){
    stepAnimations(appDoc(),dt); stepAnimations(document,dt);

    // scroll the real page, and anything inside it that scrolls on its own
    if(appDoc()&&appDoc().body){
      if(TL.scroll) scrollTrack(TL.scroll,t,null,scrollState.win);
      for(const sc of TL.scrollers||[]){ const box=find(sc.box);
        if(box&&box.clientHeight) scrollTrack(sc.keys,t,box,scrollState[sc.box]||(scrollState[sc.box]={y:0})); }
    }

    // camera: focus point (app coords), zoom (1 = the app fills the frame), tilt
    const c=walk(TL.cam,t,mem.cam,3); let fx=c[0], fy=c[1];
    let z=Math.max(1,c[2]||1); for(const [pt,mg] of TL.punch||[]) z+=mg*bump(t,pt,180);
    const hw=W/2/(S*z), hh=H/2/(S*z);                 // keep the app covering the frame
    fx=Math.min(Math.max(fx,hw),AW-hw); fy=Math.min(Math.max(fy,hh),AH-hh);
    cam.style.transformOrigin=`${fx.toFixed(1)}px ${fy.toFixed(1)}px`;
    cam.style.transform=`translate(${(W/2-fx).toFixed(1)}px,${(H/2-fy).toFixed(1)}px) scale(${(S*z).toFixed(4)}) `+
      `rotateX(${(c[3]||0).toFixed(2)}deg) rotateY(${(c[4]||0).toFixed(2)}deg)`;

    // cursor (drawn in app space so it rides the camera) + click ring
    const p=walk(TL.cursor,t,mem.cur,0), on=TL.cursorOn(t);
    cursor.style.opacity=on?1:0; cursor.style.transform=`translate(${p[0].toFixed(1)}px,${p[1].toFixed(1)}px)`;
    let rr=-1; for(const ct of clickTimes) { const e=seg(t,ct-40,340); if(e>0&&e<1) rr=e; }
    if(rr>=0){ const sz=8+rr*52; ring.style.opacity=((1-rr)*0.95).toFixed(3); ring.style.width=sz+"px"; ring.style.height=sz+"px";
      ring.style.transform=`translate(${(p[0]+2).toFixed(1)}px,${(p[1]+4).toFixed(1)}px)`; } else ring.style.opacity=0;

    // caption
    let cb=null; for(const k of TL.captions) if(t>=k[0]&&t<k[1]) cb=k;
    if(cb){ if(captxt.textContent!==cb[2]) captxt.textContent=cb[2]; cap.style.opacity=win(t,cb[0]+80,cb[1],200,200).toFixed(3); }
    else cap.style.opacity=0;

    if(TL.extra) TL.extra(t,{$,ease,appDoc,appWin,point});     // hook, outro, anything film-specific

    // where the real mouse belongs on screen: the browser maps the app-space point
    // through the camera transform (tilt included) for us
    probe.style.transform=`translate(${p[0].toFixed(1)}px,${p[1].toFixed(1)}px)`;
    const r=probe.getBoundingClientRect();
    return on?[Math.min(W-1,Math.max(0,r.left)), Math.min(H-1,Math.max(0,r.top)), p[0], p[1]]:null;   // screen x,y + app x,y
  }

  window.__frame=frameAt;
  window.__DURATION=TL.duration;
  window.__ACTIONS=(TL.actions||[]).map(a=>({t:a[0],type:a[1],arg:a[2]??null,opt:a[3]??null}));
  window.__loadApp=()=>new Promise(res=>{ frame.addEventListener("load",()=>res(true),{once:true}); frame.src="/"; });
  window.__READY__=true;
})();
