  // ---------- tool: menu engineering (Kasavana & Smith matrix) ----------
  (function () {
    var CLASSES = {
      star: { name: "Star", act: "Keep and feature", cls: "me-star" },
      plow: { name: "Plowhorse", act: "Raise price slightly or trim plate cost", cls: "me-plow" },
      puzzle: { name: "Puzzle", act: "Promote or reposition on the menu", cls: "me-puzzle" },
      dog: { name: "Dog", act: "Rework or remove", cls: "me-dog" }
    };
    var ORDER = ["star", "plow", "puzzle", "dog"];
    var st = null, pend = false, confirmClear = false, refs = null;

    document.head.appendChild(el("style", { text: [
      "#view-menueng .me-stack { display: grid; gap: 10px; }",
      "#view-menueng .me-period { width: 180px; }",
      "#view-menueng td input[type=number] { width: 80px; }",
      "#view-menueng td.me-name { min-width: 160px; }",
      "#view-menueng .chip.me-star { border-color: var(--ok); color: var(--ok); font-weight: 600; }",
      "#view-menueng .chip.me-plow { border-color: var(--warn); color: var(--warn); font-weight: 600; }",
      "#view-menueng .chip.me-puzzle { border-color: var(--accent); color: var(--accent); font-weight: 600; }",
      "#view-menueng .chip.me-dog { border-color: var(--bad); color: var(--bad); font-weight: 600; }",
      "#view-menueng td.me-act { color: var(--muted); font-size: 12px; min-width: 190px; }",
      "#view-menueng tfoot td { background: var(--head); font-weight: 600; }",
      "#view-menueng .me-grid { display: grid; grid-template-columns: auto 1fr 1fr; border: 1px solid var(--line); background: var(--surface); }",
      "#view-menueng .me-grid > div { border-right: 1px solid var(--grid); border-bottom: 1px solid var(--grid); padding: 8px 10px; min-width: 0; }",
      "#view-menueng .me-axis { background: var(--head); font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .03em; font-weight: 600; display: flex; align-items: center; justify-content: center; text-align: center; }",
      "#view-menueng .me-cell { min-height: 92px; border-top: 3px solid transparent; }",
      "#view-menueng .me-cell.me-star { border-top-color: var(--ok); }",
      "#view-menueng .me-cell.me-plow { border-top-color: var(--warn); }",
      "#view-menueng .me-cell.me-puzzle { border-top-color: var(--accent); }",
      "#view-menueng .me-cell.me-dog { border-top-color: var(--bad); }",
      "#view-menueng .me-cell h3 { display: flex; justify-content: space-between; gap: 8px; }",
      "#view-menueng .me-cell ul { margin: 6px 0 0; padding-left: 18px; }",
      "#view-menueng .me-cell .hint { margin-top: 2px; }",
      "@media (max-width: 700px) { #view-menueng .me-grid { grid-template-columns: 1fr 1fr; } #view-menueng .me-grid .me-axis { display: none; } }"
    ].join("\n") }));

    function load() {
      if (pend && st) { S.settings.menuEng = st; return; }
      var m = S.settings.menuEng && typeof S.settings.menuEng === "object" ? S.settings.menuEng : {};
      st = { period: String(m.period || ""), sold: Object.assign({}, m.sold && typeof m.sold === "object" ? m.sold : {}) };
      S.settings.menuEng = st;
    }
    function save() {
      pend = true;
      saveSoon("menueng", function () {
        pend = false;
        write("settings/main", { menuEng: JSON.parse(JSON.stringify(st)) }, true).catch(function () {});
      });
    }
    function units(id) { var u = num(st.sold[id], 0); return u > 0 ? u : 0; }

    // every number the sheet shows, from the current units
    function compute() {
      var rows = itemList().filter(function (it) { return !isPrep(it); }).map(function (it) {
        var c = itemCalc(it), price = num(it.price), cost = isFinite(c.cost) ? c.cost : 0, u = units(it.id);
        return { it: it, price: price, cost: cost, bad: c.bad, margin: price - cost, u: u, sales: u * price, food: u * cost, tm: u * (price - cost) };
      });
      var n = rows.length, tu = 0, ts = 0, tf = 0, tm = 0;
      rows.forEach(function (r) { tu += r.u; ts += r.sales; tf += r.food; tm += r.tm; });
      var popCut = n ? 0.7 * tu / n : NaN, avgM = tu > 0 ? tm / tu : NaN, any = tu > 0, counts = { star: 0, plow: 0, puzzle: 0, dog: 0 };
      rows.forEach(function (r) {
        r.share = any ? r.u / tu * 100 : NaN;
        if (!any) { r.pop = r.prof = r.k = null; return; }
        r.pop = r.u >= popCut; r.prof = r.margin >= avgM;
        r.k = r.pop ? (r.prof ? "star" : "plow") : (r.prof ? "puzzle" : "dog");
        counts[r.k]++;
      });
      return { rows: rows, n: n, tu: tu, ts: ts, tf: tf, tm: tm, popCut: popCut, avgM: avgM, has: any, counts: counts, fc: ts > 0 ? tf / ts * 100 : NaN };
    }
    function hl(b) { return b == null ? "–" : b ? "High" : "Low"; }
    function chip(k) { return k ? el("span", { class: "chip " + CLASSES[k].cls, text: CLASSES[k].name }) : el("span", { class: "muted", text: "–" }); }

    function tilesOf(R) {
      return [
        tile("Units sold", trimN(R.tu, 0), st.period ? st.period : "this period"),
        tile("Sales", money(R.ts), R.n + " dishes"),
        tile("Food cost", R.ts > 0 ? pct(R.fc) : "–", "target " + target() + "%", R.ts > 0 ? (R.fc <= target() ? "good" : "over") : ""),
        tile("Avg margin", R.has ? money(R.avgM) : "–", R.has ? "per dish sold, weighted" : "enter units sold"),
        tile("Popular if", R.has ? "≥ " + trimN(R.popCut, 1) : "–", "units (70% of average)")
      ].concat(ORDER.map(function (k) { return tile(CLASSES[k].name + "s", R.has ? String(R.counts[k]) : "–", CLASSES[k].act); }));
    }
    function gridOf(R) {
      function cell(k) {
        var names = R.rows.filter(function (r) { return r.k === k; }).map(function (r) { return r.it.name || "Unnamed"; });
        return el("div", { class: "me-cell " + CLASSES[k].cls }, [
          el("h3", null, [chip(k), el("span", { class: "muted", text: String(names.length) })]),
          el("p", { class: "hint", text: CLASSES[k].act }),
          names.length ? el("ul", null, names.map(function (x) { return el("li", { text: x }); })) : el("p", { class: "hint", text: "None" })
        ]);
      }
      return el("div", { class: "me-grid", role: "group", "aria-label": "Menu engineering matrix" }, [
        el("div", { class: "me-axis" }), el("div", { class: "me-axis", text: "High popularity" }), el("div", { class: "me-axis", text: "Low popularity" }),
        el("div", { class: "me-axis", text: "High margin" }), cell("star"), cell("puzzle"),
        el("div", { class: "me-axis", text: "Low margin" }), cell("plow"), cell("dog")
      ]);
    }

    // update the computed cells, tiles and matrix in place (keeps focus in the units column)
    function refresh() {
      if (!refs) return;
      var R = compute();
      R.rows.forEach(function (r) {
        var c = refs.cells[r.it.id]; if (!c) return;
        c.sales.textContent = money(r.sales); c.tm.textContent = money(r.tm);
        c.pop.textContent = hl(r.pop); c.prof.textContent = hl(r.prof);
        c.k.replaceChildren(chip(r.k)); c.act.textContent = r.k ? CLASSES[r.k].act : "";
        c.share.textContent = r.u > 0 && R.has ? trimN(r.share, 1) + "% of units" : "";
      });
      refs.foot.u.textContent = trimN(R.tu, 0); refs.foot.s.textContent = money(R.ts); refs.foot.m.textContent = money(R.tm);
      refs.tiles.replaceChildren.apply(refs.tiles, tilesOf(R));
      refs.grid.replaceChildren(gridOf(R));
      refs.hint.hidden = R.has;
      refs.h3.textContent = "Menu matrix" + (st.period ? " · " + st.period : "");
    }

    function build(container) {
      var R = compute(), cells = {}, inputs = [];
      var period = el("input", { type: "text", class: "me-period", value: st.period, placeholder: "e.g. Oct 1–28", "aria-label": "Sales period", oninput: function () { st.period = period.value; save(); refresh(); } });
      var clear = el("button", { class: "btn danger", type: "button", text: confirmClear ? "Tap again to clear" : "Clear units", onclick: function () {
        if (!confirmClear) { confirmClear = true; clear.textContent = "Tap again to clear"; return; }
        confirmClear = false; st.sold = {}; save(); build(container); toast("Units cleared");
      } });
      var body = [], last = null;
      R.rows.forEach(function (r) {
        var id = r.it.id;
        if (r.it.section !== last) { last = r.it.section; body.push(el("tr", { class: "cat" }, [el("td", { colspan: "11", text: r.it.section || "Other" })])); }
        var c = { sales: el("td", { class: "n" }), tm: el("td", { class: "n" }), pop: el("td"), prof: el("td"), k: el("td"), act: el("td", { class: "me-act" }), share: el("div", { class: "muted small" }) };
        cells[id] = c;
        var inp = el("input", { type: "number", min: "0", step: "1", inputmode: "numeric", value: st.sold[id] != null && st.sold[id] !== "" ? st.sold[id] : "", placeholder: "0", "aria-label": "Units sold: " + (r.it.name || "Unnamed"),
          oninput: function () { var v = inp.value.trim(); if (v === "") delete st.sold[id]; else st.sold[id] = Math.max(0, num(v)); save(); refresh(); },
          onkeydown: function (e) { if (e.key === "Enter") { e.preventDefault(); var nx = inputs[inputs.indexOf(inp) + 1]; if (nx) { nx.focus(); nx.select(); } else inp.blur(); } } });
        inputs.push(inp);
        body.push(el("tr", null, [
          el("td", { class: "me-name", text: r.it.name || "Unnamed" }),
          el("td", { class: "n", text: money(r.price) }),
          el("td", { class: "n", title: r.bad ? r.bad + " line(s) can't be costed yet" : null }, [money(r.cost), r.bad ? el("span", { class: "chip warn", text: "!", style: "margin-left:4px" }) : null]),
          el("td", { class: "n " + (r.margin < 0 ? "over" : ""), text: money(r.margin) }),
          el("td", { class: "n" }, [inp, c.share]),
          c.sales, c.tm, c.pop, c.prof, c.k, c.act
        ]));
      });
      var foot = { u: el("td", { class: "n" }), s: el("td", { class: "n" }), m: el("td", { class: "n" }) };
      var heads = ["Dish", "Price", "Plate cost", "Margin", "Units sold", "Sales", "Total margin", "Popularity", "Profit", "Class", "Action"];
      var table = R.n ? el("div", { class: "tablewrap" }, [el("table", null, [
        el("thead", null, [el("tr", null, heads.map(function (h, k) { return el("th", { scope: "col", class: k && k < 7 ? "n" : "", text: h }); }))]),
        el("tbody", null, body),
        el("tfoot", null, [el("tr", null, [el("td", { text: "Total" }), el("td"), el("td"), el("td"), foot.u, foot.s, foot.m, el("td", { colspan: "4" })])])
      ])]) : el("div", { class: "tablewrap" }, [el("div", { class: "empty", text: S.loaded.items ? "No menu items yet. Add dishes on Menu costing first." : "Loading…" })]);
      var hint = el("div", { class: "notice", text: "Type how many of each dish you sold in the period (from your till or POS report). Leave a dish blank if it didn't sell. The matrix fills in as you go." });
      refs = { cells: cells, foot: foot, tiles: el("div", { class: "tiles" }), grid: el("div"), hint: hint, h3: el("h3") };
      container.replaceChildren(
        el("div", { class: "cmdbar" }, [
          el("label", { class: "row muted" }, ["Sales period ", period]),
          el("span", { class: "sep" }), clear,
          el("span", { class: "grow" }),
          el("span", { class: "hint", text: "Popular = sold at least 70% of an average dish's share. Profitable = margin at or above the weighted average." })
        ]),
        el("div", { class: "me-stack" }, [R.n ? hint : null, refs.tiles, table, refs.h3, refs.grid].filter(Boolean))
      );
      refresh();
    }

    // the app doesn't redraw tools when only settings change (e.g. when the workbook first loads), so listen too
    var listening = false;
    function listen() {
      if (listening || !S.db) return; listening = true;
      S.db.doc("settings/main").onSnapshot(function () { if (S.view === "menueng" && $("view-menueng")) draw($("view-menueng")); });
    }
    function draw(container) {
      load();
      if (refs && editingNow(container) && container.contains(refs.tiles)) { refresh(); return; }
      if (!editingNow(container)) confirmClear = false;
      build(container);
    }
    addTool({ id: "menueng", label: "Menu engineering", render: function (container) { listen(); draw(container); } });
  })();
