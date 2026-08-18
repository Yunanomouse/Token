#!/usr/bin/env python3
"""Synthesize the trailer soundtrack from scratch (numpy) — no samples, no assets.

Musical grid = 120 BPM (bar = 2.0s) so every video cut lands on a downbeat:

    3000  drop / app slam       (whoosh + big impact)
    7000  open ticker card      (whoosh + impact)
    9000  timeframe pill tick    (UI blip)
   11000  Signals tab           (whoosh + impact)
   15000  AI tab                (whoosh + impact)
   19000  Overview tab          (whoosh + impact)
   23000  outro resolve         (big impact, beat drops out, bright chord)
   27000  end

Run:  python3 render/make_audio.py   ->  dist/track.wav
"""
import os, struct
import numpy as np

SR = 44100
DUR = 27.0
N = int(SR * DUR)
buf = np.zeros(N, dtype=np.float64)
rng = np.random.default_rng(7)

def mix(t, sig, gain=1.0):
    i0 = int(t * SR)
    i1 = min(N, i0 + len(sig))
    if i0 < 0:
        sig = sig[-i0:]; i0 = 0
    if i0 >= N or i1 <= i0:
        return
    buf[i0:i1] += sig[:i1 - i0] * gain

def tarr(dur):
    return np.arange(int(dur * SR)) / SR

def adsr(nn, a, d, s, r, sus=0.6):
    e = np.empty(nn)
    ai, di, ri = int(a*SR), int(d*SR), int(r*SR)
    ai = min(ai, nn);
    idx = np.arange(nn)
    e[:] = sus
    if ai > 0: e[:ai] = np.linspace(0, 1, ai)
    if di > 0:
        j0, j1 = ai, min(nn, ai+di)
        e[j0:j1] = np.linspace(1, sus, j1-j0)
    if ri > 0:
        e[nn-ri:] = np.linspace(sus, 0, ri)
    return e

# ---------- voices ----------
def kick(dur=0.30):
    t = tarr(dur); x = t/dur
    f = 150*np.exp(-16*x) + 48
    ph = np.cumsum(f)/SR
    o = np.sin(2*np.pi*ph) * np.exp(-9*x)
    ck = int(0.004*SR)
    o[:ck] += (rng.random(ck)*2-1)*np.linspace(1,0,ck)*0.5
    return o

def snare(dur=0.18):
    t = tarr(dur); x = t/dur
    nz = rng.random(len(t))*2-1
    body = np.sin(2*np.pi*190*t)*0.5
    return (nz*0.8 + body)*np.exp(-13*x)

def hat(dur=0.03, lvl=1.0):
    n = int(dur*SR); x = np.arange(n)/n
    nz = rng.random(n)*2-1
    hp = np.diff(nz, prepend=nz[0])        # crude high-pass -> "tss"
    return hp*np.exp(-38*x)*lvl

def bass(freq, dur):
    t = tarr(dur); e = adsr(len(t),0.006,0.05,0,0.05,0.85)
    ph = freq*t
    return (np.sin(2*np.pi*ph)*0.7 + np.sin(2*np.pi*2*ph)*0.22 + np.sin(2*np.pi*3*ph)*0.08)*e

def pluck(freq, dur, det=0.006):
    t = tarr(dur); x = t/dur; a = np.exp(-5.5*x)
    s = (np.sin(2*np.pi*freq*t) + np.sin(2*np.pi*freq*(1+det)*t)*0.7
         + np.sin(2*np.pi*freq*(1-det)*t)*0.7 + np.sin(2*np.pi*2*freq*t)*0.3)
    return s*a

def pad(freqs, dur):
    t = tarr(dur); e = adsr(len(t),0.35,0.2,0,0.5,0.75)
    s = np.zeros(len(t))
    for f in freqs:
        s += np.sin(2*np.pi*f*t) + np.sin(2*np.pi*2*f*t)*0.15
    return s/len(freqs)*e

def whoosh(dur, peak=0.85):
    n = int(dur*SR); x = np.arange(n)/n
    nz = rng.random(n)*2-1
    hp = np.diff(nz, prepend=nz[0])
    amp = np.where(x < peak, x/peak, np.clip(1-(x-peak)/(1-peak),0,1)**1.5)
    return hp*amp

def impact(dur=1.1, f0=70):
    t = tarr(dur); x = t/dur
    f = f0*np.exp(-6*x) + 34
    ph = np.cumsum(f)/SR
    o = np.sin(2*np.pi*ph)*np.exp(-4.2*x)
    ck = int(0.03*SR)
    o[:ck] += (rng.random(ck)*2-1)*np.exp(-40*np.arange(ck)/ck)*0.6
    return o

def riser(dur, f0=150, f1=1600):
    n = int(dur*SR); x = np.arange(n)/n; amp = x*x
    nz = rng.random(n)*2-1
    hp = nz - (1-x)*np.concatenate(([0], nz[:-1]))
    f = f0*np.exp(np.log(f1/f0)*x)
    tone = np.sin(2*np.pi*np.cumsum(f)/SR)
    return (hp*0.5 + tone*0.4)*amp

def blip(freq=1300, dur=0.09):
    t = tarr(dur); x = t/dur
    return (np.sin(2*np.pi*freq*t)+np.sin(2*np.pi*2*freq*t)*0.4)*np.exp(-22*x)

# ---------- arrangement ----------
BEAT = 0.5
CH = {'Am':[220.00,261.63,329.63],'F':[174.61,220.00,261.63],
      'C':[261.63,329.63,392.00],'G':[196.00,246.94,293.66],
      'Cmaj':[261.63,329.63,392.00,523.25]}
ROOT = {'Am':55.00,'F':43.65,'C':65.41,'G':49.00}
blocks = [(3.0,'Am'),(7.0,'F'),(11.0,'C'),(15.0,'G'),(19.0,'Am')]

# intro riser + accelerating ticks into the drop
mix(0.15, riser(2.8, 150, 1600), 0.30)
tk, gap = 2.97, 0.34
while tk > 0.45:
    mix(tk, hat(0.035,0.7), 0.5); tk -= gap; gap = max(0.07, gap*0.82)

# four-on-floor kick
t = 3.0
while t < 23.0: mix(t, kick(0.30), 0.95); t += BEAT
# backbeat snare (2 & 4)
t = 3.5
while t < 22.5: mix(t, snare(0.17), 0.42); t += BEAT
# hats: 16th closed + open on the "and"
t = 3.0
while t < 22.75:
    mix(t, hat(0.028,0.55), 0.5)
    mix(t+0.25, hat(0.10,0.8), 0.32)
    t += BEAT
# bass
for st,ch in blocks:
    r = ROOT[ch]; b = st
    while b < st+4.0 and b < 23.0:
        mix(b, bass(r,0.46), 0.9); mix(b+0.25, bass(r*2,0.22), 0.5); b += BEAT
# arpeggio (16ths)
for st,ch in blocks:
    tn = CH[ch]; seq=[tn[0],tn[1],tn[2],tn[1]*2,tn[2],tn[1],tn[0]*2,tn[1]]
    k=0; a=st
    while a < st+4.0 and a < 23.0:
        mix(a, pluck(seq[k%len(seq)],0.24), 0.20); k+=1; a+=0.25
# pad
for st,ch in blocks:
    mix(st, pad(CH[ch], min(4.0,23.0-st)+0.3), 0.20)

# scene-cut accents
for ct in (7.0,11.0,15.0,19.0):
    mix(ct-0.55, whoosh(0.62,0.86), 0.42)
    mix(ct, impact(0.9,64), 0.55)
mix(9.0, blip(1300,0.09), 0.30)             # timeframe pill tick
mix(3.0-0.6, whoosh(0.66,0.9), 0.6)         # the drop
mix(3.0, impact(1.2,78), 0.85)

# outro resolve
mix(22.45, whoosh(0.6,0.92), 0.5)
mix(23.0, impact(1.6,82), 0.95)
mix(23.0, pad(CH['Cmaj'],3.8), 0.34)
sh=[523.25,659.25,783.99,1046.50]
for i,a in enumerate([23.05,23.35,23.7,24.1,24.6]):
    mix(a, pluck(sh[i%4],0.5), 0.16); mix(a+0.28, pluck(sh[i%4],0.4), 0.08)
mix(24.8, impact(1.8,60), 0.4)

# master: normalize, gentle saturation, fades
peak = np.max(np.abs(buf)) or 1.0
x = np.tanh(buf/peak*0.86*1.25)/1.1
fi, fo = int(0.12*SR), int(0.9*SR)
x[:fi] *= np.linspace(0,1,fi)
x[-fo:] *= np.linspace(1,0,fo)
pcm = np.clip(x,-1,1)
pcm = (pcm*32767).astype('<i2')

path = os.path.abspath(os.path.join(os.path.dirname(__file__),'..','dist','track.wav'))
data = pcm.tobytes(); byte = len(data)
with open(path,'wb') as f:
    f.write(b'RIFF'); f.write(struct.pack('<I',36+byte)); f.write(b'WAVE')
    f.write(b'fmt '); f.write(struct.pack('<IHHIIHH',16,1,1,SR,SR*2,2,16))
    f.write(b'data'); f.write(struct.pack('<I',byte)); f.write(data)
print('wrote', path, f'({byte/1e6:.1f} MB, {DUR:.0f}s)')
