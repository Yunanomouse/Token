#!/usr/bin/env python3
"""Menu Designer: build printable and phone menus from a JSON menu file.

Copyright (c) 2026 Matthew Neil Louis Marinier, operating as Brigade Kitchen
Software. All rights reserved. See LICENSE.txt.

Usage:
    python3 build.py                         # menu.json, theme "bistro", out/bistro/
    python3 build.py --theme saloon
    python3 build.py --theme all             # every theme in themes.json
    python3 build.py --menu my-menu.json --theme modern --out out/mine

Only the Python standard library is used.
"""

import argparse
import base64
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def esc(value):
    return html.escape(str(value), quote=True)


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "menu"


def fail(msg):
    sys.stderr.write("build.py: error: %s\n" % msg)
    sys.exit(2)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        fail("%s file not found: %s" % (what, path))
    except json.JSONDecodeError as exc:
        fail("%s file %s is not valid JSON (line %d, column %d): %s"
             % (what, path, exc.lineno, exc.colno, exc.msg))


def format_price(value, settings):
    """14 -> '14', 14.5 -> '14.50', 'MP' -> 'MP', '' / None -> ''."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    currency = settings.get("currency", "")
    decimals = settings.get("decimals", "auto")
    if decimals == "always":
        text = "%.2f" % value
    elif decimals == "never":
        text = "%d" % round(value)
    else:  # auto: whole numbers bare, otherwise two decimals
        text = "%d" % value if float(value).is_integer() else "%.2f" % value
    return currency + text


# Small inline chili for the "spicy" tag (no emoji, no external file).
CHILI_SVG = ('<svg viewBox="0 0 16 16" width="1em" height="1em" aria-hidden="true" focusable="false">'
             '<path fill="currentColor" d="M11.6 1.2c.4-.3 1-.2 1.2.3.2.4 0 .8-.3 1 .9.5 1.5 1.5 1.4 2.6'
             '-.2 3.6-3.2 7.6-8.9 9.4-1.6.5-3.1.3-3.8-.4-.5-.6-.1-1.3.6-1.4 3.3-.6 5.7-2.9 6.6-6.2.3-1.2'
             ' 1.1-2.2 2.2-2.6.3-.9.6-1.9 1-2.7z"/></svg>')


def render_tags(tags, tag_names):
    out = []
    for tag in tags or []:
        label = tag_names.get(tag, tag)
        cls = "badge tag-" + slugify(tag)
        if tag.lower() == "spicy":
            inner = CHILI_SVG
        else:
            inner = esc(tag)
        out.append('<span class="%s" title="%s">%s<span class="sr">%s</span></span>'
                   % (cls, esc(label), inner, esc(label)))
    return "".join(out)


def price_cells(price, settings, ncols):
    """Return the HTML for one or more price cells."""
    if isinstance(price, list):
        cells = [format_price(p, settings) for p in price]
        cells += [""] * (max(ncols, len(cells)) - len(cells))
        return "".join('<span class="price pcol">%s</span>' % esc(c) for c in cells)
    if ncols > 1:  # single price in a multi-column section: put it in the last column
        cells = [""] * (ncols - 1) + [format_price(price, settings)]
        return "".join('<span class="price pcol">%s</span>' % esc(c) for c in cells)
    return '<span class="price">%s</span>' % esc(format_price(price, settings))


# --------------------------------------------------------------------------
# Section rendering (shared by print and phone)
# --------------------------------------------------------------------------

def render_entry(entry, kind, settings, tag_names, ncols):
    name = esc(entry.get("name", ""))
    tags = render_tags(entry.get("tags"), tag_names)
    prices = price_cells(entry.get("price", ""), settings, ncols)
    line = ('<div class="line"><span class="name">%s</span>%s'
            '<span class="leader" aria-hidden="true"></span>%s</div>'
            % (name, (' <span class="tags">%s</span>' % tags) if tags else "", prices))
    desc = entry.get("description")
    desc_html = '<p class="desc">%s</p>' % esc(desc) if desc else ""
    return '<li class="%s">%s%s</li>' % ("item" if kind == "items" else "choice", line, desc_html)


def render_section(sec, settings, tag_names, heading_tag="h2"):
    kind = "items" if sec.get("items") else "choices"
    entries = sec.get(kind) or []
    cols = sec.get("price_columns") or []
    ncols = len(cols)
    classes = ["sec", "sec-" + kind]
    if sec.get("keep_together", True):
        classes.append("keep")
    if sec.get("column_break_before"):
        classes.append("colbreak")
    head = ['<%s class="sec-title">%s</%s>' % (heading_tag, esc(sec.get("title", "")), heading_tag)]
    if sec.get("intro"):
        head.append('<p class="sec-intro">%s</p>' % esc(sec["intro"]))
    if ncols:
        head.append('<div class="price-head" aria-hidden="true"><span class="spacer"></span>%s</div>'
                    % "".join('<span class="pcol">%s</span>' % esc(c) for c in cols))
    rendered = [render_entry(e, kind, settings, tag_names, ncols) for e in entries]
    # The heading is glued to the first entry so it can never sit alone at a column foot.
    first = rendered[0] if rendered else ""
    rest = "".join(rendered[1:])
    note = '<p class="sec-note">%s</p>' % esc(sec["note"]) if sec.get("note") else ""
    return ('<section class="%s" id="sec-%s" aria-labelledby="t-%s">'
            '<div class="head-keep">%s<ul class="entries first">%s</ul></div>'
            '<ul class="entries">%s</ul>%s</section>'
            % (" ".join(classes), esc(sec["id"]), esc(sec["id"]),
               "".join(head).replace('class="sec-title"', 'class="sec-title" id="t-%s"' % esc(sec["id"]), 1),
               first, rest, note))


# --------------------------------------------------------------------------
# Theme and fonts
# --------------------------------------------------------------------------

def font_faces(theme):
    out = []
    for f in theme.get("fonts", []):
        path = os.path.join(HERE, f["file"])
        try:
            with open(path, "rb") as fh:
                data = base64.b64encode(fh.read()).decode("ascii")
        except FileNotFoundError:
            fail("font file not found: %s" % f["file"])
        fmt = "opentype" if path.lower().endswith(".otf") else ("woff2" if path.lower().endswith(".woff2") else "truetype")
        out.append("@font-face{font-family:'%s';src:url(data:font/%s;base64,%s) format('%s');"
                   "font-weight:%s;font-style:%s;font-display:block;}"
                   % (f["family"], "ttf" if fmt == "truetype" else fmt, data, fmt,
                      f.get("weight", "400"), f.get("style", "normal")))
    return "\n".join(out)


def theme_css(theme):
    vars_css = ":root{%s}" % "".join("%s:%s;" % (k, v) for k, v in theme.get("vars", {}).items())
    extra = theme.get("css", "")
    if isinstance(extra, list):
        extra = "\n".join(extra)
    return vars_css + "\n" + extra


BASE_CSS = r"""
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:var(--font-body);font-size:var(--base-size);
  line-height:1.32;-webkit-font-smoothing:antialiased;font-variant-numeric:lining-nums}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
ul.entries{list-style:none;margin:0;padding:0}
h1,h2,h3,p{margin:0}

/* masthead */
.mast{text-align:center}
.mast h1{font-family:var(--font-display);font-size:var(--mast-size);font-weight:var(--mast-weight);
  text-transform:var(--mast-case);letter-spacing:var(--mast-spacing);line-height:1.05;color:var(--ink)}
.tagline{font-style:var(--tagline-style);color:var(--muted);font-size:11pt;margin-top:3pt}
.page-title{font-size:11pt;margin-top:9pt}

/* sections */
.sec-title{font-family:var(--font-display);font-size:var(--sec-size);font-weight:var(--sec-weight);
  font-style:var(--sec-style);text-transform:var(--sec-case);letter-spacing:var(--sec-spacing);
  color:var(--accent);line-height:1.15;margin-bottom:5pt}
.sec-intro{font-style:italic;color:var(--muted);font-size:var(--desc-size);margin:-1pt 0 6pt}
.sec-note{font-size:var(--desc-size);color:var(--muted);font-style:italic;margin-top:5pt;
  padding-top:4pt;border-top:0.5pt solid var(--leader)}
.item{margin-bottom:7pt}
.choice{margin-bottom:2.5pt}
.line{display:flex;align-items:baseline;gap:0}
.name{font-family:var(--name-font);font-size:var(--name-size);font-weight:var(--name-weight);
  text-transform:var(--name-case);letter-spacing:var(--name-spacing);flex:0 1 auto}
.choice .name{font-family:var(--font-body);font-size:10.5pt;font-weight:400;text-transform:none;letter-spacing:0}
.tags{display:inline-flex;gap:2pt;margin-left:5pt;flex:none;align-self:center}
.leader{flex:1 1 auto;min-width:12pt;margin:0 5pt;border-bottom:1.1pt dotted var(--leader);
  position:relative;top:-0.28em}
.price{font-family:var(--price-font);font-weight:var(--price-weight);font-size:var(--name-size);
  font-variant-numeric:tabular-nums lining-nums;white-space:nowrap;flex:none;text-align:right}
.choice .price{font-size:10.5pt}
.pcol{display:inline-block;width:3.1em;text-align:right;flex:none}
.price-head{display:flex;font-size:8.5pt;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em;
  margin:0 0 2pt;font-weight:600}
.price-head .spacer{flex:1}
.desc{font-size:var(--desc-size);font-style:var(--desc-style);color:var(--muted);margin-top:1pt;
  padding-right:2.8em;line-height:1.3}
.badge{display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-body);
  font-style:normal;font-size:6.8pt;font-weight:700;line-height:1;letter-spacing:0.02em;
  min-width:13pt;height:11pt;padding:0 2.5pt;border-radius:2pt;border:0.7pt solid var(--badge-border);
  background:var(--badge-bg);color:var(--badge-ink);text-transform:uppercase}
.badge.tag-spicy{color:var(--accent);border-color:transparent;background:transparent;min-width:0;padding:0;font-size:9pt}
.badge.tag-new{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}

/* footer */
.foot{text-align:center;font-size:9pt;color:var(--muted);line-height:1.4}
.legend{display:flex;justify-content:center;flex-wrap:wrap;gap:3pt 12pt;margin-bottom:5pt;font-size:8.5pt}
.legend span{display:inline-flex;align-items:center;gap:3pt}
.info{color:var(--ink);font-size:9.5pt}
.info .dot{color:var(--accent);padding:0 6pt}
.footnote{font-style:italic;margin-top:2pt;font-size:8.5pt}
"""

PRINT_CSS = r"""
@page{size:8.5in 11in;margin:0}
html,body{background:#777}
@media print{html,body{background:var(--paper)}}
.page{width:8.5in;height:11in;margin:0 auto;padding:0.55in 0.62in 0.48in;display:flex;flex-direction:column;
  background:var(--paper);position:relative;overflow:hidden;break-after:page;page-break-after:always}
@media screen{.page{margin:0.25in auto}}
.page:last-child{break-after:auto;page-break-after:auto}
.page.compact .mast h1{font-size:calc(var(--mast-size) * 0.72)}
.page.compact .tagline{display:none}
.page-body{flex:1 1 auto;min-height:0;margin:18pt 0 12pt;column-count:2;column-gap:0.42in;column-fill:balance;
  overflow:hidden}
.page[data-fill="auto"] .page-body{column-fill:auto}
.sec{margin-bottom:16pt;break-inside:auto}
.sec.keep{break-inside:avoid;page-break-inside:avoid}
.sec.colbreak{break-before:column}
.head-keep,.item,.choice{break-inside:avoid;page-break-inside:avoid}
.page-body > .sec:last-child{margin-bottom:0}
.foot{flex:none;padding-top:9pt;border-top:0.6pt solid var(--rule)}
"""

PHONE_CSS = r"""
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{font-size:16px;overflow-x:hidden}
.phone{max-width:720px;margin:0 auto}
.phone .mast{padding:28px 20px 18px}
.phone .mast h1{font-size:clamp(30px,9vw,46px);overflow-wrap:anywhere}
.phone .tagline{font-size:16px}
.phone .page-title{font-size:15px}
.tabs{position:sticky;top:0;z-index:5;background:var(--paper);border-bottom:1px solid var(--leader)}
.tabs ul{display:flex;gap:4px;overflow-x:auto;list-style:none;margin:0;padding:8px 12px;scrollbar-width:none;
  scroll-snap-type:x proximity}
.tabs ul::-webkit-scrollbar{display:none}
.tabs a{display:block;white-space:nowrap;padding:8px 12px;border-radius:999px;color:var(--ink);text-decoration:none;
  font-size:15px;font-weight:600;scroll-snap-align:start;border:1px solid transparent}
.tabs a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tabs a[aria-current="true"]{background:var(--accent);color:var(--accent-ink)}
.phone main{padding:8px 18px 8px}
.phone .sec{padding-top:22px;scroll-margin-top:64px}
.phone .sec-title{font-size:calc(var(--sec-size) * 1.45)}
.phone .name{font-size:17px;overflow-wrap:anywhere}
.phone .choice .name{font-size:16px}
.phone .price,.phone .choice .price{font-size:17px}
.phone .desc,.phone .sec-intro,.phone .sec-note{font-size:15px}
.phone .desc{padding-right:0}
.phone .item{margin-bottom:14px}
.phone .choice{margin-bottom:8px}
.phone .badge{font-size:10px;height:16px;min-width:20px;border-radius:3px;padding:0 4px}
.phone .badge.tag-spicy{font-size:14px}
.phone .price-head{font-size:12px}
.phone .foot{padding:26px 20px 36px;font-size:14px;border-top:1px solid var(--rule);margin-top:24px}
.phone .info{font-size:15px}
.phone .info a{color:inherit}
.phone .info .dot{display:none}
.phone .info span{display:block}
.phone .legend{font-size:13px}
.phone .footnote{font-size:13px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""

PHONE_JS = r"""
(function(){
  var links=[].slice.call(document.querySelectorAll('.tabs a'));
  var map={};links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a;});
  function setActive(id){links.forEach(function(a){a.removeAttribute('aria-current');});
    var a=map[id];if(!a)return;a.setAttribute('aria-current','true');
    var ul=a.parentNode.parentNode;var x=a.offsetLeft-ul.clientWidth/2+a.clientWidth/2;
    ul.scrollTo({left:x,behavior:'smooth'});}
  if(!('IntersectionObserver' in window)){return;}
  var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting)setActive(e.target.id);});},
    {rootMargin:'-70px 0px -65% 0px'});
  Object.keys(map).forEach(function(id){var el=document.getElementById(id);if(el)io.observe(el);});
})();
"""


# --------------------------------------------------------------------------
# Page builders
# --------------------------------------------------------------------------

def masthead(info, page_title, tag="h1"):
    parts = ['<header class="mast"><div class="mast-ornament" aria-hidden="true"></div>',
             '<%s>%s</%s>' % (tag, esc(info.get("name", "")), tag)]
    if info.get("tagline"):
        parts.append('<p class="tagline">%s</p>' % esc(info["tagline"]))
    if page_title:
        parts.append('<p class="page-title">%s</p>' % esc(page_title))
    parts.append("</header>")
    return "".join(parts)


def used_tags(sections):
    seen = []
    for sec in sections:
        for e in (sec.get("items") or []) + (sec.get("choices") or []):
            for t in e.get("tags") or []:
                if t not in seen:
                    seen.append(t)
    return seen


def footer(info, tags_on_page, tag_names, phone=False):
    legend = ""
    if tags_on_page:
        legend = '<div class="legend">%s</div>' % "".join(
            '<span>%s %s</span>' % (render_tags([t], tag_names), esc(tag_names.get(t, t)))
            for t in tags_on_page)
    bits = []
    if info.get("address"):
        bits.append(esc(info["address"]))
    if info.get("phone"):
        tel = re.sub(r"[^0-9+]", "", info["phone"])
        bits.append('<a href="tel:%s">%s</a>' % (tel, esc(info["phone"])) if phone else esc(info["phone"]))
    if info.get("website"):
        site = info["website"]
        href = site if site.startswith("http") else "https://" + site
        bits.append('<a href="%s">%s</a>' % (esc(href), esc(site)) if phone else esc(site))
    hours = info.get("hours")
    if isinstance(hours, list):
        hours = "  ·  ".join(hours)
    sep = '<span class="dot" aria-hidden="true">·</span>'
    info_line = '<p class="info">%s</p>' % sep.join("<span>%s</span>" % b for b in bits) if bits else ""
    hours_line = '<p class="hours">%s</p>' % esc(hours) if hours else ""
    note = '<p class="footnote">%s</p>' % esc(info["footer_note"]) if info.get("footer_note") else ""
    return '<footer class="foot">%s%s%s%s</footer>' % (legend, info_line, hours_line, note)


def document(title, lang, css, body, scheme, extra_head="", script=""):
    return ("<!DOCTYPE html>\n<html lang=\"%s\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"color-scheme\" content=\"%s\">\n%s<title>%s</title>\n<style>\n%s\n</style>\n</head>\n"
            "<body>\n%s\n%s</body>\n</html>\n"
            % (esc(lang), scheme, extra_head, esc(title), css, body,
               ("<script>%s</script>\n" % script) if script else ""))


def build_print(menu, theme, theme_name):
    info = menu.get("restaurant", {})
    settings = menu.get("settings", {})
    tag_names = menu.get("tags", {})
    by_id = {s["id"]: s for s in menu["sections"]}
    pages = menu.get("pages") or [{"title": "", "sections": [s["id"] for s in menu["sections"]]}]
    out = []
    for i, page in enumerate(pages):
        secs = []
        for sid in page.get("sections", []):
            if sid not in by_id:
                fail("page %d lists unknown section id %r" % (i + 1, sid))
            secs.append(by_id[sid])
        header_style = page.get("header", "full" if i == 0 else "compact")
        cls = "page" + (" compact" if header_style == "compact" else "")
        fill = ' data-fill="auto"' if page.get("column_fill") == "auto" else ""
        body = "".join(render_section(s, settings, tag_names, "h2") for s in secs)
        out.append('<article class="%s" data-page="%d"%s>%s<div class="page-body">%s</div>%s</article>'
                   % (cls, i + 1, fill, masthead(info, page.get("title"), "h1" if i == 0 else "p"),
                      body, footer(info, used_tags(secs), tag_names)))
    css = font_faces(theme) + BASE_CSS + PRINT_CSS + theme_css(theme)
    head = '<meta name="menu-theme" content="%s">\n<meta name="menu-kind" content="print">\n' % esc(theme_name)
    return document("%s – Menu" % info.get("name", "Menu"), settings.get("language", "en"),
                    css, "\n".join(out), theme.get("scheme", "light"), head)


def build_phone(menu, theme, theme_name):
    info = menu.get("restaurant", {})
    settings = menu.get("settings", {})
    tag_names = menu.get("tags", {})
    by_id = {s["id"]: s for s in menu["sections"]}
    order = []
    for page in menu.get("pages") or []:
        for sid in page.get("sections", []):
            if sid in by_id and sid not in order:
                order.append(sid)
    for s in menu["sections"]:  # sections not placed on any page still appear online
        if s["id"] not in order and not s.get("print_only"):
            order.append(s["id"])
    secs = [by_id[sid] for sid in order]
    tabs = "".join('<li><a href="#sec-%s">%s</a></li>' % (esc(s["id"]), esc(s.get("title", "")))
                   for s in secs)
    body = ('<div class="phone">%s<nav class="tabs" aria-label="Menu sections"><ul>%s</ul></nav>'
            '<main id="menu">%s</main>%s</div>'
            % (masthead(info, None), tabs,
               "".join(render_section(s, settings, tag_names, "h2") for s in secs),
               footer(info, used_tags(secs), tag_names, phone=True)))
    css = font_faces(theme) + BASE_CSS + PHONE_CSS + theme_css(theme)
    head = ('<meta name="menu-theme" content="%s">\n<meta name="menu-kind" content="phone">\n'
            '<meta name="theme-color" content="%s">\n'
            % (esc(theme_name), esc(theme.get("vars", {}).get("--paper", "#ffffff"))))
    return document(info.get("name", "Menu"), settings.get("language", "en"), css, body,
                    theme.get("scheme", "light"), head, PHONE_JS)


def validate(menu):
    if not isinstance(menu.get("sections"), list) or not menu["sections"]:
        fail("menu needs a non-empty \"sections\" list")
    ids = set()
    for n, s in enumerate(menu["sections"], 1):
        if "id" not in s:
            s["id"] = slugify(s.get("title", "section-%d" % n))
        if s["id"] in ids:
            fail("duplicate section id %r" % s["id"])
        ids.add(s["id"])
        if not s.get("items") and not s.get("choices"):
            fail("section %r has neither \"items\" nor \"choices\"" % s["id"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build print and phone menus from a JSON menu.")
    ap.add_argument("--menu", default=os.path.join(HERE, "menu.json"), help="menu JSON file (default: menu.json)")
    ap.add_argument("--theme", default="bistro", help="theme name from themes.json, or 'all' (default: bistro)")
    ap.add_argument("--themes", default=os.path.join(HERE, "themes.json"), help="themes file (default: themes.json)")
    ap.add_argument("--out", default=None, help="output folder (default: out/<theme>)")
    args = ap.parse_args(argv)

    menu = load_json(args.menu, "menu")
    themes = load_json(args.themes, "themes")
    validate(menu)
    names = list(themes) if args.theme == "all" else [args.theme]
    for name in names:
        if name not in themes:
            fail("unknown theme %r; available: %s" % (name, ", ".join(themes)))
    slug = slugify(menu.get("restaurant", {}).get("name", "menu"))
    for name in names:
        out_dir = args.out if (args.out and len(names) == 1) else os.path.join(args.out or os.path.join(HERE, "out"), name)
        os.makedirs(out_dir, exist_ok=True)
        for kind, builder in (("print", build_print), ("phone", build_phone)):
            path = os.path.join(out_dir, "%s-%s.html" % (slug, kind))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(builder(menu, themes[name], name))
            print("wrote %s" % os.path.relpath(path))


if __name__ == "__main__":
    main()
