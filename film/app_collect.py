#!/usr/bin/env python3
"""Run Venture Trader's own collectors once and build its dashboard.

Usage:  <app-venv>/bin/python film/app_collect.py /path/to/copy-of-openbb-trader [step ...]

Point this at a COPY of the app (e.g. `git archive HEAD | tar -x -C copy/`): the
app writes data/, signals/, logs/ and reports/ next to its code.

Only data collection, the signal engine and the page generator run. Nothing that
sends alerts or touches a brokerage is imported. Feeds that need the owner's keys
(LSE, FRED, a local AI model) are skipped by the app itself and their panels stay
empty; the film does not open those tabs.
"""
import os, sys, time

if len(sys.argv) < 2:
    sys.exit(__doc__)
APP = os.path.abspath(sys.argv[1]); only = set(sys.argv[2:])
os.chdir(APP); sys.path.insert(0, APP)
import logging; logging.basicConfig(level=logging.WARNING)

def step(key, name, mod, fn):
    if only and key not in only: return
    t = time.time()
    try:
        r = getattr(__import__(mod), fn)()
        n = len(r) if hasattr(r, '__len__') else r
        print(f'OK   {name:16s} {time.time()-t:6.1f}s  {str(n)[:40]}', flush=True)
    except BaseException as e:                       # one dead feed must not stop the rest
        print(f'SKIP {name:16s} {time.time()-t:6.1f}s  {type(e).__name__}: {str(e)[:120]}', flush=True)

for args in [
    ('quotes',   'quotes',         'collector',    'collect_quotes'),
    ('crypto',   'crypto',         'collector',    'collect_crypto'),
    ('crypto',   'crypto history', 'collector',    'collect_crypto_history'),
    ('movers',   'movers',         'collector',    'collect_movers'),
    ('news',     'news',           'collector',    'collect_news'),
    ('shorts',   'short interest', 'collector',    'collect_short_interest'),
    ('macro',    'macro',          'collector',    'collect_macro'),
    ('sectors',  'sectors',        'collector',    'collect_sectors'),
    ('earnings', 'earnings',       'collector',    'collect_earnings'),
    ('history',  'history',        'collector',    'collect_history'),
    ('fund',     'fundamentals',   'fundamentals', 'collect_fundamentals'),
    ('insider',  'insider clusters','openinsider', 'collect_cluster_buys'),
    ('buzz',     'reddit buzz',    'sentiment',    'collect_social_buzz'),
    ('flip',     'discover',       'flipboard',    'collect_flipboard'),
    ('cnews',    'crypto news',    'crypto_news',  'collect_crypto_news'),
    ('signals',  'signals',        'signals',      'generate_signals'),
    ('perf',     'scorecard',      'performance',  'run_tracker'),
    ('dash',     'dashboard',      'dashboard',    'generate_dashboard'),
]:
    step(*args)
