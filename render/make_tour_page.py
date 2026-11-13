#!/usr/bin/env python3
"""Assemble src/venture-2min.html (the 2-minute guided tour).

The tour reuses the dashboard recreation from src/openbb.html (styles + markup)
and swaps in a longer timeline (render/tour_script.js) plus the few extra
elements that timeline needs: hook lines, glow states, outro chips.

Run:  python3 render/make_tour_page.py
"""
import os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src = open(os.path.join(ROOT, 'src', 'openbb.html'), encoding='utf-8').read()
script = open(os.path.join(ROOT, 'render', 'tour_script.js'), encoding='utf-8').read()

head = src[:src.index('<script>')]

def sub(pattern, repl, text, flags=re.S):
    out, n = re.subn(pattern, lambda m: repl, text, count=1, flags=flags)
    assert n == 1, 'pattern not found: ' + pattern[:60]
    return out

head = sub(r'<title>.*?</title>', '<title>Venture Trader — 2 minute tour</title>', head)

EXTRA_CSS = """
  /* ---- 2-minute tour additions ---- */
  #s1{gap:0;}
  .s1-stack{display:flex;flex-direction:column;align-items:center;gap:18px;}
  .hk{position:absolute;left:0;right:0;top:50%;text-align:center;font-size:50px;font-weight:800;
    letter-spacing:-1.4px;opacity:0;will-change:transform,opacity;}
  .hk span{color:var(--accent);text-shadow:0 0 34px rgba(0,212,255,.45);}
  .st .v{transform-origin:left center;}
  .st.gl{border-color:rgba(0,212,255,.65);box-shadow:0 0 0 1px rgba(0,212,255,.4),0 0 28px rgba(0,212,255,.2);}
  .brief.gl{box-shadow:0 0 0 1px rgba(0,212,255,.6),0 0 44px rgba(0,212,255,.28);}
  .m-box.gl{border-color:rgba(0,212,255,.65);box-shadow:0 0 0 1px rgba(0,212,255,.4),0 0 24px rgba(0,212,255,.2);}
  .m-sub{display:inline-block;padding-bottom:3px;background:linear-gradient(var(--accent),var(--accent)) no-repeat left bottom;background-size:0 2px;}
  .m-sub.gl{color:#cbd5e1;}
  .radar .rr{padding:6px 8px;border-radius:6px;}
  .radar .rr.gl{background:rgba(0,212,255,.08);box-shadow:inset 3px 0 0 var(--accent);color:#e2e8f0;}
  .nav span.hov{color:#e2e8f0;background:rgba(0,212,255,.12);border-radius:7px 7px 0 0;border-bottom-color:rgba(0,212,255,.45);}
  .an{position:relative;}
  .sk{position:absolute;left:13px;right:13px;top:54px;display:flex;flex-direction:column;gap:8px;pointer-events:none;}
  .sk i{display:block;height:9px;border-radius:5px;background:linear-gradient(90deg,#1b2740,#2a3d63);}
  .sk i:last-child{width:62%;}
  .cap{white-space:nowrap;max-width:1180px;}
  .col h4{position:relative;z-index:3;background:#141d30;margin:-12px -13px 0;padding:12px 13px 8px;}
  .chips{display:flex;gap:10px;}
  .chips span{padding:8px 15px;border-radius:20px;border:1px solid var(--border);background:rgba(17,24,39,.85);
    font-size:13px;font-weight:600;color:var(--text);opacity:0;}
  #s3{gap:22px;transform-origin:50% 50%;}
"""
head = head.replace('</style>', EXTRA_CSS + '</style>', 1)

MARK = ('<div class="mark"><svg viewBox="0 0 24 24" fill="none"><path d="M4 19V5M4 19h16M8 16V11M12 16V7M16 16v-3M20 16V9" '
        'stroke="#04121a" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>')
S1 = f"""<section class="scene" id="s1">
    <div class="hk" id="hk0">Markets move <span>fast.</span></div>
    <div class="hk" id="hk1">The signal gets buried in the <span>noise.</span></div>
    <div class="hk" id="hk2">What if it was all <span>read for you?</span></div>
    <div class="s1-stack">
      <div class="brand anim" data-a="brand">{MARK}<div class="wordmark">Venture <span>Trader</span></div></div>
      <div class="s1-sub sub anim" data-a="s1sub">Automated Intelligence</div>
      <div class="accentline anim" data-a="accent"></div>
      <div class="tagline anim" data-a="s1tag">Here's everything it does — in two minutes.</div>
    </div>
  </section>"""
head = sub(r'<section class="scene" id="s1">.*?</section>', S1, head)

CHIPS = ('<div class="chips" id="chips"><span>📋 Daily briefing</span><span>🗺 Live heatmap</span>'
         '<span>⚡ 93 signals</span><span>🤖 AI analysis</span><span>↻ Auto-refresh</span></div>\n    ')
head = sub(r'<div class="o-cta anim" data-a="octa">', CHIPS + '<div class="o-cta anim" data-a="octa">', head)

def row(k, sym, ty, msg):
    b = 'High' if k == 'H' else 'Med'
    return (f'<div class="sig {k}"><div class="r"><span class="sy">{sym}</span><span class="badge {k}">{b}</span></div>'
            f'<div class="ty">{ty}</div><div class="ms">{msg}</div></div>')

# longer signal lists (built from tickers already on the tape) so the columns really scroll
MORE_H = ''.join(row('H', *r) for r in [
    ('SNDK $1786.85', 'Top Gainer', 'SNDK top gainer +8.88% — Sandisk'),
    ('AMAT $535.31', 'Top Gainer', 'AMAT top gainer +5.55% — Applied Materials'),
    ('MU $1011.75', 'Top Gainer', 'MU top gainer +4.13% — Micron Technology'),
    ('PFE $25.77', 'Insider Cluster', '3 different insiders buying PFE')])
MORE_M = ''.join(row('M', *r) for r in [
    ('META $568.97', 'Price Move', 'META moved -3.54% to $568.97'),
    ('ORCL $146.65', 'Price Move', 'ORCL moved -2.57% to $146.65'),
    ('AMD $506.00', 'Price Move', 'AMD moved -1.63% to $506.00'),
    ('TSLA $339.30', 'Social Buzz', 'TSLA Reddit buzz 4.1× normal')])
for tail, more in (('IONQ top gainer +11.75% — IonQ Inc</div></div>', MORE_H),
                   ('COIN moved +2.90% to $402.50</div></div>', MORE_M)):
    assert tail in head, tail
    head = head.replace(tail, tail + more, 1)

out = head + '<script>\n' + script + '</script>\n</body>\n</html>\n'
dest = os.path.join(ROOT, 'src', 'venture-2min.html')
open(dest, 'w', encoding='utf-8').write(out)
print('wrote', dest, f'({len(out)//1024} KB)')
