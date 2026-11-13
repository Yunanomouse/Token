/* Venture Trader — 2 minute guided tour.
   Timeline source for src/venture-2min.html (inlined by render/make_tour_page.py).
   128 BPM grid: 1 bar = 1875 ms, 64 bars = 120 s. Every scene change is on a downbeat,
   and everything on screen is a pure function of the timestamp passed to seek(). */
(function(){
  "use strict";
  const BAR=1875, B=n=>Math.round(n*BAR);
  const DURATION=B(64);
  const $=id=>document.getElementById(id);
  const $$=s=>[...document.querySelectorAll(s)];
  const A={}; $$(".anim").forEach(el=>A[el.dataset.a]=el);
  const clamp=x=>x<0?0:x>1?1:x;
  const outCubic=x=>1-Math.pow(1-x,3);
  const outBack=x=>{const c=1.9;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2);};
  const inOut=x=>x<.5?2*x*x:1-Math.pow(-2*x+2,2)/2;
  const seg=(t,s,d)=>clamp((t-s)/d);
  const bump=(t,c,d)=>{const x=(t-c)/d;return (x>=0&&x<=1)?Math.sin(x*Math.PI):0;};
  const win=(t,a,b,fi,fo)=>clamp(Math.min(seg(t,a,fi||220),1-seg(t,b-(fo||220),fo||220)));
  const setT=(k,op,tx,ty,sc)=>{const el=A[k];if(!el)return;el.style.opacity=op;
    el.style.transform=`translate(${tx||0}px,${ty||0}px)`+(sc!=null?` scale(${sc})`:"");};

  /* ---------------- section times (ms) ---------------- */
  const T={ app:B(4), brief:B(6), stats:B(8), heat:B(12),
    nvda:B(16), tf1:B(18), tf2:B(19), tf3:B(20), perf:B(21), fund:B(23), trend:B(25), mclose:B(27),
    sig:B(28), sigH:B(30), sigM:B(33), radar:B(36), graded:B(39),
    ai:B(40), an0:B(44), an1:B(46), an2:B(48),
    tabs:B(50), ov2:B(53), out:B(58) };
  const XF=260;

  /* ---------------- static content ---------------- */
  const arrow=u=>u?"▲":"▼";
  const syms=[["TSLA","339.30",0,"0.87"],["AMD","506.00",0,"1.63"],["NVDA","225.01",0,"0.07"],
    ["META","568.97",0,"3.54"],["AMZN","261.31",0,"0.51"],["AAPL","305.59",0,"0.11"],
    ["MSFT","480.35",0,"3.04"],["MU","1011.75",1,"4.13"],["AMAT","535.31",1,"5.55"],
    ["ARGX","987.84",1,"16.04"],["SNDK","1786.85",1,"8.88"],["ORCL","146.65",0,"2.57"]];
  const tRow=()=>syms.map(([s,p,u,c])=>`<span><span class="tsym">${s}</span> ${p} <span class="${u?'up':'dn'}">${arrow(u)}${c}%</span></span>`).join("");
  $("tape").innerHTML=tRow()+tRow();
  const tapeEl=$("tape"); let tapeW=0;

  // heatmap: two snapshots so the auto-refresh visibly updates values + colours
  const hm=[["NVDA",-0.07,0,0,44,55],["AAPL",-0.11,0,55,44,45],["MSFT",-3.04,44,0,30,52],
    ["AVGO",-0.14,74,0,26,52],["MU",4.13,44,52,17,48],["AMD",-1.63,61,52,17,48],
    ["ORCL",-2.57,78,52,22,24],["PLTR",-0.86,78,76,22,24]];
  const hm2v=[0.62,0.34,-2.11,0.28,4.88,-0.44,-1.72,0.51];
  const lerpc=(a,b,e)=>a.map((v,i)=>Math.round(v+(b[i]-v)*e));
  function hmColorC(n){ const red=[158,61,71],mid=[47,58,77],grn=[11,143,79]; let c,al;
    if(n<=0){const e=clamp(-n/3.2); c=lerpc(mid,red,e); al=0.4+0.16*e;}
    else{const e=clamp(n/4.4); c=lerpc(mid,grn,e); al=0.4+0.16*e;}
    return `rgba(${c[0]},${c[1]},${c[2]},${al.toFixed(2)})`; }
  const fmtv=v=>(v>=0?"+":"")+v.toFixed(2)+"%";
  $("hm").innerHTML=hm.map(([s,v,x,y,w,h],i)=>
    `<a class="blk" id="blk${i}" style="left:${x}%;top:${y}%;width:${w}%;height:${h}%;background:${hmColorC(v)}">
      <b style="font-size:${w>28?13:10}px">${s}</b><s class="hmv" style="font-size:${w>28?10:8}px">${fmtv(v)}</s></a>`).join("");
  const hmBlk=$$("#hm .blk"), hmVal=hmBlk.map(b=>b.querySelector(".hmv"));

  // stock chart: one candlestick series (+ moving average) per timeframe
  function genChart(seed,N,base,drift,vol){
    const c=[]; let p=base, rs=seed*97+3; const rnd=()=>{rs=(rs*9301+49297)%233280;return rs/233280;};
    for(let i=0;i<N;i++){const o=p, ch=drift+Math.sin(i/4+seed)*vol+(rnd()-0.5)*vol*1.5;
      const cl=o+ch, hi=Math.max(o,cl)+vol*0.6, lo=Math.min(o,cl)-vol*0.6; c.push([o,hi,lo,cl]); p=cl;}
    const lo=Math.min(...c.map(x=>x[2])), hi=Math.max(...c.map(x=>x[1])), W=600,H=150,cw=W/N,bw=cw*0.58;
    const Y=v=>8+(H-16)-(v-lo)/(hi-lo)*(H-16); let s="";
    c.forEach((k,i)=>{const x=i*cw+cw/2, up=k[3]>=k[0], col=up?"#00e676":"#ff3d71";
      s+=`<line x1="${x.toFixed(1)}" y1="${Y(k[1]).toFixed(1)}" x2="${x.toFixed(1)}" y2="${Y(k[2]).toFixed(1)}" stroke="${col}" stroke-width="1"/>`;
      const yt=Y(Math.max(k[0],k[3])), yb=Y(Math.min(k[0],k[3]));
      s+=`<rect x="${(x-bw/2).toFixed(1)}" y="${yt.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1,yb-yt).toFixed(1)}" fill="${col}"/>`;});
    let pts=""; for(let i=0;i<N;i++){const w0=Math.max(0,i-3);let m=0,ct=0;for(let j=w0;j<=i;j++){m+=c[j][3];ct++;}m/=ct;
      pts+=`${(i*cw+cw/2).toFixed(1)},${Y(m).toFixed(1)} `;}
    return s+`<polyline points="${pts.trim()}" fill="none" stroke="#00d4ff" stroke-width="1.7" opacity=".92"/>`;
  }
  // [click time, pill index, series]  pills: 1D 1W 1M 6M 1Y 5Y
  const TF=[[T.nvda,2,genChart(2,22,214,0.35,2.2)],[T.tf1,1,genChart(5,14,221,0.3,1.3)],
            [T.tf2,3,genChart(7,28,186,1.25,3.0)],[T.tf3,4,genChart(9,34,150,1.7,3.6)]];
  $("mchart").innerHTML=TF.map((f,i)=>`<g id="tf${i}" style="opacity:0">${f[2]}</g>`).join("");
  const tfG=TF.map((f,i)=>$("tf"+i));

  // word-by-word reveal for the AI text
  function wordify(el){ const out=[]; (function walk(n){ [...n.childNodes].forEach(c=>{
      if(c.nodeType===3){ const f=document.createDocumentFragment();
        c.textContent.split(/(\s+)/).forEach(p=>{ if(!p) return;
          if(/^\s+$/.test(p)) f.appendChild(document.createTextNode(p));
          else{ const s=document.createElement("span"); s.className="w"; s.textContent=p; f.appendChild(s); out.push(s);} });
        n.replaceChild(f,c);
      } else if(c.nodeType===1) walk(c); }); })(el); return out; }
  const reveal=(list,p)=>{ const k=p*list.length; for(let i=0;i<list.length;i++) list[i].style.opacity=i<k?1:0; };

  /* ---------------- element handles ---------------- */
  const tabs={}; $$("#nav span").forEach(s=>tabs[s.dataset.tab]=s);
  const panels={ov:$("pv-ov"),sig:$("pv-sig"),ai:$("pv-ai")};
  const pills=$$("#modal .m-tf span");
  const stCards=$$("#pv-ov .stats .st"), stVals=stCards.map(c=>c.querySelector(".v"));
  const brief=document.querySelector("#pv-ov .brief");
  const mBoxes=$$("#modal .m-box"), mSub=document.querySelector("#modal .m-sub");
  const mNums=mBoxes.map(b=>[...b.querySelectorAll(".up")]);
  const rowsH=$$("#sc1 .sig"), rowsM=$$("#sc2 .sig"), rowsR=$$("#pv-sig .radar .rr");
  const anCards=$$("#pv-ai .an");
  const aiWords=wordify(document.querySelector("#pv-ai .ai-out"));
  const anWords=anCards.map(c=>wordify(c.querySelector("p")));
  anCards.forEach(c=>{ const sk=document.createElement("div"); sk.className="sk"; sk.innerHTML="<i></i><i></i>"; c.appendChild(sk); });
  const anSk=anCards.map(c=>c.querySelector(".sk"));
  const chips=$$("#chips span"), hooks=[$("hk0"),$("hk1"),$("hk2")];
  const appEl=document.querySelector(".app");
  // tab hit-boxes (measured before any camera transform is applied)
  const tabBox={}; for(const k in tabs){ const r=tabs[k].getBoundingClientRect(); tabBox[k]=[r.left,r.right]; }

  /* ---------------- timeline data ---------------- */
  // which panel is on screen: [t0,t1,panel,tab]
  const VIEWS=[[T.app,T.sig,"ov","Overview"],[T.sig,T.ai,"sig","Signals"],[T.ai,T.ov2,"ai","AI"],[T.ov2,T.out,"ov","Overview"]];
  const panelOp=(name,t)=>{ let o=0; for(const [a,b,p] of VIEWS) if(p===name)
      o=Math.max(o,Math.min(a===T.app?1:seg(t,a-200,200),1-seg(t,b-200,200))); return o; };

  const CAPS=[
    [T.app,   T.brief, "Meet Venture Trader — your whole market on one screen."],
    [T.brief, T.stats, "It opens with a plain-English briefing of the day."],
    [T.stats, B(10),   "Market sentiment and high-conviction signals, front and center."],
    [B(10),   T.heat,  "Everything it tracks — and where the Fed stands."],
    [T.heat,  B(14),   "The heatmap: 174 US stocks, sized and colored by the day's move."],
    [B(14),   T.nvda,  "Red is down, green is up. One look shows where the action is."],
    [T.nvda,  T.tf1,   "Click any ticker — and the full picture opens."],
    [T.tf1,   T.perf,  "Flip through timeframes. Candles and moving average redraw instantly."],
    [T.perf,  T.fund,  "Performance over a week, a month, a year."],
    [T.fund,  T.trend, "Fundamentals right beside it — P/E, margins, revenue growth."],
    [T.trend, T.sig-250,"Plus a one-line trend read against its key averages."],
    [T.sig,   T.sigH,  "Signals: 93 live reads on the market, ranked by conviction."],
    [T.sigH,  T.sigM,  "High conviction — the movers that need attention now."],
    [T.sigM,  T.radar, "Medium signals: RSI extremes, sharp moves, unusual options flow."],
    [T.radar, T.graded,"Buy Radar flags setups while they're still forming."],
    [T.graded,T.ai,    "And every signal is graded daily against real closes."],
    [T.ai,    B(42),   "Then the AI reads all of it — and tells you what it means."],
    [B(42),   T.an0,   "A plain-English take. No jargon. No digging."],
    [T.an0,   T.an1,   "Markets Analyst — where the momentum is."],
    [T.an1,   T.an2,   "Risk Sentinel — what could go wrong."],
    [T.an2,   T.tabs,  "Strategy Researcher — what to do about it."],
    [T.tabs,  T.ov2,   "And there's more: watchlist, markets, crypto, fundamentals, news, macro, insiders."],
    [T.ov2,   B(55.5), "Best part? You never have to reload."],
    [B(55.5), T.out-200,"It refreshes itself every 30 seconds — prices, signals, briefing."]
  ];

  const CLICKS=[T.nvda,T.tf1,T.tf2,T.tf3,T.sig,T.ai,T.ov2];
  const PUNCH=[[T.app,.022],[T.nvda,.022],[T.tf1,.010],[T.tf2,.010],[T.tf3,.010],[T.sig,.022],[T.ai,.022],[T.ov2,.020]];
  const punch=t=>{let s=0;for(const[pt,mg]of PUNCH)s+=mg*bump(t,pt,180);return s;};

  // cursor waypoints [t,x,y] in frame px
  const WP=[
    [T.app,900,360],[B(5),760,300],
    [T.brief-300,520,190],[T.brief+900,420,182],[T.stats-200,760,186],
    [T.stats+500,187,262],[T.stats+BAR+400,490,262],[T.stats+2*BAR+400,790,262],[T.stats+3*BAR+400,1092,262],
    [T.heat+600,745,426],[B(13)+200,745,440],[B(13)+1100,669,590],[B(14)+900,868,590],
    [B(15)+300,400,470],[T.nvda-250,372,480],[T.nvda,372,500],
    [B(17),560,380],
    [T.tf1-200,408,281],[T.tf1,408,281],[T.tf2-250,500,281],[T.tf2,500,281],[T.tf3-250,545,281],[T.tf3,545,281],
    [B(20.6),640,380],
    [T.perf+500,430,516],[T.fund-300,560,516],[T.fund+500,720,516],[T.trend-300,880,516],
    [T.trend+600,420,258],[B(26.6),800,258],
    [T.sig-250,458,100],[T.sig,458,100],
    [B(29),600,300],
    [T.sigH+500,235,190],[B(31.5),235,262],[T.sigM-300,235,330],
    [T.sigM+500,620,190],[B(34.5),620,262],[T.radar-300,620,330],
    [T.radar+500,1000,182],[B(37.3),1000,238],[B(38.1),1000,284],[T.graded-200,1000,322],
    [T.graded+500,960,362],
    [T.ai-250,945,100],[T.ai,945,100],
    [B(41),300,150],[B(43.5),900,178],
    [T.an0+500,237,285],[T.an1-200,300,300],[T.an1+500,640,285],[T.an2-200,700,300],
    [T.an2+500,1042,285],[T.tabs-200,1100,300],
    [T.tabs+350,179,96],[T.ov2-900,1037,96],
    [T.ov2-250,86,100],[T.ov2,86,100],
    [B(54),1160,54],[B(55),640,440],[B(56.5),560,470],[B(57),520,216],[T.out-200,700,220]
  ];
  // camera keyframes [t, focusX, focusY, zoom, rotX, rotY]
  const CAM=[
    [T.app,640,360,1.00,0,0],[T.brief-500,640,360,1.05,0,0],
    [T.brief+500,510,170,1.30,2,0],[T.stats-300,512,170,1.33,2,0],           // briefing
    [T.stats+500,440,262,1.50,1,0],[T.heat-500,840,262,1.50,1,0],           // pan along the stat cards
    [T.heat+500,700,470,1.30,2,0],[B(14.6),700,500,1.36,2,1],               // heatmap
    [T.nvda-600,330,432,1.58,3,-5],[T.nvda,330,450,1.52,2,-3],              // close on NVDA
    [T.nvda+520,640,392,1.12,-2,0],                                          // the full stock card
    [T.tf1-300,600,310,1.36,1,0],[T.tf3+300,640,360,1.48,0,0],[T.perf-200,640,372,1.46,0,0],
    [T.perf+500,500,470,1.75,1,3],[T.fund-250,500,470,1.75,1,3],            // performance
    [T.fund+500,780,470,1.75,1,-3],[T.trend-250,780,470,1.75,1,-3],         // fundamentals
    [T.trend+500,560,262,1.62,2,0],[T.mclose,600,262,1.62,2,0],             // trend line
    [T.sig-500,640,370,1.08,0,0],[T.sig,640,360,1.00,0,0],[T.sigH-400,640,360,1.06,0,0],
    [T.sigH+500,240,300,1.32,1,4],[T.sigM-300,240,300,1.34,1,4],            // high conviction
    [T.sigM+500,620,300,1.34,1,0],[T.radar-300,620,300,1.34,1,0],           // medium
    [T.radar+500,1030,290,1.36,1,-4],[T.ai-600,1030,290,1.38,1,-4],         // buy radar
    [T.ai-150,640,360,1.03,0,0],[T.ai,640,360,1.00,0,0],
    [T.ai+700,524,180,1.25,3,0],[T.ai+2200,524,180,1.25,3,0],[T.ai+4600,756,180,1.25,3,0],[T.an0-300,560,190,1.27,3,0],  // follow the AI take as it types
    [T.an0+500,320,330,1.50,2,3],[T.an1-250,320,330,1.52,2,3],
    [T.an1+500,640,330,1.50,2,0],[T.an2-250,640,330,1.52,2,0],
    [T.an2+500,960,330,1.50,2,-3],[T.tabs-250,960,330,1.52,2,-3],
    [T.tabs+450,470,100,1.62,-2,2],[T.ov2-800,810,100,1.62,-2,-2],          // ride along the nav bar
    [T.ov2-150,640,360,1.03,0,0],[T.ov2,640,360,1.00,0,0],
    [B(54),640,360,1.03,-2,0],[B(54.4),640,468,1.30,2,0],[B(56.3),640,468,1.32,2,0],  // heatmap refreshing
    [B(56.9),510,170,1.30,2,0],[B(57.7),512,170,1.32,2,0],                  // recomputed briefing
    [T.out-150,640,360,1.04,0,0],[T.out,640,360,1.00,0,0]
  ];
  function track(K,t,n){ // eased interpolation through keyframes K=[t,...n values]
    if(t<=K[0][0]) return K[0].slice(1);
    const L=K[K.length-1]; if(t>=L[0]) return L.slice(1);
    for(let i=0;i<K.length-1;i++){ if(t>=K[i][0]&&t<K[i+1][0]){
      const e=inOut((t-K[i][0])/(K[i+1][0]-K[i][0])), a=K[i], b=K[i+1], r=[];
      for(let k=1;k<=n;k++) r.push(a[k]+(b[k]-a[k])*e); return r; }}
    return L.slice(1);
  }
  const lit=(nodes,t,start,step,hold)=>nodes.forEach((n,i)=>{const a=start+i*step; n.classList.toggle("gl",t>=a&&t<a+(hold||step));});

  /* ---------------- the timeline ---------------- */
  function seek(t){
    t=clamp(t/DURATION)*DURATION;
    $("prog").style.width=(t/DURATION*100)+"%";
    $("s1").style.opacity=(1-seg(t,T.app-XF,XF)).toFixed(3);
    $("s2").style.opacity=win(t,T.app,T.out,XF,XF).toFixed(3);
    $("s3").style.opacity=Math.min(seg(t,T.out,XF),1-seg(t,DURATION-700,700)).toFixed(3);

    // ---- hook: three lines, then the logo ----
    hooks.forEach((h,i)=>{ const a=B(i)+60, b=B(i+1)-30, o=win(t,a,b,260,220), p=outCubic(seg(t,a,420));
      h.style.opacity=o.toFixed(3);
      h.style.transform=`translateY(${(-50+ (1-p)*40).toFixed(1)}%) scale(${(0.96+0.04*p+0.03*seg(t,a,BAR)).toFixed(3)})`; });
    { const s=B(3), p=clamp(outBack(seg(t,s+60,520)));
      setT("brand",p,0,22*(1-p),0.94+0.06*p);
      A.accent.style.width=(300*outCubic(seg(t,s+380,620)))+"px"; A.accent.style.opacity=seg(t,s+300,200);
      A.s1sub.style.opacity=seg(t,s+280,420); A.s1tag.style.opacity=seg(t,s+560,460); }

    // ---- camera ----
    { const c=track(CAM,t,5); let fx=c[0], fy=c[1]; const z=c[2]+punch(t);
      if(z>1){ // how close the frame may get to the app's outer edge (relaxed where a shot needs the edge)
        const ins=42-30*Math.max(win(t,T.brief,T.heat,500,500),win(t,T.ai,T.tabs,500,500),win(t,B(56.5),T.out,400,300));
        const AL=ins,AR=1280-ins,AT=38-48*win(t,T.tabs,T.ov2,400,400),AB=682, mx=640/z, my=360/z, xa=AL+mx, xb=AR-mx, ya=AT+my, yb=AB-my;
        fx = xa<=xb ? Math.min(Math.max(fx,xa),xb) : 640;  fy = ya<=yb ? Math.min(Math.max(fy,ya),yb) : 360; }
      const cam=$("cam");
      cam.style.transformOrigin=`${fx.toFixed(1)}px ${fy.toFixed(1)}px`;
      cam.style.transform=`translate(${(640-fx).toFixed(1)}px,${(360-fy).toFixed(1)}px) scale(${z.toFixed(3)}) `+
        `rotateX(${c[3].toFixed(2)}deg) rotateY(${c[4].toFixed(2)}deg)`; }

    // ---- app shell ----
    { const p=clamp(outBack(seg(t,T.app,480))); setT("app",p,0,0,0.985+0.015*p); }
    for(const k in panels) panels[k].style.opacity=panelOp(k,t).toFixed(3);
    let curTab="Overview"; for(const v of VIEWS) if(t>=v[0]-140&&t<v[1]) curTab=v[3];
    const [cx,cy]=track(WP,t,2);
    const ribbon=t>T.tabs+250&&t<T.ov2-650;
    for(const k in tabs){ tabs[k].classList.toggle("act",k===curTab);
      tabs[k].classList.toggle("hov",ribbon&&k!==curTab&&cx>=tabBox[k][0]&&cx<tabBox[k][1]); }
    if(!tapeW) tapeW=tapeEl.scrollWidth/2;
    tapeEl.style.transform=`translateX(${(-((t/11000)%1)*tapeW).toFixed(1)}px)`;
    $("livedot").style.opacity=(0.4+0.6*Math.abs(Math.sin(t/(t>T.ov2?320:560)))).toFixed(2);

    // ---- overview ----
    { const hp=clamp((t-(T.app+200))/1300);
      const rp=clamp((t-B(54.3))/1300);                       // auto-refresh morph
      hmBlk.forEach((b,i)=>{ b.style.opacity=clamp(hp*hm.length-i).toFixed(3);
        const loc=clamp(rp*1.35-i*0.045), v=hm[i][1]+(hm2v[i]-hm[i][1])*inOut(loc);
        hmVal[i].textContent=fmtv(v); b.style.background=hmColorC(v);
        b.style.filter=`brightness(${(1+0.5*Math.sin(loc*Math.PI)).toFixed(2)})`; });
      // tiles the cursor rests on
      const hot=[[2,T.heat+500,B(13)+900],[4,B(13)+900,B(14)+700],[5,B(14)+700,B(15)],[0,B(15)+400,T.nvda+120]];
      hmBlk.forEach(b=>b.classList.remove("hot")); for(const [i,a,b] of hot) if(t>=a&&t<b) hmBlk[i].classList.add("hot");
      // numbers count up as the dashboard loads, then pop when the camera visits them
      const cu=outCubic(seg(t,T.app+350,1200));
      stVals[1].textContent=Math.round(29*cu); stVals[2].textContent=Math.round(10*cu);
      stCards.forEach((c,i)=>{ const a=T.stats+i*BAR+250; c.classList.toggle("gl",t>=a&&t<a+BAR);
        stVals[i].style.transform=`scale(${(1+0.14*bump(t,a,420)).toFixed(3)})`; });
      brief.classList.toggle("gl",(t>T.brief+300&&t<T.stats-150)||(t>B(56.8)&&t<T.out-250));
      // refresh: toast + green pulse, then briefing and sentiment recompute
      $("refresh").style.opacity=win(t,T.ov2+500,B(54.4),220,260).toFixed(2);
      appEl.classList.toggle("refreshing",t>T.ov2+550&&t<B(54.4));
      const g=inOut(clamp((t-B(54.5))/600)), uu=Math.round(5*g);
      $("bUp").textContent=`${uu} are up`; $("bDn").textContent=`${8-uu} are down`;
      $("sentSub").textContent=`${uu} up · ${10-uu} down of 10`;
      $("bDot").textContent=uu>=4?"🟡":"🔴"; $("bLean").textContent=uu>=4?"turning mixed":"leaning negative";
      $("sentV").textContent=uu>=4?"Mixed":"Bearish"; $("sentV").className=uu>=4?"v":"v dn";
      $("hmUpd").textContent=g>0.15?"↻ updated just now":"updated 2h ago"; }

    // ---- stock card ----
    { const openP=clamp(outBack(seg(t,T.nvda,480))), m=$("modal");
      m.style.opacity=Math.min(openP,1-seg(t,B(27.6),300)).toFixed(3);
      m.style.transform=`translate(-50%,-50%) scale(${(0.72+0.28*openP).toFixed(3)})`;
      let cur=0; TF.forEach((f,i)=>{ if(t>=f[0]) cur=i; });
      pills.forEach((s,i)=>s.classList.toggle("on",i===TF[cur][1]));
      TF.forEach((f,i)=>{ const st=f[0]+(i?90:0), draw=outCubic(seg(t,st,560));
        const gone=i<TF.length-1?seg(t,TF[i+1][0],220):0;
        tfG[i].style.opacity=(clamp(seg(t,st,180))*(1-gone)).toFixed(3);
        tfG[i].style.clipPath=`inset(0 ${((1-draw)*100).toFixed(1)}% 0 0)`; });
      mBoxes[0].classList.toggle("gl",t>T.perf+300&&t<T.fund-100);
      mBoxes[1].classList.toggle("gl",t>T.fund+300&&t<T.trend-100);
      mNums.forEach((ns,bi)=>ns.forEach((n,i)=>{ const a=(bi?T.fund:T.perf)+550+i*380;
        n.style.display="inline-block"; n.style.transform=`scale(${(1+0.28*bump(t,a,420)).toFixed(3)})`; }));
      const tr=outCubic(seg(t,T.trend+350,1500)); mSub.classList.toggle("gl",t>T.trend+300&&t<B(27.6));
      mSub.style.backgroundSize=`${(tr*100).toFixed(1)}% 2px`; }

    // ---- signals ----
    { $("sc1").style.transform=`translateY(${(-235*inOut(seg(t,T.sigH+700,4300))).toFixed(1)}px)`;
      $("sc2").style.transform=`translateY(${(-235*inOut(seg(t,T.sigM+700,4300))).toFixed(1)}px)`;
      lit(rowsH,t,T.sigH+450,490); lit(rowsM,t,T.sigM+450,490);
      rowsR.forEach((r,i)=>{ const a=i<4?T.radar+450+i*1250:T.graded+200, b=i<4?a+1250:T.ai-250;
        r.classList.toggle("gl",t>=a&&t<b); }); }

    // ---- AI analysis ----
    { reveal(aiWords,seg(t,T.ai+500,5200));
      [T.an0,T.an1,T.an2].forEach((a,i)=>{ const p=seg(t,a+450,2100);
        reveal(anWords[i],p); anCards[i].classList.toggle("gl",t>=a+250&&t<a+2*BAR-150);
        anSk[i].style.opacity=(p>0?0:0.35+0.3*Math.abs(Math.sin(t/420+i))).toFixed(2); }); }

    // ---- caption ----
    { let cb=null; for(const c of CAPS) if(t>=c[0]&&t<c[1]) cb=c; const cap=$("cap");
      if(cb){ $("captxt").textContent=cb[2]; cap.style.opacity=win(t,cb[0]+80,cb[1],200,200).toFixed(3); }
      else cap.style.opacity=0; }

    // ---- cursor + click ring ----
    { const cur=$("cursor"), ring=$("ring");
      cur.style.opacity=(t>T.app-100&&t<T.out-100)?1:0; cur.style.transform=`translate(${cx.toFixed(1)}px,${cy.toFixed(1)}px)`;
      let rr=-1; for(const ct of CLICKS){ const e=seg(t,ct-40,340); if(e>0&&e<1) rr=e; }
      if(rr>=0){ const sz=8+rr*50; ring.style.opacity=((1-rr)*0.95).toFixed(3); ring.style.width=sz+"px"; ring.style.height=sz+"px";
        ring.style.transform=`translate(${(cx+2).toFixed(1)}px,${(cy+4).toFixed(1)}px)`; } else ring.style.opacity=0; }

    // ---- outro ----
    { const p=clamp(outBack(seg(t,T.out+120,560))); setT("obrand",p,0,0,0.9+0.1*p);
      chips.forEach((c,i)=>{ const q=outCubic(seg(t,T.out+1200+i*560,460));
        c.style.opacity=q.toFixed(3); c.style.transform=`translateY(${((1-q)*14).toFixed(1)}px)`; });
      A.octa.style.opacity=seg(t,T.out+4700,560); A.osub.style.opacity=seg(t,T.out+5500,640);
      $("s3").style.transform=`scale(${(1+0.035*seg(t,T.out,DURATION-T.out)).toFixed(4)})`; }
  }
  window.__seek=seek; window.__DURATION=DURATION; window.__T=T; seek(0); window.__READY__=true;
})();
