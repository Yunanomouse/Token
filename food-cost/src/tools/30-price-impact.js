  // ---------- Kitchen Manager tool: price-change impact ("what if" before accepting a supplier increase) ----------
  (function () {
    // scenario lives here, not in the workbook, so data re-renders never wipe it: [{ id, mode: "price"|"pct", val: "" }]
    var SCN = [], box = null;
    var css = "#view-impact .pi-grid { display: grid; gap: 10px; min-width: 0; }" +
      "#view-impact .pi-ings td input[type=number] { width: 90px; border-color: var(--line); background: var(--surface); }" +
      "#view-impact .pi-ings td select { border-color: var(--line); background: var(--surface); }" +
      "#view-impact .pi-hist { font-size: 11px; color: var(--muted); white-space: normal; }" +
      "#view-impact .pi-add { min-width: 240px; max-width: 100%; }" +
      "#view-impact .pi-up { color: var(--bad); }" +
      "#view-impact .pi-down { color: var(--ok); }" +
      "#view-impact td.pi-name { white-space: nowrap; }" +
      "#view-impact tr.pi-new td { background: color-mix(in srgb, var(--bad) 7%, transparent); }" +
      "#view-impact .pi-sec { margin-top: 4px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }" +
      "@media (max-width: 600px) { #view-impact .pi-add { min-width: 0; width: 100%; } }";
    document.head.appendChild(el("style", { text: css }));

    function r2(x) { return Math.round(x * 100) / 100; }
    function today() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
    function hasPrice(i) { return i && i.price != null && i.price !== "" && isFinite(num(i.price, NaN)); }
    // the price this scenario line would set, or NaN while it's blank or invalid
    function newPrice(s) {
      var i = S.ing[s.id]; if (!i || String(s.val).trim() === "") return NaN;
      var v = num(s.val, NaN); if (!isFinite(v)) return NaN;
      if (s.mode === "pct") return hasPrice(i) && v > -100 ? r2(num(i.price) * (1 + v / 100)) : NaN;
      return v >= 0 ? r2(v) : NaN;
    }
    function changes() {
      var m = {};
      SCN.forEach(function (s) { var p = newPrice(s); if (isFinite(p) && !(hasPrice(S.ing[s.id]) && p === num(S.ing[s.id].price))) m[s.id] = p; });
      return m;
    }
    // run fn with the scenario prices swapped in; real objects always restored, nothing is written
    function simulate(m, fn) {
      var saved = {};
      Object.keys(m).forEach(function (id) { saved[id] = S.ing[id]; S.ing[id] = Object.assign({}, saved[id], { price: m[id] }); });
      try { return fn(); } finally { Object.keys(saved).forEach(function (id) { S.ing[id] = saved[id]; }); }
    }
    // the item as the app costs it (unsaved edits in the open editor count, like Menu costing)
    function live(it) { return it.id === S.sel && S.draft ? Object.assign({ id: it.id }, S.draft) : it; }
    // does an item use any of these ingredients, directly or through prep recipes (any depth)?
    function uses(it, set, depth, seen) {
      if (!it || depth > 8) return false;
      return (it.lines || []).some(function (l) {
        if (l.kind === "ing") return !!set[l.ing];
        if (l.kind === "prep" && !seen[l.prep]) { seen[l.prep] = 1; var p = itemOf(l.prep); var r = uses(p, set, depth + 1, seen); delete seen[l.prep]; return r; }
        return false;
      });
    }
    function usedCount(id) { var set = {}; set[id] = 1; return itemList().filter(function (it) { return uses(live(it), set, 0, {}); }).length; }
    function snapshot() {
      return itemList().map(function (it) { var x = live(it); return { it: x, prep: isPrep(x), c: itemCalc(x), ps: isPrep(x) ? prepStats(x) : null }; });
    }
    function avgFc(rows) {
      var m = rows.filter(function (r) { return !r.prep && num(r.it.price) > 0 && isFinite(r.c.fc); });
      return m.length ? m.reduce(function (a, r) { return a + r.c.fc; }, 0) / m.length : NaN;
    }
    function dchg(a, b, money0) {
      var d = b - a, cls = Math.abs(d) < 0.005 ? "" : d > 0 ? "pi-up" : "pi-down";
      return el("td", { class: "n " + cls, text: !isFinite(d) ? "–" : (d > 0 ? "+" : d < 0 ? "−" : "") + (money0 ? money(Math.abs(d)).replace("−", "") : pct(Math.abs(d))) });
    }
    function fcCell(fc, t) { return el("td", { class: "n " + (!isFinite(fc) ? "" : fc <= t ? "good" : "over"), text: pct(fc) }); }

    // ----- results (recomputed live while typing, inputs untouched) -----
    function renderResults() {
      var out = box && box.querySelector("#pi-out"); if (!out) return;
      SCN.forEach(function (s) {
        var cell = box.querySelector('[data-pi-new="' + s.id + '"]'), real = box.querySelector('[data-pi-real="' + s.id + '"]'); if (!cell) return;
        var p = newPrice(s), i = S.ing[s.id];
        cell.textContent = isFinite(p) ? money(p) : "–";
        cell.className = "n " + (isFinite(p) && hasPrice(i) ? (p > num(i.price) ? "pi-up" : p < num(i.price) ? "pi-down" : "") : "");
        if (real) real.textContent = isFinite(p) ? perText(Object.assign({}, i, { price: p })) : "";
      });
      var m = changes(), ids = Object.keys(m), t = target();
      var ap = box.querySelector("#pi-apply"); if (ap) ap.disabled = !ids.length || !S.canWrite;
      if (!ids.length) {
        out.replaceChildren(el("div", { class: "tablewrap" }, [el("div", { class: "empty", text: SCN.length ? "Type a new price or a % change for the ingredients above to see what it does to your menu." : "Add the ingredients your supplier is changing. Nothing is saved until you press Apply new prices." })]));
        return;
      }
      var set = {}; ids.forEach(function (id) { set[id] = 1; });
      var before = snapshot(), after = simulate(m, snapshot);
      var rows = before.map(function (b, k) { return { b: b, a: after[k], hit: uses(b.it, set, 0, {}) }; });
      var dishes = rows.filter(function (r) { return r.hit && !r.b.prep; }), preps = rows.filter(function (r) { return r.hit && r.b.prep; });
      dishes.sort(function (x, y) { return (y.a.c.cost - y.b.c.cost) - (x.a.c.cost - x.b.c.cost) || (x.b.it.name || "").localeCompare(y.b.it.name || ""); });
      var newly = dishes.filter(function (r) { return num(r.b.it.price) > 0 && !(r.b.c.fc > t) && r.a.c.fc > t; });
      var avgB = avgFc(before), avgA = avgFc(after);
      var extra = dishes.reduce(function (a, r) { return a + (r.a.c.cost - r.b.c.cost); }, 0);
      var dRows = dishes.map(function (r) {
        var price = num(r.b.it.price), wasOver = r.b.c.fc > t, isOver = r.a.c.fc > t, nw = price > 0 && !wasOver && isOver;
        var chg = r.a.c.cost - r.b.c.cost;
        return el("tr", { class: nw ? "pi-new" : "" }, [
          el("td", { class: "pi-name", text: r.b.it.name || "Unnamed" }, [el("div", { class: "muted small", text: r.b.it.section || "" })]),
          el("td", { class: "n", text: price > 0 ? money(price) : "–" }),
          el("td", { class: "n", text: money(r.b.c.cost) }),
          el("td", { class: "n", text: money(r.a.c.cost) }),
          dchg(r.b.c.cost, r.a.c.cost, true),
          el("td", { class: "n " + (chg > 0.005 ? "pi-up" : chg < -0.005 ? "pi-down" : ""), text: r.b.c.cost > 0 ? (chg >= 0 ? "+" : "−") + pct(Math.abs(chg / r.b.c.cost * 100)) : "–" }),
          fcCell(r.b.c.fc, t), fcCell(r.a.c.fc, t),
          el("td", null, [price > 0 ? el("span", { class: "chip " + (nw ? "bad" : isOver ? "warn" : "good"), text: nw ? "Newly over" : isOver ? (wasOver ? "Still over" : "Over") : wasOver ? "Back under" : "OK" }) : el("span", { class: "muted", text: "no price" })]),
          el("td", { class: "n" + (isOver ? " over" : ""), text: money(r.a.c.need), title: "New plate cost ÷ " + t + "%" })
        ]);
      });
      var pRows = preps.map(function (r) {
        var f = r.b.ps.fam, k = f === "e" ? 1 : 1000, u = f === "m" ? "/kg" : f === "v" ? "/L" : " ea";
        return el("tr", null, [
          el("td", { class: "pi-name", text: r.b.it.name || "Unnamed" }, [el("div", { class: "muted small", text: num(r.b.it.yieldQty) ? "batch " + trimN(num(r.b.it.yieldQty), 2) + " " + r.b.it.yieldUnit : "" })]),
          el("td", { class: "n", text: money(r.b.ps.batch) }),
          el("td", { class: "n", text: money(r.a.ps.batch) }),
          dchg(r.b.ps.batch, r.a.ps.batch, true),
          el("td", { class: "n", text: isFinite(r.b.ps.per) ? money(r.b.ps.per * k) + u : "–" }),
          el("td", { class: "n", text: isFinite(r.a.ps.per) ? money(r.a.ps.per * k) + u : "–" })
        ]);
      });
      function th(h, k) { return el("th", { class: k ? "n" : "", scope: "col", text: h }); }
      out.replaceChildren(
        el("div", { class: "tiles" }, [
          tile("Dishes affected", String(dishes.length), preps.length ? "plus " + preps.length + " prep recipe" + (preps.length > 1 ? "s" : "") : "no prep recipes"),
          tile("Average food cost now", pct(avgB), "whole menu · target " + t + "%", isFinite(avgB) ? (avgB <= t ? "good" : "over") : ""),
          tile("Average food cost after", pct(avgA), isFinite(avgA - avgB) ? (avgA >= avgB ? "+" : "−") + trimN(Math.abs(avgA - avgB), 2) + " points" : "", isFinite(avgA) ? (avgA <= t ? "good" : "over") : ""),
          tile("Newly over target", String(newly.length), newly.length ? newly.map(function (r) { return r.b.it.name; }).slice(0, 3).join(", ") + (newly.length > 3 ? "…" : "") : "none", newly.length ? "over" : "good"),
          tile("Extra cost per round", money(extra), "one of each affected dish")
        ]),
        el("div", { class: "pi-sec" }, [el("h3", { text: "Menu dishes" }), el("span", { class: "hint", text: "Highest increase first. Your real prices are not changed." })]),
        el("div", { class: "tablewrap" }, [el("table", null, [
          el("thead", null, [el("tr", null, ["Dish", "Price", "Plate cost now", "New plate cost", "Change", "Change %", "Food cost now", "New food cost", "Target " + t + "%", "Price to stay at target"].map(th))]),
          el("tbody", null, dRows.length ? dRows : [el("tr", null, [el("td", { colspan: "10", class: "empty", text: "No menu dish uses these ingredients." })])])
        ])]),
        pRows.length ? el("div", { class: "pi-sec" }, [el("h3", { text: "Prep recipes" }), el("span", { class: "hint", text: "Sauces and doughs that use these ingredients; their new cost flows into the dishes above." })]) : null,
        pRows.length ? el("div", { class: "tablewrap" }, [el("table", null, [
          el("thead", null, [el("tr", null, ["Prep recipe", "Batch cost now", "New batch cost", "Change", "Per kg / L now", "New per kg / L"].map(th))]),
          el("tbody", null, pRows)
        ])]) : null
      );
    }

    // ----- apply to the real ingredients -----
    function apply() {
      var m = changes(), ids = Object.keys(m); if (!ids.length) return;
      if (!S.canWrite) { toast("Storage is not available."); return; }
      var list = ids.map(function (id) { var i = S.ing[id]; return "• " + (i.name || id) + ": " + (hasPrice(i) ? money(num(i.price)) : "no price") + " → " + money(m[id]); }).join("\n");
      if (!confirm("Change these prices on the Ingredients sheet? Every recipe will use them from now on.\n\n" + list)) return;
      var d = today();
      ids.forEach(function (id) {
        var i = S.ing[id], hist = Array.isArray(i.priceHistory) ? i.priceHistory.slice() : [];
        if (hasPrice(i)) hist.push({ date: d, price: num(i.price) });
        i.priceHistory = hist.slice(-20); i.price = m[id];
        // written right away (not debounced) so a data refresh can't put the old price back
        write("ingredients/" + id, JSON.parse(JSON.stringify(i))).catch(function () {});
      });
      SCN = [];
      toast("Updated " + ids.length + (ids.length === 1 ? " price" : " prices"));
      render();
    }

    // ----- inputs (rebuilt only when nobody is typing in them) -----
    function histText(i) {
      var h = Array.isArray(i.priceHistory) ? i.priceHistory : [];
      return h.slice(-3).reverse().map(function (x) { return money(num(x.price)) + " (" + x.date + ")"; }).join(" · ");
    }
    function build(c) {
      SCN = SCN.filter(function (s) { return S.ing[s.id]; });
      var inS = {}; SCN.forEach(function (s) { inS[s.id] = 1; });
      var pick = el("select", { class: "pi-add", "aria-label": "Add an ingredient to the scenario", onchange: function () {
        if (pick.value) { SCN.push({ id: pick.value, mode: "pct", val: "" }); var id = pick.value; build(c); var f = c.querySelector('[data-pi-val="' + id + '"]'); if (f) f.focus(); }
      } }, [el("option", { value: "", text: "Add an ingredient…" })].concat(ingList().filter(function (i) { return !inS[i.id]; }).map(function (i) {
        return el("option", { value: i.id, text: i.name + (i.supplier ? " (" + i.supplier + ")" : "") + (hasPrice(i) ? " · " + money(num(i.price)) : " · no price") });
      })));
      var addPct = el("input", { type: "number", step: "0.1", placeholder: "e.g. 5", "aria-label": "Percent for every ingredient in the scenario", style: "width:80px" });
      var rows = SCN.map(function (s, k) {
        var i = S.ing[s.id], n = usedCount(s.id), h = histText(i);
        var mode = el("select", { "aria-label": "Change type", onchange: function () { s.mode = mode.value; val.placeholder = s.mode === "pct" ? "e.g. 12" : "new price"; renderResults(); } }, [
          el("option", { value: "pct", text: "% change" }), el("option", { value: "price", text: "New price $" })]);
        mode.value = s.mode;
        var val = el("input", { type: "number", step: s.mode === "pct" ? "0.1" : "0.01", value: s.val, placeholder: s.mode === "pct" ? "e.g. 12" : "new price", "data-pi-val": s.id, "aria-label": "Change for " + (i.name || ""), oninput: function () { s.val = val.value; renderResults(); } });
        return el("tr", null, [
          el("td", { class: "pi-name" }, [el("b", { text: i.name || "Unnamed" }), el("div", { class: "muted small", text: (i.supplier ? i.supplier + " · " : "") + (i.packQty ? packText(i) : "") })]),
          el("td", { class: "n", text: hasPrice(i) ? money(num(i.price)) : "price?" }, [el("div", { class: "muted small", text: perText(i) })]),
          el("td", null, [mode]),
          el("td", null, [val]),
          el("td", { class: "n", "data-pi-new": s.id, text: "–" }, []),
          el("td", { class: "n muted small", "data-pi-real": s.id }),
          el("td", { class: "n", text: n ? n + (n === 1 ? " recipe" : " recipes") : "not used" }),
          el("td", { class: "pi-hist", text: h || "–" }),
          el("td", null, [el("button", { class: "btn danger", type: "button", text: "✕", "aria-label": "Remove " + (i.name || "") + " from the scenario", onclick: function () { SCN.splice(k, 1); build(c); } })])
        ]);
      });
      c.replaceChildren(el("div", { class: "pi-grid" }, [
        el("div", { class: "cmdbar" }, [
          el("h2", { text: "Price changes" }), el("span", { class: "sep" }), pick,
          SCN.length ? el("span", { class: "sep" }) : null,
          SCN.length ? el("span", { class: "muted small", text: "Same % for all:" }) : null, SCN.length ? addPct : null,
          SCN.length ? el("button", { class: "btn", type: "button", text: "Set", onclick: function () { if (addPct.value === "") return; SCN.forEach(function (s) { s.mode = "pct"; s.val = addPct.value; }); build(c); } }) : null,
          el("span", { class: "grow" }),
          SCN.length ? el("button", { class: "btn", type: "button", text: "Clear", onclick: function () { SCN = []; build(c); } }) : null,
          el("button", { class: "btn primary", type: "button", id: "pi-apply", text: "Apply new prices", disabled: true, onclick: apply })
        ]),
        el("p", { class: "hint", text: "What if a supplier raises prices? Pick the ingredients, type the new pack price or a % change, and see every dish and prep recipe that uses them, including through sauces and doughs. Nothing changes until you press Apply new prices." }),
        SCN.length ? el("div", { class: "tablewrap" }, [el("table", { class: "pi-ings" }, [
          el("thead", null, [el("tr", null, ["Ingredient", "Pack price now", "Change by", "Amount", "New pack price", "New real cost", "Used in", "Earlier prices", ""].map(function (h, k) { return el("th", { class: k === 1 || k === 4 || k === 5 || k === 6 ? "n" : "", scope: "col", text: h }); }))]),
          el("tbody", null, rows)
        ])]) : null,
        el("div", { class: "pi-grid", id: "pi-out" })
      ]));
      renderResults();
    }

    addTool({ id: "impact", label: "Price changes", render: function (container) {
      box = container;
      if (!S.loaded.ing || !S.loaded.items) { container.replaceChildren(el("div", { class: "empty", text: "Loading…" })); return; }
      if (editingNow(container) && container.querySelector("#pi-out")) { renderResults(); return; }
      build(container);
    } });
  })();
