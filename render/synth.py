"""Tiny numpy synth shared by the soundtrack scripts — no samples, no assets.

    from synth import *
    start(24.0)                       # allocate a stereo buffer of that length
    mix(t, kick(), gain, pan)         # place voices on the timeline (pan: -1 L .. +1 R)
    write(path)                       # normalize, glue, fade, write a 16-bit stereo WAV
"""
import math, os, struct, sys
import numpy as np

SR = 44100
rng = np.random.default_rng(7)
_buf = {}

def start(dur):
    n = int(SR * dur)
    _buf.update(N=n, L=np.zeros(n), R=np.zeros(n), dur=dur)

def mix(t, sig, gain=1.0, pan=0.0):
    """Mix mono sig at time t with equal-power pan (-1 L .. +1 R)."""
    N, L, R = _buf['N'], _buf['L'], _buf['R']
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

def write(path=None, fade_in=0.1, fade_out=0.8):
    """Master (normalize, gentle tanh glue, fades) and write a stereo WAV."""
    N, L, R = _buf['N'], _buf['L'], _buf['R']
    peak = max(np.max(np.abs(L)), np.max(np.abs(R))) or 1.0
    g = 0.86/peak
    def finish(ch):
        x = np.tanh(ch*g*1.25)/1.1
        fi, fo = int(fade_in*SR), int(fade_out*SR)
        x[:fi] *= np.linspace(0,1,fi); x[-fo:] *= np.linspace(1,0,fo)
        return np.clip(x,-1,1)
    inter = np.empty(N*2); inter[0::2] = finish(L); inter[1::2] = finish(R)
    pcm = (inter*32767).astype('<i2')
    if path is None:
        path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'dist', 'track.wav')
    path = os.path.abspath(path)
    data = pcm.tobytes(); byte = len(data)
    with open(path,'wb') as f:
        f.write(b'RIFF'); f.write(struct.pack('<I',36+byte)); f.write(b'WAVE')
        f.write(b'fmt '); f.write(struct.pack('<IHHIIHH',16,1,2,SR,SR*4,4,16))  # 2ch
        f.write(b'data'); f.write(struct.pack('<I',byte)); f.write(data)
    print('wrote', path, f"({byte/1e6:.1f} MB, {_buf['dur']:.0f}s, stereo)")
