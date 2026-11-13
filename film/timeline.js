/* Venture Trader — the 2-minute film, shot on the real dashboard.

   Everything here is data for film/engine.js: when to click, where the cursor and
   camera go (as selectors into the live page), what to scroll, and the captions.
   128 BPM grid: 1 bar = 1875 ms, 64 bars = 120 s, so scene changes land on downbeats
   of the soundtrack (render/make_audio_film.py uses the same bar numbers).

   Only screens that have live data without private keys are opened. AI Analysis,
   Options Flow, Calendar and the Macro panels need the owner's own keys / local
   model, so the film does not go there. */
window.__TIMELINE=function(E,{AW,AH}){
  const {clamp,outCubic,outBack,seg,win}=E;
  const BAR=1875, B=n=>Math.round(n*BAR), DUR=B(64);

  /* ---- things on the page ---- */
  const all=(d,s)=>[...d.querySelectorAll(s)];
  const card=(page,title)=>d=>all(d,`#page-${page} .card`).find(c=>((c.querySelector(".card-title")||{}).textContent||"").includes(title));
  const nth=(sel,i)=>d=>all(d,sel)[i];
  const tile=sym=>`#page-overview a.hm-blk[data-sym="${sym}"]`;
  const stat=i=>nth("#page-overview .grid-4 .card",i);
  const box=i=>nth("#sd-body .sd-grid .sd-box",i);              // popup: 0 performance, 1 key levels, 2 dividends, 3 earnings & shorts, 4 fundamentals
  const tab=id=>`#tab-${id}`;
  const MID=[AW/2,AH/2];

  /* ---- scene times ---- */
  const T={ app:B(4), brief:B(6), stats:B(8), radar:B(10), heat:B(12), next:B(12.8), prev:B(13.7),
    pop:B(16), tf1:B(18), tf2:B(19), tf3:B(20), read:B(21), levels:B(22.3), lower:B(23.5), fund:B(25), close1:B(26.6),
    search:B(28), pick:B(29.4), close2:B(31.5),
    watch:B(32), mkts:B(36), gain:B(37.3), lose:B(38.6),
    crypto:B(40), sig:B(44), score:B(46), buzz:B(48.5), lists:B(50.5),
    fundTab:B(53), news:B(54.25), nfilter:B(54.85), disc:B(55.5), ins:B(56.75), out:B(58) };

  /* ---- real input: mouse clicks and key presses the recorder performs ---- */
  const typed="tesla".split("").map((ch,i)=>[T.search+320+i*190,"text",ch]);
  // each click names what must be under the cursor; the recorder refuses to click anything else
  const actions=[
    [T.app-520,"load"],
    [T.next,"click",".hm-side-r"], [T.prev,"click",".hm-side-l"],          // heatmap: next sector, and back
    [T.pop,"click",'a.hm-blk[data-sym="NVDA"]'], [T.pop,"wait","document.querySelector('#sd-overlay').classList.contains('open')","the stock popup"],
    [T.tf1,"click","#tf-1D"], [T.tf2,"click","#tf-1Y"], [T.tf3,"click","#tf-5Y"],
    [T.close1,"click",".sd-close"],
    [T.search,"click","#lk-in"], ...typed,
    [T.pick,"click","#lk-row-0"], [T.close2,"click",".sd-close"],
    [T.watch,"click","#tab-watchlist"], [T.mkts,"click","#tab-markets"], [T.gain,"click",".mk-tab"], [T.lose,"click",".mk-tab"],
    [T.crypto,"click","#tab-crypto"], [T.sig,"click","#tab-signals"],
    [T.fundTab,"click","#tab-fundamentals"], [T.news,"click","#tab-news"], [T.nfilter,"click",".nf-pill"],
    [T.disc,"click","#tab-discover"], [T.ins,"click","#tab-insiders"],
  ].sort((a,b)=>a[0]-b[0]);

  /* ---- cursor: [time, where] ---- */
  const cursor=[
    [T.app,[1000,420]], [B(5.2),[820,330]],
    [T.brief+500,{s:"#page-overview .brief",ax:.3,ay:.62}], [T.stats-300,{s:"#page-overview .brief",ax:.62,ay:.7}],
    [T.stats+500,{s:stat(0),ay:.6}], [B(8.9),{s:stat(1),ay:.6}], [B(9.5),{s:stat(2),ay:.6}],
    [T.radar+900,{s:card("overview","Buy Radar"),ax:.25,ay:.42}], [T.heat-300,{s:card("overview","Buy Radar"),ax:.3,ay:.8}],
    [T.heat+900,{s:"#page-overview .hm-wrap",ax:.55,ay:.4}],
    [T.next-250,".hm-side-r"], [T.next,".hm-side-r"], [T.prev-300,".hm-side-l"], [T.prev,".hm-side-l"],
    [B(14.6),tile("AVGO")], [B(15.3),tile("AMD")], [T.pop-250,tile("NVDA")], [T.pop,tile("NVDA")],
    [B(17),{s:"#sd-chart",ax:.55,ay:.5}],
    [T.tf1-220,"#tf-1D"], [T.tf1,"#tf-1D"], [T.tf2-250,"#tf-1Y"], [T.tf2,"#tf-1Y"], [T.tf3-250,"#tf-5Y"], [T.tf3,"#tf-5Y"],
    [B(20.6),{s:"#sd-chart",ax:.6,ay:.55}],
    [T.read+900,{s:"#sd-cap",ax:.3,dy:34}], [T.levels-250,{s:box(0),ax:.5,ay:.6}], [T.levels+500,{s:box(1),ax:.45,ay:.6}],
    [T.lower+900,{s:box(2),ax:.5,ay:.65}], [B(24.4),{s:box(3),ax:.5,ay:.6}], [T.fund+500,{s:box(4),ax:.4,ay:.6}],
    [T.close1-900,{s:box(4),ax:.6,ay:.5}], [T.close1-150,".sd-close"], [T.close1,".sd-close"],
    [T.search-250,"#lk-in"], [T.search,"#lk-in"], [B(29),{s:"#lk-in",ax:.8,ay:.6}],
    [T.pick-250,"#lk-row-0"], [T.pick,"#lk-row-0"],
    [B(30.4),{s:"#sd-chart",ax:.5,ay:.5}], [T.close2-300,".sd-close"], [T.close2,".sd-close"],
    [T.watch-200,tab("watchlist")], [T.watch,tab("watchlist")],
    [B(33),{s:nth("#page-watchlist tbody tr",1),ax:.2}], [B(34.2),{s:nth("#page-watchlist tbody tr",3),ax:.5}], [B(35.3),{s:nth("#page-watchlist tbody tr",6),ax:.8}],
    [T.mkts-200,tab("markets")], [T.mkts,tab("markets")],
    [T.gain-250,nth(".mk-tab",1)], [T.gain,nth(".mk-tab",1)], [T.lose-250,nth(".mk-tab",2)], [T.lose,nth(".mk-tab",2)],
    [B(39.4),{s:"#mkv-losers",ax:.4,ay:.3}],
    [T.crypto-200,tab("crypto")], [T.crypto,tab("crypto")],
    [B(41),{s:"#cx-chart-BTC-USD",ax:.5,ay:.45}], [B(42.2),{s:"#cx-chart-ETH-USD",ax:.5,ay:.5}], [B(43.3),{s:card("crypto","Technicals"),ax:.4,ay:.6}],
    [T.sig-200,tab("signals")], [T.sig,tab("signals")],
    [B(45),{s:card("signals","Buy Radar"),ax:.3,ay:.35}], [T.score+900,{s:card("signals","Scorecard"),ax:.3,ay:.55}],
    [T.buzz+900,{s:card("signals","Reddit Buzz"),ax:.2,ay:.4}], [B(50),{s:card("signals","Reddit Buzz"),ax:.4,ay:.7}],
    [T.lists+900,{s:card("signals","High Conviction"),ax:.5,ay:.25}], [B(52.4),{s:card("signals","Medium Conviction"),ax:.5,ay:.4}],
    [T.fundTab-200,tab("fundamentals")], [T.fundTab,tab("fundamentals")], [B(53.7),{s:card("fundamentals","company health"),ax:.45,ay:.5}],
    [T.news-200,tab("news")], [T.news,tab("news")], [T.nfilter-150,nth(".nf-pill",3)], [T.nfilter,nth(".nf-pill",3)],
    [T.disc-200,tab("discover")], [T.disc,tab("discover")], [B(56.2),{s:"#dc-grid",ax:.5,ay:.3}],
    [T.ins-200,tab("insiders")], [T.ins,tab("insiders")], [B(57.6),{s:card("insiders","Cluster Buys"),ax:.3,ay:.35}],
  ];

  /* ---- camera: [time, focus, zoom, tiltX, tiltY]  (zoom 1 = the app fills the frame) ---- */
  const cam=[
    [T.app,MID,1,0,0], [T.brief-500,MID,1.06,0,0],
    [T.brief+500,{s:"#page-overview .brief",ax:.38},1.5,2,0], [T.stats-300,{s:"#page-overview .brief",ax:.5},1.55,2,0],
    [T.stats+500,stat(0),1.7,1,2], [T.radar-400,stat(3),1.7,1,-2],
    [T.radar+900,{s:card("overview","Buy Radar"),ax:.36,ay:.4},1.45,2,2], [T.heat-300,{s:card("overview","Buy Radar"),ax:.4,ay:.75},1.5,2,2],
    [T.heat+900,"#page-overview .hm-wrap",1.12,1,0], [B(14.2),"#page-overview .hm-wrap",1.16,1,0],
    [T.pop-500,tile("NVDA"),1.7,3,-4], [T.pop,tile("NVDA"),1.62,2,-3],
    [T.pop+700,{s:"#sd-chart",ay:.1},1.3,-1,0], [T.tf1-300,"#sd-tfbar",1.75,1,2],
    [T.tf3+400,{s:"#sd-chart",ay:.45},1.6,0,0], [T.read-200,{s:"#sd-chart",ay:.5},1.62,0,0],
    [T.read+900,{s:"#sd-cap",ax:.45,dy:60},1.7,1,2], [T.levels-250,{s:box(0),ax:.6},1.8,1,2],
    [T.levels+500,{s:box(1),ax:.4},1.8,1,-2], [T.lower-200,{s:box(1),ax:.4},1.8,1,-2],
    [T.lower+900,{s:box(2),ax:1,ay:.6},1.55,1,0], [T.fund-250,{s:box(2),ax:1,ay:.6},1.58,1,0],
    [T.fund+500,{s:box(4),ay:.5},1.6,2,0], [T.close1-900,{s:box(4),ay:.4},1.55,1,0],
    [T.close1-250,{s:"#sd-body .sd-hd",ax:.75,ay:1},1.3,0,0], [T.close1+400,MID,1.04,0,0],
    [T.search-300,{s:"#lk-in",dx:-40,dy:60},1.75,1,-2], [T.pick,{s:"#lk-in",dx:-40,dy:90},1.8,1,-2],
    [T.pick+800,{s:"#sd-chart",ay:.2},1.3,-1,0], [B(31),{s:"#sd-chart",ay:.5},1.5,0,0], [T.close2+300,MID,1.04,0,0],
    [T.watch,MID,1,0,0], [B(33),{s:"#page-watchlist table",ax:.3,ay:.4},1.5,1,3], [B(35.4),{s:"#page-watchlist table",ax:.7,ay:.5},1.5,1,-3],
    [T.mkts-150,MID,1.03,0,0], [T.mkts,MID,1,0,0], [T.gain-400,{s:nth(".mk-tab",1),dx:160,dy:130},1.55,1,3],
    [B(39.6),{s:"#mkv-losers",ax:.45,ay:.25},1.5,1,-2],
    [T.crypto-150,MID,1.03,0,0], [T.crypto,MID,1,0,0], [B(41),{s:card("crypto","BTC"),ax:.6,ay:.5},1.7,1,3],
    [B(42.4),{s:card("crypto","ETH"),ax:.5,ay:.5},1.7,1,0], [B(43.4),{s:card("crypto","Technicals"),ax:.4,ay:.5},1.35,1,0],
    [T.sig-150,MID,1.03,0,0], [T.sig,MID,1,0,0], [B(45),{s:card("signals","Buy Radar"),ax:.35,ay:.3},1.5,1,3],
    [T.score-200,{s:card("signals","Buy Radar"),ax:.4,ay:.5},1.5,1,3],
    [T.score+900,{s:card("signals","Scorecard"),ax:.3,ay:.5},1.4,2,0], [T.buzz-200,{s:card("signals","Scorecard"),ax:.32,ay:.5},1.43,2,0],
    [T.buzz+900,{s:card("signals","Reddit Buzz"),ax:.25,ay:.4},1.4,1,2], [T.lists-200,{s:card("signals","Reddit Buzz"),ax:.3,ay:.6},1.4,1,2],
    [T.lists+900,{s:card("signals","High Conviction"),ax:.8,ay:.3},1.35,1,2], [B(52.8),{s:card("signals","Medium Conviction"),ax:.5,ay:.5},1.4,1,0],
    [T.fundTab-120,MID,1.03,0,0], [T.fundTab,MID,1,0,0], [B(53.8),{s:card("fundamentals","company health"),ax:.3,ay:.5},1.38,1,2],
    [T.news,MID,1,0,0], [B(55.2),{s:"#nf-feed",ax:.35,ay:.25},1.4,1,2],
    [T.disc,MID,1,0,0], [B(56.4),{s:"#dc-grid",ax:.5,ay:.3},1.3,1,0],
    [T.ins,MID,1,0,0], [B(57.5),{s:card("insiders","Cluster Buys"),ax:.25,ay:.3},1.4,1,2],
    [T.out-150,MID,1.03,0,0], [T.out,MID,1,0,0],
  ];
  const punch=[[T.app,.022],[T.pop,.022],[T.tf1,.008],[T.tf2,.008],[T.tf3,.008],[T.search,.012],[T.pick,.016],
    [T.watch,.018],[T.mkts,.018],[T.crypto,.018],[T.sig,.022],[T.fundTab,.02],[T.news,.012],[T.disc,.012],[T.ins,.012]];

  /* ---- scrolling the real page: [time, target]  ({s, top} = bring that element `top` px below the top) ---- */
  const radarTop={s:card("overview","Buy Radar"),top:150}, heatTop={s:card("overview","Market Heatmap"),top:132};
  const scoreTop={s:card("signals","Scorecard"),top:160}, buzzTop={s:card("signals","Reddit Buzz"),top:150};
  const listTop={s:card("signals","High Conviction"),top:150}, listLow={s:card("signals","High Conviction"),top:-150};
  const techTop={s:card("crypto","Technicals"),top:330}, clusterTop={s:card("insiders","Cluster Buys"),top:140};
  const scroll=[
    [0,0], [T.radar-100,0], [T.radar+900,radarTop], [T.heat-100,radarTop], [T.heat+900,heatTop],
    [T.watch-1,heatTop], [T.watch,0],
    [T.crypto,0], [B(42.6),0], [B(43.5),techTop],
    [T.sig-1,techTop], [T.sig,0], [T.score-100,0], [T.score+900,scoreTop], [T.buzz-100,scoreTop], [T.buzz+900,buzzTop],
    [T.lists-100,buzzTop], [T.lists+900,listTop], [T.fundTab-150,listLow],
    [T.fundTab-1,listLow], [T.fundTab,0], [T.ins,0], [T.ins+800,clusterTop],
  ];
  // the stock popup scrolls inside its own overlay
  const scrollers=[{box:"#sd-overlay",keys:[
    [0,0], [T.read-100,0], [T.read+900,{s:"#sd-cap",top:150}], [T.lower-100,{s:"#sd-cap",top:150}],
    [T.lower+900,{s:box(2),top:170}], [T.fund-100,{s:box(2),top:170}], [T.fund+700,{s:box(4),top:220}],
    [T.close1-900,{s:box(4),top:220}], [T.close1-300,0],      // back to the top so the close button is on screen
  ]}];

  const captions=[
    [T.app,   T.brief, "This is Venture Trader — running live on today's market."],
    [T.brief, T.stats, "It opens with a plain-English briefing of the day."],
    [T.stats, T.radar, "Sentiment, live signal counts and everything it tracks."],
    [T.radar, T.heat,  "Buy Radar spots setups while they're still forming."],
    [T.heat,  B(14.2), "The heatmap: the US market, one sector per slide."],
    [B(14.2), T.pop,   "Red is down, green is up — sized by market cap."],
    [T.pop,   T.tf1,   "Click any ticker and the full picture opens, fetched live."],
    [T.tf1,   T.read,  "Six timeframes, from today's minutes to five years."],
    [T.read,  T.lower, "A pattern read: RSI, momentum, volatility, key levels."],
    [T.lower, T.close1,"Dividends, short interest and fundamentals in one card."],
    [T.search,T.pick+600,"Not on your list? Search any ticker or company."],
    [T.pick+600,T.watch-150,"Same depth for any stock."],
    [T.watch, T.mkts,  "Your watchlist: price, 52-week range, health and growth."],
    [T.mkts,  T.gain,  "A full US market screener."],
    [T.gain,  T.crypto,"Most active, top gainers, top losers."],
    [T.crypto,B(42.4), "Crypto streams live from Kraken, tick by tick."],
    [B(42.4), T.sig,   "With daily technicals and crypto news underneath."],
    [T.sig,   T.score, "Signals: every live read on the market, in one place."],
    [T.score, T.buzz,  "A scorecard grades every call as it matures — 1, 5 and 20 days out."],
    [T.buzz,  T.lists, "Reddit buzz shows what the crowd is piling into."],
    [T.lists, T.fundTab,"And every signal is ranked by conviction."],
    [T.fundTab,T.news, "Fundamentals: company health at a glance."],
    [T.news,  T.disc,  "News from the wires, filterable."],
    [T.disc,  T.ins,   "Discover: a magazine of the financial press."],
    [T.ins,   T.out-150,"Insiders: cluster buys across the whole market."],
  ];

  /* ---- hook + outro cards ---- */
  const HOOK=["Markets move <span>fast.</span>","The signal gets buried in the <span>noise.</span>","What if it was all <span>read for you?</span>"];
  const CHIPS=["📋 Daily briefing","🗺 Sector heatmap","🔍 Any-ticker lookup","⚡ Signal engine","₿ Live crypto","🧾 Fundamentals","📰 News &amp; Discover","🏛 Insider clusters"];
  let built=false;
  function extra(t,{$}){
    if(!built){ built=true; HOOK.forEach((h,i)=>$("hk"+i).innerHTML=h);
      $("h-tag").textContent="Here's the real thing — in two minutes.";
      $("chips").innerHTML=CHIPS.map(c=>`<span>${c}</span>`).join(""); }
    $("prog").style.width=(t/DUR*100)+"%";
    $("hook").style.opacity=(1-seg(t,T.app-260,260)).toFixed(3);
    $("view").style.opacity=t>=T.app-300?1:0;
    $("outro").style.opacity=Math.min(seg(t,T.out,260),1-seg(t,DUR-700,700)).toFixed(3);
    for(let i=0;i<3;i++){ const h=$("hk"+i), a=B(i)+60, b=B(i+1)-30, p=outCubic(seg(t,a,420));
      h.style.opacity=win(t,a,b,260,220).toFixed(3);
      h.style.transform=`translateY(${(-50+(1-p)*40).toFixed(1)}%) scale(${(0.96+0.04*p+0.03*seg(t,a,BAR)).toFixed(3)})`; }
    { const s=B(3), p=clamp(outBack(seg(t,s+60,520))), br=$("h-brand");
      br.style.opacity=p; br.style.transform=`translateY(${(22*(1-p)).toFixed(1)}px) scale(${(0.94+0.06*p).toFixed(3)})`;
      $("h-line").style.width=(300*outCubic(seg(t,s+380,620)))+"px";
      $("h-sub").style.opacity=seg(t,s+280,420); $("h-tag").style.opacity=seg(t,s+560,460); }
    { const p=clamp(outBack(seg(t,T.out+120,560))), br=$("o-brand");
      br.style.opacity=p; br.style.transform=`scale(${(0.9+0.1*p).toFixed(3)})`;
      [...$("chips").children].forEach((c,i)=>{ const q=outCubic(seg(t,T.out+1100+i*330,440));
        c.style.opacity=q.toFixed(3); c.style.transform=`translateY(${((1-q)*14).toFixed(1)}px)`; });
      $("o-btn").style.opacity=seg(t,T.out+4700,560); $("o-sub").style.opacity=seg(t,T.out+5500,640);
      $("outro").style.transform=`scale(${(1+0.035*seg(t,T.out,DUR-T.out)).toFixed(4)})`; }
  }

  return { duration:DUR, actions, cursor, cam, punch, scroll, scrollers, captions, extra,
           cursorOn:t=>t>T.app-100&&t<T.out-100 };
};
