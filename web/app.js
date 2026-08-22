/* Canada Tax 2026 - calculation engine and view.
   Tax math mirrors examples/income_tax_calculator.py exactly so the browser and
   the CLI agree on every figure. Data is read from data/json/ at runtime. */

'use strict';

const DATA = '../data/json/';

const FILES = {
  income: 'personal_income_tax_2026.json',
  payroll: 'payroll_contributions_2026.json',
  sales: 'sales_tax_2026.json',
  corporate: 'corporate_income_tax_2026.json',
  credits: 'credits_and_limits_2026.json',
};

let D = null;

/* ---------------- formatting ---------------- */

const cad0 = new Intl.NumberFormat('en-CA', {
  style: 'currency', currency: 'CAD', maximumFractionDigits: 0,
});

const cad2 = new Intl.NumberFormat('en-CA', {
  style: 'currency', currency: 'CAD', minimumFractionDigits: 2, maximumFractionDigits: 2,
});

const money = (n) => cad0.format(n);
const money2 = (n) => cad2.format(n);
/** Percent with up to `dp` decimals, trailing zeros and any dangling point removed. */
const pct = (n, dp = 1) =>
  `${(n * 100)
    .toFixed(dp)
    .replace(/(\.\d*?)0+$/, '$1')
    .replace(/\.$/, '')}%`;

/* Tax math lives in tax.js so Node can verify it against the Python. */
const { estimate: rawEstimate } = globalThis.TaxEngine;
const estimate = (income, code) => rawEstimate(income, code, D);

/* ---------------- rendering ---------------- */

const $ = (sel) => document.querySelector(sel);

function segments(r) {
  const rows = [
    { key: 'Federal tax', value: r.fedTax, color: 'var(--seg-1)' },
    { key: 'Provincial tax', value: r.provTax, color: 'var(--seg-2)' },
    { key: r.isQuebec ? 'QPP + QPP2' : 'CPP + CPP2', value: r.pension + r.pension2, color: 'var(--seg-3)' },
    { key: 'EI', value: r.ei, color: 'var(--seg-4)' },
  ];
  if (r.qpip > 0) rows.push({ key: 'QPIP', value: r.qpip, color: 'var(--seg-5)' });
  rows.push({ key: 'Take-home', value: r.keep, color: 'var(--accent)' });
  return rows;
}

function renderResult(r) {
  const rows = segments(r);
  const denom = r.income > 0 ? r.income : 1;

  const parts = [];
  if (r.surtax > 0) parts.push(`surtax ${money2(r.surtax)}`);
  if (r.premium > 0) parts.push(`health premium ${money2(r.premium)}`);
  const provNote = parts.length
    ? `<div class="sub">Provincial tax includes ${parts.join(' and ')}.</div>`
    : '';

  $('#result').innerHTML = `
    <div class="result-head">
      <div class="stat keep">
        <div class="k">Take-home on ${money(r.income)}</div>
        <div class="v">${money(r.keep)}</div>
        <div class="sub">${r.name}</div>
      </div>
      <div class="stat">
        <div class="k">Total deductions</div>
        <div class="v">${money(r.total)}</div>
        <div class="sub">${pct(r.avgRate)} average rate</div>
      </div>
      <div class="stat">
        <div class="k">Marginal rate</div>
        <div class="v">${pct(r.marginal)}</div>
        <div class="sub">on the next dollar</div>
      </div>
    </div>

    <div class="bar" role="img" aria-label="${
      rows.map((s) => `${s.key} ${pct(s.value / denom)}`).join(', ')
    }">
      ${rows
        .filter((s) => s.value > 0)
        .map((s) => `<span style="width:${(s.value / denom) * 100}%;background:${s.color}"></span>`)
        .join('')}
    </div>

    <div class="legend">
      ${rows
        .map(
          (s) => `<div>
            <div class="k"><span class="swatch" style="background:${s.color}"></span>${s.key}</div>
            <div class="v">${money2(s.value)}</div>
            <div class="pct">${pct(s.value / denom)} of income</div>
          </div>`
        )
        .join('')}
    </div>
    ${provNote}
  `;
}

let sortKey = 'total';
let sortDir = 1;

function renderComparison(income, current) {
  const rows = Object.keys(D.income.provinces).map((code) => estimate(income, code));

  rows.sort((a, b) => {
    if (sortKey === 'name') return a.name.localeCompare(b.name) * sortDir;
    const map = {
      fed: 'fedTax', prov: 'provTax', payroll: 'payroll',
      total: 'total', rate: 'avgRate', keep: 'keep',
    };
    return (a[map[sortKey]] - b[map[sortKey]]) * sortDir;
  });

  $('#cmp-body').innerHTML = rows
    .map(
      (r) => `<tr class="${r.code === current ? 'is-current' : ''}">
        <td>${r.name}</td>
        <td>${money(r.fedTax)}</td>
        <td>${money(r.provTax)}</td>
        <td>${money(r.payroll)}</td>
        <td>${money(r.total)}</td>
        <td>${pct(r.avgRate)}</td>
        <td class="keep">${money(r.keep)}</td>
      </tr>`
    )
    .join('');

  document.querySelectorAll('#cmp thead button').forEach((b) => {
    const active = b.dataset.sort === sortKey;
    b.querySelector('.arrow').textContent = active ? (sortDir === 1 ? '▲' : '▼') : '';
    b.closest('th').setAttribute('aria-sort', active ? (sortDir === 1 ? 'ascending' : 'descending') : 'none');
  });
}

function renderSales(code) {
  const j = D.sales.jurisdictions[code];
  const all = Object.entries(D.sales.jurisdictions)
    .sort((a, b) => a[1].total_rate - b[1].total_rate);
  const lowest = all[0][1];
  const highest = all[all.length - 1][1];

  $('#sales-lede').textContent =
    `Combined rate on a typical taxable sale. ${j.name} charges ${pct(j.total_rate, 3)}.`;

  $('#sales-grid').innerHTML = `
    <div>
      <h3>${j.name}</h3>
      <div class="big">${pct(j.total_rate, 3)}</div>
      <p>${j.system}</p>
    </div>
    <div>
      <h3>On a $100 purchase</h3>
      <div class="big">${money2(100 * j.total_rate)}</div>
      <p>Tax added at the register.</p>
    </div>
    <div>
      <h3>Lowest in Canada</h3>
      <div class="big">${pct(lowest.total_rate, 0)}</div>
      <p>${lowest.name}, ${lowest.system}.</p>
    </div>
    <div>
      <h3>Highest in Canada</h3>
      <div class="big">${pct(highest.total_rate, 3)}</div>
      <p>${highest.name}, ${highest.system}.</p>
    </div>
  `;
}

function renderCorporate(code) {
  const fed = D.corporate.federal;
  const p = D.corporate.provincial[code];
  if (!p) {
    $('#corp-grid').innerHTML = '<div><p>No corporate rate published for this jurisdiction.</p></div>';
    return;
  }

  const smallCombined = fed.small_business_rate + p.small_business_rate;
  const generalCombined = fed.general_rate + p.general_rate;
  const limit = Math.min(fed.small_business_limit, p.small_business_limit);

  $('#corp-lede').textContent =
    `Combined federal and provincial rates on active business income in ${p.name}.`;

  $('#corp-grid').innerHTML = `
    <div>
      <h3>Small business rate</h3>
      <div class="big">${pct(smallCombined, 1)}</div>
      <p>${pct(fed.small_business_rate, 0)} federal plus ${pct(p.small_business_rate, 1)} provincial.</p>
    </div>
    <div>
      <h3>General rate</h3>
      <div class="big">${pct(generalCombined, 1)}</div>
      <p>Above the business limit, or on non-eligible income.</p>
    </div>
    <div>
      <h3>Business limit</h3>
      <div class="big">${money(limit)}</div>
      <p>Shared among associated corporations.</p>
    </div>
    <div>
      <h3>Personal average rate</h3>
      <div class="big">${pct(estimate(currentIncome(), code).avgRate)}</div>
      <p>For comparison, on the income entered above.</p>
    </div>
  `;
}

function renderLimits() {
  const c = D.credits;
  const cells = [
    ['TFSA', money(c.registered_accounts.tfsa.annual_limit), `${money(c.registered_accounts.tfsa.cumulative_room_since_2009)} cumulative room since 2009.`],
    ['RRSP', money(c.registered_accounts.rrsp.annual_limit), '18% of prior-year earned income, up to this cap.'],
    ['FHSA', money(c.registered_accounts.fhsa.annual_limit), `${money(c.registered_accounts.fhsa.lifetime_limit)} lifetime limit.`],
    ['OAS clawback starts', money(c.oas.clawback_threshold), `${pct(c.oas.recovery_rate, 0)} of net income above the threshold.`],
    ['Capital gains inclusion', pct(c.capital_gains.inclusion_rate, 0), 'The proposed increase was cancelled in March 2025.'],
    ['Lifetime capital gains exemption', money(c.capital_gains.lifetime_capital_gains_exemption), 'On qualified small business shares.'],
  ];

  $('#limits-grid').innerHTML = cells
    .map(([h, big, note]) => `<div><h3>${h}</h3><div class="big">${big}</div><p>${note}</p></div>`)
    .join('');
}

/* ---------------- interaction ---------------- */

function currentIncome() {
  const raw = Number($('#income').value);
  return Number.isFinite(raw) && raw >= 0 ? raw : 0;
}

function validate() {
  const el = $('#income');
  const raw = el.value.trim();
  const n = Number(raw);
  let msg = '';

  if (raw === '') msg = 'Enter an amount.';
  else if (!Number.isFinite(n)) msg = 'Enter a number.';
  else if (n < 0) msg = 'Income cannot be negative.';
  else if (n > 10000000) msg = 'Enter an amount up to $10,000,000.';

  $('#income-err').textContent = msg;
  el.setAttribute('aria-invalid', msg ? 'true' : 'false');
  return msg === '';
}

function update() {
  if (!validate()) return;
  const income = currentIncome();
  const code = $('#province').value;

  renderResult(estimate(income, code));
  renderComparison(income, code);
  renderSales(code);
  renderCorporate(code);

  const url = new URL(location.href);
  url.searchParams.set('income', String(income));
  url.searchParams.set('province', code);
  history.replaceState(null, '', url);
}

function wire() {
  const income = $('#income');
  const range = $('#income-range');
  const province = $('#province');

  province.innerHTML = Object.entries(D.income.provinces)
    .map(([code, p]) => `<option value="${code}">${p.name}</option>`)
    .join('');

  const params = new URLSearchParams(location.search);
  const qIncome = Number(params.get('income'));
  if (Number.isFinite(qIncome) && qIncome >= 0 && qIncome <= 10000000) {
    income.value = String(qIncome);
  }
  const qProv = (params.get('province') || '').toUpperCase();
  if (D.income.provinces[qProv]) province.value = qProv;
  else province.value = 'ON';

  range.value = String(Math.min(Number(income.value), Number(range.max)));

  income.addEventListener('input', () => {
    range.value = String(Math.min(currentIncome(), Number(range.max)));
    update();
  });

  range.addEventListener('input', () => {
    income.value = range.value;
    update();
  });

  province.addEventListener('change', update);

  document.querySelectorAll('#cmp thead button').forEach((b) => {
    b.addEventListener('click', () => {
      const key = b.dataset.sort;
      if (key === sortKey) sortDir *= -1;
      else { sortKey = key; sortDir = key === 'name' ? 1 : -1; }
      renderComparison(currentIncome(), province.value);
    });
  });

  $('#form').addEventListener('submit', (e) => e.preventDefault());
}

function wireTheme() {
  const btn = $('#theme-toggle');
  const order = ['', 'light', 'dark'];
  const label = { '': 'system', light: 'light', dark: 'dark' };

  let saved = '';
  try { saved = localStorage.getItem('ct-theme') || ''; } catch { saved = ''; }
  if (!order.includes(saved)) saved = '';

  const apply = (v) => {
    document.documentElement.setAttribute('data-theme', v);
    btn.textContent = `Theme: ${label[v]}`;
    try { localStorage.setItem('ct-theme', v); } catch { /* storage blocked */ }
  };

  apply(saved);

  btn.addEventListener('click', () => {
    const next = order[(order.indexOf(document.documentElement.getAttribute('data-theme') || '') + 1) % order.length];
    apply(next);
  });
}

/* ---------------- boot ---------------- */

async function boot() {
  wireTheme();

  try {
    const entries = await Promise.all(
      Object.entries(FILES).map(async ([key, file]) => {
        const res = await fetch(DATA + file);
        if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`);
        return [key, await res.json()];
      })
    );
    D = Object.fromEntries(entries);
  } catch (err) {
    $('#boot-msg').textContent = `Could not read the dataset: ${err.message}`;
    $('#boot').hidden = false;
    return;
  }

  $('#app').hidden = false;
  wire();
  renderLimits();
  update();
}

boot();
