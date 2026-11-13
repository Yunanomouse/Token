#!/usr/bin/env python3
"""Synthesize the trailer soundtrack from scratch (numpy, STEREO) — no samples.

Musical grid = 128 BPM (bar = 1.875s). Every video cut lands on a downbeat:

    2250  drop / app slam        (whoosh + big impact)
    6000  open ticker card       (whoosh + impact)
    7875  timeframe pill tick     (UI blip)
    9750  Signals tab            (whoosh + impact)
   13500  AI tab                 (whoosh + impact)
   17250  Overview / auto-refresh(whoosh + impact)
   21000  outro resolve          (big impact, beat drops out, bright chord)
   24000  end

Run:  python3 render/make_audio.py   ->  dist/track.wav  (stereo)
"""
from synth import *

start(24.0)

# ---- arrangement (128 BPM) ----
BEAT=60/128; H=BEAT/2
CH={'Am':[220.00,261.63,329.63],'F':[174.61,220.00,261.63],
    'C':[261.63,329.63,392.00],'G':[196.00,246.94,293.66],
    'Cmaj':[261.63,329.63,392.00,523.25]}
ROOT={'Am':55.00,'F':43.65,'C':65.41,'G':49.00}
DROP=2.25; ENDBEAT=21.0
blocks=[(2.25,'Am'),(6.0,'F'),(9.75,'C'),(13.5,'G'),(17.25,'Am')]
BLEN=3.75

# intro riser + accelerating stereo ticks into the drop
mix(0.1, riser(2.15,150,1700), 0.30, 0.0)
tk,gap,pan=2.22,0.30,-0.5
while tk>0.4:
    mix(tk, hat(0.033,0.7), 0.5, pan); tk-=gap; gap=max(0.065,gap*0.82); pan=-pan

# four-on-floor kick (centered)
t=DROP
while t<ENDBEAT: mix(t,kick(),0.95,0.0); t+=BEAT
# backbeat snare (beats 2 & 4)
t=DROP+BEAT
while t<ENDBEAT-0.1: mix(t,snare(),0.42,0.0); t+=2*BEAT
# 16th hats: closed alternating L/R, open on the 8th offbeat
t=DROP; i=0
while t<ENDBEAT-0.05:
    mix(t, hat(0.026,0.5), 0.46, -0.35 if i%2 else 0.35)
    mix(t+H, hat(0.09,0.75), 0.30, 0.55 if i%2 else -0.55)
    t+=BEAT; i+=1
# bass (centered)
for st,ch in blocks:
    r=ROOT[ch]; b=st
    while b<st+BLEN and b<ENDBEAT:
        mix(b,bass(r,0.44),0.9,0.0); mix(b+H,bass(r*2,0.20),0.5,0.0); b+=BEAT
# arpeggio 16ths, panned alternately for width
for st,ch in blocks:
    tn=CH[ch]; seq=[tn[0],tn[1],tn[2],tn[1]*2,tn[2],tn[1],tn[0]*2,tn[1]]
    k=0; a=st
    while a<st+BLEN and a<ENDBEAT:
        mix(a,pluck(seq[k%len(seq)],0.22),0.19, -0.5 if k%2 else 0.5); k+=1; a+=H
# pad
for st,ch in blocks:
    mix(st,pad(CH[ch],min(BLEN,ENDBEAT-st)+0.3),0.20,0.0)

# scene-cut accents (stereo whoosh = two panned noise sweeps)
for ct in (6.0,9.75,13.5,17.25):
    mix(ct-0.5, whoosh(0.56,0.88),0.30,-0.8)
    mix(ct-0.5, whoosh(0.56,0.88),0.30, 0.8)
    mix(ct, impact(0.85,64),0.55,0.0)
mix(7.875, blip(1300,0.09),0.30, 0.4)          # timeframe pill tick
mix(DROP-0.55, whoosh(0.6,0.9),0.42,-0.8)      # the drop
mix(DROP-0.55, whoosh(0.6,0.9),0.42, 0.8)
mix(DROP, impact(1.1,80),0.85,0.0)

# outro 21.0 -> 24.0
mix(20.5, whoosh(0.55,0.92),0.34,-0.8)
mix(20.5, whoosh(0.55,0.92),0.34, 0.8)
mix(ENDBEAT, impact(1.5,84),0.95,0.0)
mix(ENDBEAT, pad(CH['Cmaj'],2.8),0.34,0.0)
sh=[523.25,659.25,783.99,1046.50]
for i,a in enumerate([21.05,21.30,21.6,21.95,22.4]):
    mix(a, pluck(sh[i%4],0.5),0.16, -0.5 if i%2 else 0.5)
mix(22.6, impact(1.4,60),0.4,0.0)              # low tail boom

write()
