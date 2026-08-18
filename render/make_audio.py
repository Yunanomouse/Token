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
import os, struct, math
import numpy as np

SR = 44100
DUR = 24.0
N = int(SR * DUR)
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(7)

def mix(t, sig, gain=1.0, pan=0.0):
    """Mix mono sig at time t with equal-power pan (-1 L .. +1 R)."""
    i0 = int(t * SR)
    if i0 < 0:
        sig = sig[-i0:]; i0 = 0
    i1 = min(N, i0 + len(sig))
    if i0 >= N or i1 <= i0: return
    s = sig[:i1-i0]
    a = (pan+1)*math.pi/4
    L[i0:i1] += s*gain*math.cos(a)
    R[i0:i1] += s*gain*math.sin(a)

def tarr(d): return np.arange(int(d*SR))/SR

def adsr(nn,a,d,s,r,sus=0.6):
    e=np.full(nn,sus); ai,di,ri=int(a*SR),int(d*SR),int(r*SR); ai=min(ai,nn)
    if ai>0: e[:ai]=np.linspace(0,1,ai)
    if di>0:
        j1=min(nn,ai+di); e[ai:j1]=np.linspace(1,sus,j1-ai)
    if ri>0: e[nn-ri:]=np.linspace(sus,0,ri)
    return e

# ---- voices ----
def kick(dur=0.28):
    t=tarr(dur); x=t/dur; f=150*np.exp(-16*x)+48
    o=np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-9.5*x)
    ck=int(0.004*SR); o[:ck]+=(rng.random(ck)*2-1)*np.linspace(1,0,ck)*0.5
    return o

def snare(dur=0.16):
    t=tarr(dur); x=t/dur; nz=rng.random(len(t))*2-1
    return (nz*0.8+np.sin(2*np.pi*190*t)*0.5)*np.exp(-15*x)

def hat(dur=0.028,lvl=1.0):
    n=int(dur*SR); x=np.arange(n)/n; nz=rng.random(n)*2-1
    return np.diff(nz,prepend=nz[0])*np.exp(-40*x)*lvl

def bass(freq,dur):
    t=tarr(dur); e=adsr(len(t),0.005,0.05,0,0.05,0.85); ph=freq*t
    return (np.sin(2*np.pi*ph)*0.7+np.sin(2*np.pi*2*ph)*0.22+np.sin(2*np.pi*3*ph)*0.08)*e

def pluck(freq,dur,det=0.006):
    t=tarr(dur); x=t/dur; a=np.exp(-6*x)
    return (np.sin(2*np.pi*freq*t)+np.sin(2*np.pi*freq*(1+det)*t)*0.7
            +np.sin(2*np.pi*freq*(1-det)*t)*0.7+np.sin(2*np.pi*2*freq*t)*0.3)*a

def pad(freqs,dur):
    t=tarr(dur); e=adsr(len(t),0.3,0.2,0,0.5,0.75); s=np.zeros(len(t))
    for f in freqs: s+=np.sin(2*np.pi*f*t)+np.sin(2*np.pi*2*f*t)*0.15
    return s/len(freqs)*e

def whoosh(dur,peak=0.85):
    n=int(dur*SR); x=np.arange(n)/n; nz=rng.random(n)*2-1
    hp=np.diff(nz,prepend=nz[0])
    amp=np.where(x<peak,x/peak,np.clip(1-(x-peak)/(1-peak),0,1)**1.5)
    return hp*amp

def impact(dur=1.0,f0=70):
    t=tarr(dur); x=t/dur; f=f0*np.exp(-6*x)+34
    o=np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-4.4*x)
    ck=int(0.03*SR); o[:ck]+=(rng.random(ck)*2-1)*np.exp(-40*np.arange(ck)/ck)*0.6
    return o

def riser(dur,f0=150,f1=1700):
    n=int(dur*SR); x=np.arange(n)/n; amp=x*x; nz=rng.random(n)*2-1
    hp=nz-(1-x)*np.concatenate(([0],nz[:-1]))
    f=f0*np.exp(np.log(f1/f0)*x)
    return (hp*0.5+np.sin(2*np.pi*np.cumsum(f)/SR)*0.4)*amp

def blip(freq=1300,dur=0.09):
    t=tarr(dur); x=t/dur
    return (np.sin(2*np.pi*freq*t)+np.sin(2*np.pi*2*freq*t)*0.4)*np.exp(-22*x)

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

# ---- master: normalize, gentle glue, fades ----
peak=max(np.max(np.abs(L)),np.max(np.abs(R))) or 1.0
g=0.86/peak
def finish(ch):
    x=np.tanh(ch*g*1.25)/1.1
    fi,fo=int(0.1*SR),int(0.8*SR)
    x[:fi]*=np.linspace(0,1,fi); x[-fo:]*=np.linspace(1,0,fo)
    return np.clip(x,-1,1)
Lf=finish(L); Rf=finish(R)
inter=np.empty(N*2); inter[0::2]=Lf; inter[1::2]=Rf
pcm=(inter*32767).astype('<i2')

path=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','dist','track.wav'))
data=pcm.tobytes(); byte=len(data)
with open(path,'wb') as f:
    f.write(b'RIFF'); f.write(struct.pack('<I',36+byte)); f.write(b'WAVE')
    f.write(b'fmt '); f.write(struct.pack('<IHHIIHH',16,1,2,SR,SR*4,4,16))  # 2ch
    f.write(b'data'); f.write(struct.pack('<I',byte)); f.write(data)
print('wrote',path,f'({byte/1e6:.1f} MB, {DUR:.0f}s, stereo)')
