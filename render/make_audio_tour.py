#!/usr/bin/env python3
"""Soundtrack for the 2-minute Venture Trader tour (src/venture-2min.html).

128 BPM, 64 bars = 120 s. Sections follow the film so the music changes when
the picture does (bar numbers; 1 bar = 1.875 s):

     0- 4  hook        soft hits under the three opening lines, riser into the drop
     4-16  overview    drop: kick, hats, bass, pad, light arp
    16-28  stock card  adds snare + fuller arp
    28-40  signals     adds a lead line
    40-44  AI take     breakdown: drums out, pad + arp, riser back in
    44-53  analysts    full band again, snare roll into the last scene
    53-58  auto-refresh
    58-64  outro       big resolve on C major, shimmer, tail

Run:  python3 render/make_audio_tour.py [out.wav]   (default dist/track.wav)
"""
from synth import *

BEAT = 60/128; H = BEAT/2; BAR = 4*BEAT
bar = lambda n: n*BAR
start(bar(64))

CH = {'Am':[220.00,261.63,329.63], 'F':[174.61,220.00,261.63],
      'C':[261.63,329.63,392.00],  'G':[196.00,246.94,293.66],
      'Cmaj':[261.63,329.63,392.00,523.25], 'Fmaj':[174.61,220.00,261.63,349.23]}
ROOT = {'Am':55.00, 'F':43.65, 'C':65.41, 'G':49.00}
PROG = ['Am','F','C','G']                       # one chord per 2 bars, from bar 4
chord = lambda b: PROG[((b-4)//2) % 4]

def sweep(t, dur=0.56, gain=0.30):              # stereo whoosh that peaks at t
    mix(t-dur+0.06, whoosh(dur,0.88), gain, -0.8)
    mix(t-dur+0.06, whoosh(dur,0.88), gain,  0.8)

# ---- hook (bars 0-4): a soft hit under each line, logo hit, riser into the drop ----
for i in range(3):
    mix(bar(i)+0.06, impact(1.5,58), 0.42)
    mix(bar(i)+0.06, pad(CH['Am'] if i<2 else CH['F'], BAR+0.2), 0.16)
mix(bar(3)+0.06, impact(1.3,74), 0.55)
mix(bar(3)+0.06, pad(CH['Cmaj'], BAR), 0.26)
mix(bar(2), riser(2*BAR-0.1,150,1700), 0.26)
tk, gap, pan = bar(4)-0.03, 0.30, -0.5
while tk > bar(3)+0.2:
    mix(tk, hat(0.033,0.7), 0.45, pan); tk -= gap; gap = max(0.065, gap*0.82); pan = -pan

# ---- main body (bars 4-58) ----
n_hat = 0
for b in range(4, 58):
    t0 = bar(b); ch = chord(b); half = (b-4) % 2          # 0 = first bar of the chord
    drums = not (40 <= b < 44)                            # breakdown under the AI take
    snares = b >= 16
    arp_g = 0.11 if b < 16 else (0.18 if drums else 0.26)
    lead = (28 <= b < 40) or (44 <= b < 58)

    if drums:
        for k in range(4):
            t = t0 + k*BEAT
            mix(t, kick(), 0.95)
            mix(t, hat(0.026,0.5), 0.44, -0.35 if n_hat % 2 else 0.35)
            mix(t+H, hat(0.09,0.75), 0.30 if snares else 0.22, 0.55 if n_hat % 2 else -0.55)
            mix(t, bass(ROOT[ch],0.44), 0.9); mix(t+H, bass(ROOT[ch]*2,0.20), 0.5)
            n_hat += 1
        if snares and b != 52:
            mix(t0+BEAT, snare(), 0.42); mix(t0+3*BEAT, snare(), 0.42)
    elif b >= 42:                                         # hats creep back in before the drop
        for k in range(8):
            mix(t0+k*H, hat(0.026,0.5), 0.14+0.02*k*(b-41), -0.4 if k % 2 else 0.4)

    tn = CH[ch]; seq = [tn[0],tn[1],tn[2],tn[1]*2,tn[2],tn[1],tn[0]*2,tn[1]]
    for k in range(8):                                    # 16th-note arpeggio
        mix(t0+k*H, pluck(seq[(half*8+k) % 8],0.22), arp_g, -0.5 if k % 2 else 0.5)
    if half == 0:
        mix(t0, pad(tn, 2*BAR+0.3), 0.20 if drums else 0.44)
    if lead and drums:                                    # two long notes a bar, an octave up
        mix(t0,        pluck(tn[2]*2, 0.85, 0.004), 0.10, -0.2)
        mix(t0+2*BEAT, pluck(tn[(1+half) % 3]*2, 0.85, 0.004), 0.09, 0.2)

# breakdown riser + build into the last scene
mix(bar(42), riser(2*BAR-0.05,160,1800), 0.30)
for i in range(8):  mix(bar(52)+i*H, snare(0.12), 0.16+0.03*i)             # snare roll: 8ths...
for i in range(8):  mix(bar(52)+2*BEAT+i*H/2, snare(0.09), 0.26+0.025*i)   # ...then 16ths
mix(bar(51), riser(2*BAR-0.05,170,1900), 0.24)

# ---- accents on the picture ----
mix(bar(4), impact(1.1,80), 0.85); sweep(bar(4), 0.6, 0.42)               # the drop / app slams in
for b in (16, 28, 40, 44, 53):                                            # scene changes
    sweep(bar(b)); mix(bar(b), impact(0.9,66), 0.58)
for b in (6, 8, 12, 21, 23, 25, 30, 33, 36, 46, 48, 50):                  # camera moves inside a scene
    sweep(bar(b), 0.5, 0.13)
for b, f in ((18,1200), (19,1350), (20,1500)):                            # timeframe pill clicks
    mix(bar(b), blip(f,0.09), 0.30, 0.4)

# ---- outro (bars 58-64) ----
sweep(bar(58), 0.6, 0.36); mix(bar(58), impact(1.7,84), 0.95)
mix(bar(58), pad(CH['Cmaj'], 2*BAR+0.3), 0.34)
mix(bar(60), pad(CH['Fmaj'], 2*BAR+0.3), 0.30)
mix(bar(62), pad(CH['Cmaj'], 2*BAR), 0.30)
for b in (58, 59, 60, 61, 62):                                            # slow heartbeat
    mix(bar(b), kick(0.34), 0.5 - 0.06*(b-58))
shimmer = [523.25,659.25,783.99,1046.50,783.99,659.25]
for i in range(18):                                                       # sparse falling shimmer
    t = bar(58) + 0.3 + i*BEAT*1.0
    mix(t, pluck(shimmer[i % 6], 0.6), 0.15*(1 - i/22), -0.5 if i % 2 else 0.5)
mix(bar(62), impact(2.0,56), 0.38)

write(fade_out=2.2)
