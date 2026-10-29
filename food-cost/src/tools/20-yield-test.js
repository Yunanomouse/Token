  // ---------- Kitchen Manager tool: yield test ----------
  // Weigh a whole piece, record trim and other losses, credit usable by-products,
  // and get the real yield % and cost per usable kg. Tests are kept in settings.yieldTests.
  (function () {
    var W = { kg: 1000, g: 1, lb: 453.592, oz: 28.3495 }, WUNITS = ["kg", "g", "lb", "oz"];
    var DKEY = "fc-yield-draft";
    function today() { var d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
    function blankTest() { return { savedId: null, date: today(), ing: "", start: "", startUnit: "kg", losses: [{ label: "Fat trim", qty: "", unit: "kg" }, { label: "Silverskin", qty: "", unit: "kg" }], byproducts: [], portion: "", portionUnit: "oz" }; }
    var D = (function () { try { var x = JSON.parse(lsGet(DKEY)); if (x && Array.isArray(x.losses) && Array.isArray(x.byproducts)) return x; } catch (e) {} return blankTest(); })();
    var R = {}, box = null, confirmDel = null;
    function keep() { lsSet(DKEY, JSON.stringify(D)); }
    function tests() { return Array.isArray(S.settings.yieldTests) ? S.settings.yieldTests : []; }
    function g(qty, unit) { return Math.max(0, num(qty)) * (W[unit] || 0); }
    function wText(gr) { if (!isFinite(gr)) return "–"; return Math.abs(gr) >= 1000 ? trimN(gr / 1000, 3) + " kg" : trimN(gr, 0) + " g"; }
    function lbText(gr) { return isFinite(gr) ? trimN(gr / 453.592, 2) + " lb" : ""; }
    function byWeight(i) { return !!(i && U[i.unit] && U[i.unit][0] === "m"); }

    function calc(t) {
      var i = S.ing[t.ing], r = { i: i, ok: false, msg: "" };
      r.startG = g(t.start, t.startUnit);
      r.lossG = (t.losses || []).reduce(function (a, l) { return a + g(l.qty, l.unit); }, 0);
      r.byG = (t.byproducts || []).reduce(function (a, l) { return a + g(l.qty, l.unit); }, 0);
      r.credit = (t.byproducts || []).reduce(function (a, l) { return a + Math.max(0, num(l.qty)) * Math.max(0, num(l.value)); }, 0);
      r.usableG = r.startG - r.lossG - r.byG;
      r.yieldPct = r.startG > 0 ? r.usableG / r.startG * 100 : NaN;
      var base = i ? packBase(i) : 0;
      r.apPerG = byWeight(i) && base > 0 && i.price != null && i.price !== "" ? num(i.price) / base : NaN;
      r.apCost = r.startG * r.apPerG;
      r.net = r.apCost - r.credit;
      r.perG = r.usableG > 0 ? r.net / r.usableG : NaN;
      r.curYield = i ? num(i.yield, 100) : NaN;
      r.curPerG = i ? usableCost(i) : NaN;
      if (!i) r.msg = "Pick the ingredient you're testing.";
      else if (!byWeight(i)) r.msg = (i.name || "This ingredient") + " is priced by " + (U[i.unit] && U[i.unit][0] === "v" ? "volume" : "count") + ". A yield test needs something bought by weight (kg, lb or g). Pick a whole cut, a fish or a case of produce.";
      else if (!(r.startG > 0)) r.msg = "Weigh the whole piece as it came in and enter the starting weight.";
      else if (!(r.usableG > 0)) r.msg = "Losses and by-products add up to the whole piece or more. Check the weights and units.";
      else { r.ok = true; if (!isFinite(r.apPerG)) r.msg = "Give " + (i.name || "this ingredient") + " a price and pack size on the Ingredients sheet to see costs."; else if (!(r.lossG + r.byG > 0)) r.msg = "Add what you trimmed off: fat, silverskin, bones, cooking loss."; }
      return r;
    }

    function update() {
      if (!R.results) return;
      var r = calc(D), i = r.i, hasCost = r.ok && isFinite(r.perG);
      R.msg.textContent = r.msg; R.msg.hidden = !r.msg;
      R.results.replaceChildren(
        tile("Total loss", r.startG > 0 ? wText(r.lossG) : "–", r.startG > 0 ? lbText(r.lossG) + (r.byG > 0 ? " · plus " + wText(r.byG) + " by-products" : "") : ""),
        tile("Usable weight", r.ok ? wText(r.usableG) : "–", r.ok ? lbText(r.usableG) : ""),
        tile("Yield", r.ok ? pct(r.yieldPct) : "–", r.ok ? "usable ÷ starting weight" : ""),
        tile("As-purchased cost", r.ok && isFinite(r.apCost) ? money(r.apCost) : "–", isFinite(r.apPerG) ? money(r.apPerG * 1000) + "/kg as bought" : ""),
        tile("By-product credit", r.credit > 0 ? "−" + money(r.credit) : money(0), r.credit > 0 && isFinite(r.apCost) ? "net " + money(r.net) : "trim you can use elsewhere"),
        tile("Cost per usable kg", hasCost ? money(r.perG * 1000) : "–", hasCost ? money(r.perG * 453.592) + "/lb · " + money(r.perG * 28.3495) + "/oz" : "", hasCost && isFinite(r.curPerG) ? (r.perG > r.curPerG * 1.005 ? "over" : "good") : "")
      );
      // compare with what the Ingredients sheet uses now
      if (i && byWeight(i)) {
        var rows = [
          ["Usable %", trimN(r.curYield, 1) + "%", r.ok ? pct(r.yieldPct) : "–", r.ok ? r.yieldPct - r.curYield : NaN, function (x) { return (x > 0 ? "+" : x < 0 ? "−" : "") + trimN(Math.abs(x), 1) + " pts"; }, 1],
          ["Real cost per kg", isFinite(r.curPerG) ? money(r.curPerG * 1000) : "–", hasCost ? money(r.perG * 1000) : "–", hasCost && isFinite(r.curPerG) ? (r.perG - r.curPerG) * 1000 : NaN, function (x) { return (x > 0 ? "+" : "") + money(x); }, -1],
          ["Real cost per lb", isFinite(r.curPerG) ? money(r.curPerG * 453.592) : "–", hasCost ? money(r.perG * 453.592) : "–", hasCost && isFinite(r.curPerG) ? (r.perG - r.curPerG) * 453.592 : NaN, function (x) { return (x > 0 ? "+" : "") + money(x); }, -1]
        ];
        R.compare.replaceChildren(el("table", null, [
          el("thead", null, [el("tr", null, [el("th", { text: "" }), el("th", { class: "n", text: "Ingredients sheet now" }), el("th", { class: "n", text: "This test" }), el("th", { class: "n", text: "Difference" })])]),
          el("tbody", null, rows.map(function (x) {
            var d = x[3], cls = !isFinite(d) || Math.abs(d) < 0.005 ? "" : d * x[5] > 0 ? "good" : "over";
            return el("tr", null, [el("td", { text: x[0] }), el("td", { class: "n", text: x[1] }), el("td", { class: "n", text: x[2] }), el("td", { class: "n " + cls, text: isFinite(d) ? x[4](d) : "–" })]);
          }))
        ]));
        R.compareWrap.hidden = false;
        var newY = r.ok ? Math.round(r.yieldPct) : NaN;
        R.note.textContent = hasCost ? "Using " + (isFinite(newY) ? newY : "–") + "% on the Ingredients sheet would cost it at " + money(r.apPerG * 1000 / (newY / 100)) + "/kg." + (r.credit > 0 ? " The by-product credit isn't part of usable %, so dishes are costed slightly higher than this test." : "") : "";
      } else { R.compareWrap.hidden = true; R.note.textContent = ""; }
      // portions
      var pg = g(D.portion, D.portionUnit);
      R.portions.replaceChildren(
        tile("Portions", r.ok && pg > 0 ? String(Math.floor(r.usableG / pg + 1e-9)) : "–", r.ok && pg > 0 ? trimN(r.usableG / pg, 1) + " exactly" : "enter a portion size"),
        tile("Cost per portion", hasCost && pg > 0 ? money(r.perG * pg) : "–", hasCost && pg > 0 ? trimN(num(D.portion), 2) + " " + D.portionUnit + " cut" : ""),
        tile("Leftover", r.ok && pg > 0 ? wText(r.usableG - Math.floor(r.usableG / pg + 1e-9) * pg) : "–", "")
      );
      // line credits
      (D.byproducts || []).forEach(function (l, k) { var c = R.lines && R.lines[k]; if (c) c.textContent = money(Math.max(0, num(l.qty)) * Math.max(0, num(l.value))); });
      // buttons
      var y = r.ok ? Math.round(r.yieldPct) : NaN, canUse = r.ok && y >= 1 && y <= 100;
      R.use.textContent = canUse ? (y === Math.round(r.curYield) ? "Usable % is already " + y + "%" : "Use this yield (" + y + "%)") : "Use this yield";
      R.use.disabled = !canUse || y === Math.round(r.curYield);
      R.save.disabled = !r.ok;
      R.save.textContent = D.savedId && tests().some(function (t) { return t.id === D.savedId; }) ? "Update saved test" : "Save test";
    }
    function changed() { keep(); update(); }

    function saveTest() {
      var r = calc(D); if (!r.ok) { toast(r.msg || "Finish the test first."); return; }
      var list = tests().slice(), id = D.savedId && list.some(function (t) { return t.id === D.savedId; }) ? D.savedId : newId("yt");
      var t = { id: id, date: D.date || today(), ing: D.ing, ingName: r.i.name || "", start: num(D.start), startUnit: D.startUnit,
        losses: D.losses.filter(function (l) { return num(l.qty) > 0 || l.label; }).map(function (l) { return { label: l.label || "", qty: num(l.qty), unit: l.unit }; }),
        byproducts: D.byproducts.filter(function (l) { return num(l.qty) > 0 || l.label; }).map(function (l) { return { label: l.label || "", qty: num(l.qty), unit: l.unit, value: num(l.value) }; }),
        yieldPct: Math.round(r.yieldPct * 10) / 10, costPerKg: isFinite(r.perG) ? Math.round(r.perG * 100000) / 100 : null,
        portion: num(D.portion) > 0 ? num(D.portion) : null, portionUnit: D.portionUnit };
      var at = -1; list.forEach(function (x, k) { if (x.id === id) at = k; });
      if (at >= 0) list[at] = t; else list.push(t);
      S.settings.yieldTests = list; D.savedId = id; keep();
      write("settings/main", { yieldTests: JSON.parse(JSON.stringify(list)) }, true).then(function () { toast(at >= 0 ? "Test updated" : "Test saved"); }, function () {});
      build();
    }
    function useYield() {
      var r = calc(D); if (!r.ok) return;
      var y = Math.round(r.yieldPct), i = r.i;
      if (!(y >= 1 && y <= 100)) return;
      if (!confirm("Set the usable % of " + (i.name || "this ingredient") + " from " + trimN(r.curYield, 1) + "% to " + y + "%?\n\nEvery dish and prep recipe that uses it will be re-costed.")) return;
      S.ing[D.ing].yield = y; saveIng(D.ing);
      toast((i.name || "Ingredient") + " now " + y + "% usable");
      renderSum(); build();
    }
    function openTest(t) {
      D = { savedId: t.id, date: t.date || today(), ing: t.ing, start: t.start, startUnit: W[t.startUnit] ? t.startUnit : "kg",
        losses: (t.losses || []).map(function (l) { return Object.assign({}, l); }), byproducts: (t.byproducts || []).map(function (l) { return Object.assign({}, l); }),
        portion: t.portion || "", portionUnit: t.portionUnit === "g" ? "g" : "oz" };
      keep(); build(); if (box) box.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function delTest(t) {
      if (confirmDel !== t.id) { confirmDel = t.id; build(); return; }
      confirmDel = null;
      var list = tests().filter(function (x) { return x.id !== t.id; });
      S.settings.yieldTests = list; if (D.savedId === t.id) { D.savedId = null; keep(); }
      write("settings/main", { yieldTests: JSON.parse(JSON.stringify(list)) }, true).then(function () { toast("Test deleted"); }, function () {});
      build();
    }

    function wSel(val, onch, label) {
      var s = el("select", { "aria-label": label, onchange: function () { onch(s.value); } }, WUNITS.map(function (u) { return el("option", { value: u, text: u }); }));
      s.value = W[val] ? val : "kg"; return s;
    }
    function numIn(obj, key, label, ph, w) {
      return el("input", { type: "number", min: "0", step: "0.01", value: obj[key] != null ? obj[key] : "", placeholder: ph || "", "aria-label": label, style: w ? "width:" + w : null, oninput: function (e) { obj[key] = e.target.value; changed(); } });
    }
    function txtIn(obj, key, label, ph) { return el("input", { type: "text", value: obj[key] || "", placeholder: ph, "aria-label": label, oninput: function (e) { obj[key] = e.target.value; keep(); } }); }
    function rmBtn(arr, k, label) { return el("button", { class: "btn danger", type: "button", "aria-label": label, text: "✕", onclick: function () { arr.splice(k, 1); keep(); build(); } }); }

    function build() {
      if (!box) return;
      var ings = ingList(), wt = ings.filter(byWeight), other = ings.filter(function (i) { return !byWeight(i); });
      if (D.ing && !S.ing[D.ing] && S.loaded.ing) D.ing = "";
      var sel = el("select", { "aria-label": "Ingredient tested", style: "min-width:260px", onchange: function () { D.ing = sel.value; D.savedId = null; keep(); build(); } }, [
        el("option", { value: "", text: "Pick an ingredient" }),
        wt.length ? el("optgroup", { label: "Bought by weight" }, wt.map(function (i) { return el("option", { value: i.id, text: i.name + (i.supplier ? " (" + i.supplier + ")" : "") }); })) : null,
        other.length ? el("optgroup", { label: "Bought by volume or count (can't be tested)" }, other.map(function (i) { return el("option", { value: i.id, text: i.name }); })) : null
      ]);
      sel.value = S.ing[D.ing] ? D.ing : "";
      var date = el("input", { type: "date", value: D.date || "", "aria-label": "Test date", oninput: function (e) { D.date = e.target.value; keep(); } });

      R.lines = [];
      var lossRows = D.losses.map(function (l, k) {
        return el("tr", null, [el("td", null, [txtIn(l, "label", "Loss", "e.g. Fat trim")]), el("td", { class: "n" }, [numIn(l, "qty", "Weight lost")]), el("td", null, [wSel(l.unit, function (v) { l.unit = v; changed(); }, "Unit")]), el("td", { class: "x" }, [rmBtn(D.losses, k, "Remove loss line")])]);
      });
      var byRows = D.byproducts.map(function (l, k) {
        var credit = el("td", { class: "n" });
        R.lines[k] = credit;
        return el("tr", null, [el("td", null, [txtIn(l, "label", "By-product", "e.g. Trim for burger")]), el("td", { class: "n" }, [numIn(l, "qty", "By-product weight")]), el("td", null, [wSel(l.unit, function (v) { l.unit = v; changed(); }, "Unit")]),
          el("td", { class: "n" }, [numIn(l, "value", "Worth, dollars per unit", "$ per unit")]), credit, el("td", { class: "x" }, [rmBtn(D.byproducts, k, "Remove by-product")])]);
      });
      var i = S.ing[D.ing];
      var left = el("div", { class: "panel" }, [
        el("div", { class: "panelhead", text: "Test sheet" + (i ? " · " + (i.name || "") : "") }),
        i && byWeight(i) ? el("p", { class: "hint", text: "Invoice: " + perText(Object.assign({}, i, { yield: 100 })).split(" · ")[0] + " as bought · Ingredients sheet uses " + trimN(num(i.yield, 100), 1) + "% usable." }) : null,
        el("div", { class: "fields" }, [
          el("label", null, ["Starting weight (as purchased)", el("div", { class: "row yt-pair" }, [numIn(D, "start", "Starting weight", "e.g. 5"), wSel(D.startUnit, function (v) { D.startUnit = v; changed(); }, "Starting weight unit")])])
        ]),
        el("div", { class: "toolbar" }, [el("h3", { text: "Losses" }), el("span", { class: "hint", text: "Fat, silverskin, bones, cooking loss: anything that goes in the bin." })]),
        el("div", { class: "tablewrap" }, [el("table", null, [
          el("thead", null, [el("tr", null, [el("th", { text: "What came off" }), el("th", { class: "n", text: "Weight" }), el("th", { text: "Unit" }), el("th", { text: "" })])]),
          el("tbody", null, lossRows.length ? lossRows : [el("tr", null, [el("td", { colspan: "4", class: "empty", text: "No losses yet." })])])
        ])]),
        el("div", { class: "row" }, [el("button", { class: "btn", type: "button", text: "Add loss", onclick: function () { D.losses.push({ label: "", qty: "", unit: D.startUnit || "kg" }); keep(); build(); } }),
          D.losses.some(function (l) { return /cook/i.test(l.label || ""); }) ? null : el("button", { class: "btn", type: "button", text: "Add cooking loss", onclick: function () { D.losses.push({ label: "Cooking loss", qty: "", unit: D.startUnit || "kg" }); keep(); build(); } })]),
        el("div", { class: "toolbar" }, [el("h3", { text: "Usable by-products (optional)" }), el("span", { class: "hint", text: "Trim you'll use elsewhere. Its value comes off the cost of the main cut." })]),
        byRows.length ? el("div", { class: "tablewrap" }, [el("table", null, [
          el("thead", null, [el("tr", null, [el("th", { text: "By-product" }), el("th", { class: "n", text: "Weight" }), el("th", { text: "Unit" }), el("th", { class: "n", text: "Worth ($ per unit)" }), el("th", { class: "n", text: "Credit" }), el("th", { text: "" })])]),
          el("tbody", null, byRows)
        ])]) : null,
        el("div", { class: "row" }, [el("button", { class: "btn", type: "button", text: "Add by-product", onclick: function () { D.byproducts.push({ label: "", qty: "", unit: D.startUnit || "kg", value: "" }); keep(); build(); } })]),
        el("div", { class: "toolbar" }, [el("h3", { text: "Portions" }), el("span", { class: "hint", text: "How many steaks or fillets the usable weight gives." })]),
        el("div", { class: "fields" }, [el("label", null, ["Portion size", el("div", { class: "row yt-pair" }, [numIn(D, "portion", "Portion size", "e.g. 8"),
          (function () { var s = el("select", { "aria-label": "Portion unit", onchange: function () { D.portionUnit = s.value; changed(); } }, [el("option", { value: "oz", text: "oz" }), el("option", { value: "g", text: "g" })]); s.value = D.portionUnit === "g" ? "g" : "oz"; return s; })()])])]),
        R.portions = el("div", { class: "tiles" })
      ]);

      R.msg = el("div", { class: "notice", role: "status" });
      R.results = el("div", { class: "tiles yt-res" });
      R.compare = el("div", { class: "tablewrap" });
      R.note = el("p", { class: "hint" });
      R.compareWrap = el("div", { class: "stack" }, [el("h3", { text: "Compared with the Ingredients sheet" }), R.compare, R.note]);
      R.save = el("button", { class: "btn", type: "button", text: "Save test", onclick: saveTest });
      R.use = el("button", { class: "btn primary", type: "button", text: "Use this yield", onclick: useYield });
      var right = el("div", { class: "panel" }, [
        el("div", { class: "panelhead", text: "Results" }),
        R.msg, R.results, R.compareWrap,
        el("div", { class: "row" }, [R.save, R.use])
      ]);

      // history, newest first, with change from the previous test of the same ingredient
      var all = tests().slice().sort(function (a, b) { return String(b.date || "").localeCompare(String(a.date || "")); });
      var hist = all.map(function (t) {
        var prev = all.filter(function (x) { return x.ing === t.ing && x.id !== t.id && String(x.date || "") <= String(t.date || "") && all.indexOf(x) > all.indexOf(t); })[0];
        var dy = prev ? num(t.yieldPct) - num(prev.yieldPct) : NaN, ii = S.ing[t.ing];
        return el("tr", { class: t.id === D.savedId ? "sel" : "" }, [
          el("td", { text: t.date || "" }),
          el("td", { text: ii ? ii.name : (t.ingName || "Deleted ingredient") }),
          el("td", { class: "n", text: trimN(num(t.start), 3) + " " + (t.startUnit || "kg") }),
          el("td", { class: "n", text: pct(num(t.yieldPct)) }),
          el("td", { class: "n" }, [isFinite(dy) ? el("span", { class: "chip " + (Math.abs(dy) < 0.05 ? "" : dy > 0 ? "good" : "bad"), text: (dy > 0 ? "+" : dy < 0 ? "−" : "") + trimN(Math.abs(dy), 1) + " pts" }) : el("span", { class: "muted", text: "first" })]),
          el("td", { class: "n", text: t.costPerKg != null ? money(num(t.costPerKg)) : "–" }),
          el("td", { class: "n muted", text: ii ? trimN(num(ii.yield, 100), 1) + "%" : "" }),
          el("td", { class: "x" }, [el("div", { class: "row" }, [el("button", { class: "btn", type: "button", text: "Open", onclick: function () { openTest(t); } }),
            el("button", { class: "btn danger", type: "button", text: confirmDel === t.id ? "Tap again" : "Delete", onclick: function () { delTest(t); } })])])
        ]);
      });

      box.replaceChildren(
        el("div", { class: "cmdbar" }, [
          el("label", { class: "row muted" }, ["Ingredient ", sel]), el("span", { class: "sep" }),
          el("label", { class: "row muted" }, ["Test date ", date]), el("span", { class: "sep" }),
          el("button", { class: "btn", type: "button", text: "New test", onclick: function () { var ing = D.ing; D = blankTest(); D.ing = ing; confirmDel = null; keep(); build(); } }),
          el("span", { class: "grow" }),
          el("span", { class: "hint", text: "Weigh the piece as it came in, trim it, weigh what came off. Yield % and the real cost per kg update as you type." })
        ]),
        el("div", { class: "yt-grid" }, [left, right]),
        el("div", { class: "toolbar yt-histhead" }, [el("h3", { text: "Saved tests" }), el("span", { class: "hint", text: "Compare tests over time: a falling yield can mean a supplier change or a new cook on the block." })]),
        el("div", { class: "tablewrap" }, [all.length ? el("table", null, [
          el("thead", null, [el("tr", null, [el("th", { text: "Date" }), el("th", { text: "Ingredient" }), el("th", { class: "n", text: "Start" }), el("th", { class: "n", text: "Yield" }), el("th", { class: "n", text: "vs last test" }), el("th", { class: "n", text: "Cost per usable kg" }), el("th", { class: "n", text: "Usable % now" }), el("th", { text: "" })])]),
          el("tbody", null, hist)
        ]) : el("div", { class: "empty", text: "No saved tests yet. Run a test above and press Save test." })])
      );
      update();
    }

    var css = document.createElement("style");
    css.textContent = [
      "#view-yield .yt-grid { display: grid; grid-template-columns: minmax(0, 640px) minmax(0, 1fr); gap: 12px; align-items: start; margin-bottom: 12px; }",
      "@media (max-width: 1000px) { #view-yield .yt-grid { grid-template-columns: 1fr; } }",
      "#view-yield .yt-pair { flex-wrap: nowrap; }",
      "#view-yield .yt-pair input { flex: 1; min-width: 0; }",
      "#view-yield .yt-pair select { width: auto; flex: none; }",
      "#view-yield input[type=\"date\"] { background: var(--surface); border: 1px solid var(--line); border-radius: 2px; padding: 3px 6px; min-height: 26px; color: var(--ink); font: inherit; }",
      "#view-yield td.x { width: 1%; white-space: nowrap; }",
      "#view-yield .notice { margin: 0; }",
      "#view-yield .yt-res { grid-template-columns: repeat(3, minmax(0, 1fr)); border-bottom: 0; }",
      "#view-yield .yt-res .tile { border-bottom: 1px solid var(--line); }",
      "#view-yield .yt-res .tile:nth-child(3n) { border-right: 0; }",
      "#view-yield .yt-res .tile .v { font-size: 18px; }",
      "@media (max-width: 600px) { #view-yield .yt-res { grid-template-columns: repeat(2, minmax(0, 1fr)); } #view-yield .yt-res .tile:nth-child(3n) { border-right: 1px solid var(--grid); } #view-yield .yt-res .tile:nth-child(2n) { border-right: 0; } }",
      "#view-yield .yt-histhead { margin: 4px 0 6px; justify-content: flex-start; gap: 10px; }",
      "#view-yield .cmdbar select { max-width: 100%; }"
    ].join("\n");
    document.head.appendChild(css);

    addTool({ id: "yield", label: "Yield test", render: function (container) {
      var fresh = box !== container || !container.firstChild;
      box = container;
      if (!fresh && editingNow(container)) { update(); return; }
      build();
    } });
  })();
