  // ---------- Kitchen Manager tool: allergens (Health Canada priority allergens, gluten sources, sulphites) ----------
  // Data: each ingredient may carry allergens: [codes]. [] = checked, none. Missing = not checked yet.
  (function () {
    if (!has(MGR)) return;
    var ALG = [
      ["PNT", "Peanuts"], ["TRN", "Tree nuts"], ["SES", "Sesame"], ["MLK", "Milk"], ["EGG", "Eggs"], ["FSH", "Fish"],
      ["CRU", "Crustaceans"], ["MOL", "Molluscs"], ["SOY", "Soy"], ["WHT", "Wheat & triticale"], ["MUS", "Mustard"],
      ["GLU", "Gluten (barley, rye, oats)", "Gluten"], ["SUL", "Sulphites"]
    ];
    var NAME = {}; ALG.forEach(function (a) { NAME[a[0]] = a[2] || a[1]; });
    var DISCLAIMER = "Based on the allergens entered for each ingredient. Check supplier labels; cross-contact is not tracked.";
    function codesOf(x) { return Array.isArray(x && x.allergens) ? x.allergens.filter(function (c) { return NAME[c]; }) : null; }
    function ordered(set) { return ALG.map(function (a) { return a[0]; }).filter(function (c) { return set[c]; }); }

    // union over all lines, following prep recipes; ingredients not checked yet are listed by name
    function collect(it, depth, acc) {
      acc = acc || { set: {}, unchecked: {} };
      if (!it || depth > 6) return acc;
      (it.lines || []).forEach(function (l) {
        if (l.kind === "prep") { if (l.prep) collect(itemOf(l.prep), depth + 1, acc); return; }
        if (l.kind === "other" || !l.ing || !S.ing[l.ing]) return;
        var c = codesOf(S.ing[l.ing]);
        if (!c) acc.unchecked[l.ing] = S.ing[l.ing].name || "Unnamed";
        else c.forEach(function (k) { acc.set[k] = true; });
      });
      return acc;
    }
    function summary(it) {
      var a = collect(it, 0), codes = ordered(a.set), un = Object.keys(a.unchecked).map(function (k) { return a.unchecked[k]; }).sort();
      return { codes: codes, names: codes.map(function (c) { return NAME[c]; }), unchecked: un };
    }

    // ---------- styles ----------
    document.head.appendChild(el("style", { text: [
      ".alg-btn { display: inline-flex; gap: 3px; flex-wrap: wrap; align-items: center; min-width: 92px; max-width: 170px; text-align: left; padding: 2px 6px; min-height: 26px; background: transparent; border-color: transparent; }",
      "#i-table .alg-btn:hover { border-color: var(--accent); background: var(--surface); }",
      ".alg-chip { display: inline-block; font-size: 10.5px; font-weight: 600; letter-spacing: .03em; padding: 0 4px; border: 1px solid var(--line); border-radius: 2px; background: var(--surface2); color: var(--ink); }",
      ".alg-none { font-size: 12px; color: var(--muted); }",
      ".alg-todo { font-size: 12px; color: var(--warn); font-style: italic; }",
      "#alg-dlg { width: min(420px, calc(100vw - 32px)); }",
      ".alg-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 12px; }",
      ".alg-list label { display: flex !important; align-items: center; gap: 6px; color: var(--ink) !important; font-size: 13px !important; cursor: pointer; }",
      ".alg-list input { width: auto !important; margin: 0; }",
      ".alg-list .alg-code { margin-left: auto; font-size: 10.5px; color: var(--muted); }",
      ".alg-box { border: 1px solid var(--line); border-left: 4px solid var(--accent); background: var(--surface2); padding: 8px 10px; display: grid; gap: 6px; }",
      ".alg-box .alg-chips { display: flex; flex-wrap: wrap; gap: 4px; }",
      ".alg-box .alg-chip { font-size: 12px; padding: 1px 6px; }",
      "#view-allergens .alg-wrap { overflow: auto; max-height: calc(100vh - 210px); }",
      "#view-allergens table { width: auto; min-width: 100%; }",
      "#view-allergens th.alg-col { text-align: center; min-width: 46px; white-space: normal; line-height: 1.15; font-size: 11px; vertical-align: bottom; }",
      "#view-allergens th.alg-col b { display: block; font-size: 12px; }",
      "#view-allergens th.alg-col span { color: var(--muted); font-weight: 400; }",
      "#view-allergens td.alg-c { text-align: center; font-weight: 700; font-size: 15px; }",
      "#view-allergens td.alg-c.on { background: var(--sel); }",
      "#view-allergens td.alg-dish { position: sticky; left: 0; background: var(--surface); min-width: 180px; z-index: 1; }",
      "#view-allergens th.alg-dish { left: 0; z-index: 2; }",
      "#view-allergens td.alg-q { color: var(--warn); font-size: 12px; }",
      "#view-allergens .alg-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 8px; }",
      "#view-allergens .alg-disc { margin-top: 6px; }",
      ".alg-print { display: none; }",
      "@media print {",
      "  @page alg-land { size: landscape; margin: 10mm; }",
      "  #printcards .alg-print { display: block; page: alg-land; font-family: Arial, sans-serif; color: #000; }",
      "  .alg-print .ch { display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 4px; margin-bottom: 8px; }",
      "  .alg-print .cb { font-weight: 800; font-size: 18px; letter-spacing: .04em; }",
      "  .alg-print .cs { font-size: 12px; align-self: end; }",
      "  .alg-print h2 { font-size: 20px; margin: 2px 0 8px; }",
      "  .alg-print table { width: 100%; border-collapse: collapse; font-size: 12px; }",
      "  .alg-print th, .alg-print td { border: 1px solid #555; padding: 4px 5px; color: #000; background: #fff; position: static; text-align: center; }",
      "  .alg-print th { background: #e6e6e6; font-size: 10.5px; line-height: 1.15; vertical-align: bottom; }",
      "  .alg-print td.d, .alg-print th.d { text-align: left; }",
      "  .alg-print tr.sec td { background: #e6e6e6; font-weight: 700; text-align: left; }",
      "  .alg-print td.y { font-weight: 800; font-size: 14px; }",
      "  .alg-print td.q { font-size: 10.5px; text-align: left; }",
      "  .alg-print tr { break-inside: avoid; }",
      "  .alg-print p { font-size: 11px; margin: 6px 0 0; }",
      "}"
    ].join("\n") }));

    // ---------- ingredient checklist dialog ----------
    var dlg = null, dlgId = null;
    function closeDlg() { if (dlg) { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); } }
    function setAllergens(val) {
      var x = S.ing[dlgId]; if (!x) { closeDlg(); return; }
      if (val === undefined) delete x.allergens; else x.allergens = val;
      // write now rather than via the debounced saveIng: the dialog sits outside #i-table, so a snapshot from another
      // ingredient's save would otherwise replace S.ing before this one's timer fires and the change would be lost
      write("ingredients/" + dlgId, JSON.parse(JSON.stringify(x))).catch(function () {});
      closeDlg(); renderIng();
      toast(val === undefined ? "Marked not checked yet" : val.length ? "Allergens: " + val.map(function (c) { return NAME[c]; }).join(", ") : "No priority allergens");
    }
    function buildDlg() {
      var boxes = ALG.map(function (a) {
        return el("label", null, [el("input", { type: "checkbox", value: a[0], "data-alg": a[0] }), a[1], el("span", { class: "alg-code", text: a[0] })]);
      });
      dlg = el("dialog", { id: "alg-dlg", "aria-labelledby": "alg-title" }, [
        el("div", { class: "dlghead", id: "alg-title", text: "Allergens" }),
        el("div", { class: "dlgbody" }, [
          el("p", { class: "hint", id: "alg-for" }),
          el("div", { class: "alg-list" }, boxes),
          el("p", { class: "hint", text: "Tick everything the supplier label lists under “Contains”. Save with nothing ticked to record that you checked and it has none." })
        ]),
        el("div", { class: "dlgfoot" }, [
          el("button", { class: "btn", type: "button", id: "alg-unk", text: "Not checked yet", title: "Clear: you haven't read this label yet", onclick: function () { setAllergens(undefined); } }),
          el("span", { style: "flex:1" }),
          el("button", { class: "btn", type: "button", id: "alg-cancel", text: "Cancel", onclick: closeDlg }),
          el("button", { class: "btn primary", type: "button", id: "alg-save", text: "Save", onclick: function () {
            setAllergens(Array.prototype.filter.call(dlg.querySelectorAll("input[data-alg]"), function (b) { return b.checked; }).map(function (b) { return b.value; }));
          } })
        ])
      ]);
      document.body.appendChild(dlg);
    }
    function openDlg(id) {
      if (!dlg) buildDlg();
      dlgId = id; var x = S.ing[id] || {}, c = codesOf(x) || [];
      dlg.querySelector("#alg-title").textContent = "Allergens: " + (x.name || "Unnamed");
      dlg.querySelector("#alg-for").textContent = codesOf(x) ? (c.length ? "Currently: " + c.map(function (k) { return NAME[k]; }).join(", ") + "." : "Currently: checked, none of the priority allergens.") : "Not checked yet.";
      dlg.querySelectorAll("input[data-alg]").forEach(function (b) { b.checked = c.indexOf(b.value) >= 0; });
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    }
    function cellKids(x) {
      var c = codesOf(x);
      if (!c) return [el("span", { class: "alg-todo", text: "Not checked" })];
      if (!c.length) return [el("span", { class: "alg-none", text: "None" })];
      return c.map(function (k) { return el("span", { class: "alg-chip", title: NAME[k], text: k }); });
    }
    HOOKS.ingCols.push({ label: "Allergens", cell: function (x, id) {
      var c = codesOf(x);
      return el("button", { class: "btn alg-btn", type: "button", "data-alg-ing": id,
        "aria-label": "Allergens for " + (x.name || "ingredient") + ": " + (!c ? "not checked yet" : c.length ? c.map(function (k) { return NAME[k]; }).join(", ") : "none"),
        title: "Set allergens", onclick: function () { openDlg(id); } }, cellKids(x));
    } });

    // ---------- editor: combined allergens for a dish or prep recipe ----------
    HOOKS.editor.push(function (item) {
      var s = summary(item), prep = isPrep(item);
      return el("div", { class: "alg-box", id: "alg-editor" }, [
        el("h3", { text: "Allergens" + (prep ? " in this prep recipe" : " in this dish") }),
        s.codes.length ? el("div", { class: "alg-chips" }, s.names.map(function (n) { return el("span", { class: "alg-chip", text: n }); }))
          : el("div", { class: "alg-none", text: s.unchecked.length ? "None found so far." : "None of the priority allergens." }),
        s.unchecked.length ? el("div", { class: "warn", text: "Not checked yet: " + s.unchecked.join(", ") + ". Set them on the Ingredients sheet." }) : null
      ]);
    });

    // ---------- recipe card line ----------
    HOOKS.card.push(function (item) {
      var s = summary(item);
      var txt = s.codes.length ? s.names.join(", ") : s.unchecked.length ? "not fully checked" : "none of the priority allergens";
      if (s.codes.length && s.unchecked.length) txt += " (not fully checked)";
      return el("p", { class: "alg-card", style: "font-weight:700;font-size:13px;margin:10px 0 4px;padding:4px 6px;border:2px solid #000;color:#000;background:#fff" }, ["Allergens: " + txt]);
    });

    // ---------- matrix tab ----------
    function dishes() { return itemList().filter(function (it) { return !isPrep(it); }).map(function (it) { var live = itemOf(it.id) || it; return { id: it.id, name: live.name || "Unnamed", section: live.section || "Other", s: summary(live) }; }); }
    function printMatrix() {
      var rows = [], last = null, list = dishes();
      list.forEach(function (d) {
        if (d.section !== last) { last = d.section; rows.push(el("tr", { class: "sec" }, [el("td", { colspan: String(ALG.length + 2), text: d.section })])); }
        rows.push(el("tr", null, [el("td", { class: "d", text: d.name })].concat(ALG.map(function (a) { return el("td", { class: d.s.codes.indexOf(a[0]) >= 0 ? "y" : "", text: d.s.codes.indexOf(a[0]) >= 0 ? "✓" : "" }); }))
          .concat([el("td", { class: "q", text: d.s.unchecked.length ? "? " + d.s.unchecked.join(", ") : "" })])));
      });
      var sheet = el("div", { class: "alg-print" }, [
        el("div", { class: "ch" }, [el("span", { class: "cb", text: (bizName() || "Allergen chart").toUpperCase() }), el("span", { class: "cs", text: "Printed " + new Date().toLocaleDateString("en-CA") })]),
        el("h2", { text: "Allergen chart" }),
        el("table", null, [el("thead", null, [el("tr", null, [el("th", { class: "d", text: "Dish" })].concat(ALG.map(function (a) { return el("th", { text: a[2] || a[1] }); })).concat([el("th", { class: "d", text: "Not checked yet" })]))]), el("tbody", null, rows)]),
        el("p", { text: "✓ = contains. ? = some ingredients' allergens have not been checked yet: ask the kitchen. Gluten = barley, rye or oats." }),
        el("p", { text: DISCLAIMER })
      ]);
      $("printcards").replaceChildren(sheet);
      window.print();
    }
    addTool({ id: "allergens", label: "Allergens", render: function (box) {
      if (editingNow(box)) return;
      var list = dishes(), body = [], last = null, todo = 0;
      list.forEach(function (d) {
        if (d.section !== last) { last = d.section; body.push(el("tr", { class: "cat" }, [el("td", { colspan: String(ALG.length + 2), text: d.section })])); }
        if (d.s.unchecked.length) todo++;
        body.push(el("tr", { tabindex: "0", style: "cursor:pointer", title: "Open in Menu costing", onclick: function () { if (S.dirty) flushItem(); lsSet("fc-sel", d.id); S.sel = null; S.draft = null; showView("menu"); },
          onkeydown: function (e) { if (e.key === "Enter") this.click(); } }, [el("td", { class: "alg-dish", text: d.name })]
          .concat(ALG.map(function (a) { var on = d.s.codes.indexOf(a[0]) >= 0; return el("td", { class: "alg-c" + (on ? " on" : ""), title: on ? NAME[a[0]] : "", text: on ? "✓" : "" }); }))
          .concat([el("td", { class: "alg-q", text: d.s.unchecked.length ? "? " + d.s.unchecked.join(", ") : "" })])));
      });
      var nIng = Object.keys(S.ing).filter(function (k) { return !codesOf(S.ing[k]); }).length;
      box.replaceChildren(
        el("div", { class: "cmdbar" }, [
          el("button", { class: "btn primary", type: "button", id: "alg-print", text: "Print allergen chart", onclick: printMatrix }),
          el("span", { class: "sep" }),
          el("span", { class: todo ? "warn" : "hint", text: todo ? todo + " dish" + (todo > 1 ? "es use" : " uses") + " ingredients not checked yet (" + nIng + " ingredient" + (nIng === 1 ? "" : "s") + " in all)." : nIng ? nIng + " unused ingredient" + (nIng === 1 ? " is" : "s are") + " not checked yet." : "Every ingredient has been checked." }),
          el("span", { class: "grow" }),
          el("span", { class: "hint", text: "Set allergens per ingredient on the Ingredients sheet. Sauces and doughs are followed through." })
        ]),
        body.length ? el("div", { class: "tablewrap alg-wrap" }, [el("table", null, [
          el("thead", null, [el("tr", null, [el("th", { class: "alg-dish", text: "Dish" })].concat(ALG.map(function (a) { return el("th", { class: "alg-col", title: a[1] }, [el("b", { text: a[0] }), el("span", { text: a[2] || a[1] })]); })).concat([el("th", { text: "Not checked yet" })]))]),
          el("tbody", null, body)
        ])]) : el("div", { class: "tablewrap" }, [el("div", { class: "empty", text: S.loaded.items ? "No menu items yet." : "Loading…" })]),
        el("div", { class: "alg-legend hint" }, ALG.map(function (a) { return el("span", null, [el("b", { text: a[0] }), " " + a[1]]); })),
        el("p", { class: "hint alg-disc", text: "✓ contains · ? ingredients not checked yet. " + DISCLAIMER })
      );
    } });
  })();
