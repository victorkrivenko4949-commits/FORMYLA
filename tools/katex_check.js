// Проверка всех формул в JSON-файлах каталога через реальный KaTeX.
// Использование: node check_latex.js <file.json> ...
const katex = require('katex');
const fs = require('fs');

// те же macros, что в static/js/olympiad_latex.js и templates/base.html
const MACROS = {
  '\\N': '\\mathbb{N}', '\\Z': '\\mathbb{Z}', '\\Q': '\\mathbb{Q}', '\\R': '\\mathbb{R}',
  '\\floor': '\\left\\lfloor #1 \\right\\rfloor',
  '\\ceil':  '\\left\\lceil #1 \\right\\rceil',
  '\\abs':   '\\left| #1 \\right|'
};

function extractMath(text) {
  // $$...$$, \[...\], \(...\), $...$
  const out = [];
  const re = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$(?!\$)([^$\n]+?)\$/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const expr = m[1] ?? m[2] ?? m[3] ?? m[4];
    if (expr !== undefined) out.push(expr);
  }
  return out;
}

function splitDollars(text) {
  // возвращаем текст с вырезанными $$..$$ и $..$, чтобы проверить парность отдельно
  return text.replace(/\$\$[\s\S]+?\$\$/g, '').replace(/\$(?!\$)[^$\n]+?\$/g, '');
}

let totalBad = 0, totalFormulas = 0;
for (const f of process.argv.slice(2)) {
  const data = JSON.parse(fs.readFileSync(f, 'utf8'));
  const items = Array.isArray(data) ? data : [];
  const bad = [];
  for (const t of items) {
    const sol = typeof t.solution === 'string' ? t.solution : '';
    if (!sol) continue;
    const rest = splitDollars(sol);
    if (rest.includes('$')) bad.push([t.uid, 'ODD_DOLLAR', sol.slice(0, 60)]);
    const formulas = extractMath(sol);
    for (const expr of formulas) {
      totalFormulas++;
      try {
        katex.renderToString(expr, { throwOnError: true, strict: false, trust: true, macros: { ...MACROS } });
      } catch (e) {
        bad.push([t.uid, String(e.message).split('\n')[0].slice(0, 100), expr.slice(0, 60)]);
      }
    }
  }
  if (bad.length) {
    console.log('== ' + f + ' : ' + bad.length + ' ошибок');
    for (const [uid, msg, frag] of bad.slice(0, 15)) console.log('  ' + uid.slice(0, 12) + ' | ' + msg + ' | ' + frag.replace(/\n/g, ' '));
    if (bad.length > 15) console.log('  ... и ещё ' + (bad.length - 15));
    totalBad += bad.length;
  }
}
console.log('TOTAL formulas: ' + totalFormulas + ', errors: ' + totalBad);
