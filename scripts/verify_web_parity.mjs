/* Verify the browser tax engine agrees with examples/income_tax_calculator.py.
   Run: node scripts/verify_web_parity.mjs
   Exits non-zero on any disagreement above one cent. */

import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const { estimate } = require(join(root, 'web/tax.js'));

const read = (f) => JSON.parse(readFileSync(join(root, 'data/json', f), 'utf8'));
const data = {
  income: read('personal_income_tax_2026.json'),
  payroll: read('payroll_contributions_2026.json'),
};

const INCOMES = [0, 15000, 30000, 55000, 74600, 85000, 90000, 120000, 181440, 250000, 400000, 1000000];
const CODES = Object.keys(data.income.provinces);

/* Parse the CLI's human-readable output back into numbers. */
function fromPython(income, code) {
  const out = execFileSync('python3', [join(root, 'examples/income_tax_calculator.py'), String(income), code], { encoding: 'utf8' });
  const num = (label) => {
    const m = out.match(new RegExp(label + String.raw`:\s+\$\s*([\d,]+\.\d{2})`));
    return m ? Number(m[1].replace(/,/g, '')) : null;
  };
  return {
    fedTax: num('Federal income tax'),
    provTax: num('Provincial income tax'),
    total: num('Total deductions'),
    keep: num('After-tax income'),
  };
}

let checked = 0;
let failed = 0;

for (const code of CODES) {
  for (const income of INCOMES) {
    if (income === 0) continue; // the CLI divides by income for the average rate
    const js = estimate(income, code, data);
    const py = fromPython(income, code);

    for (const key of ['fedTax', 'provTax', 'total', 'keep']) {
      checked++;
      const diff = Math.abs(js[key] - py[key]);
      if (diff > 0.01) {
        failed++;
        console.error(
          `MISMATCH ${code} @ ${income} ${key}: js=${js[key].toFixed(2)} py=${py[key].toFixed(2)} diff=${diff.toFixed(4)}`
        );
      }
    }
  }
}

console.log(`${checked} figures compared across ${CODES.length} jurisdictions and ${INCOMES.length - 1} income levels.`);
if (failed) {
  console.error(`${failed} mismatches.`);
  process.exit(1);
}
console.log('Browser engine matches the Python calculator exactly.');
