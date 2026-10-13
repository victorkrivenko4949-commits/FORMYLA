/* method_week.js — блоки «Куратор: план на сегодня» и «Метод недели» на странице задач дня.
   Вставляется автоматически (method_week/ui_inject.py) только для тестовых аккаунтов.
   LaTeX рендерится через KaTeX, если на странице есть renderMathInElement. */
(function () {
  'use strict';
  var root = document.getElementById('mw-root');
  if (!root) return;

  var css = document.createElement('style');
  css.textContent = [
    '.mw-card{max-width:960px;margin:18px auto;padding:18px 20px;border-radius:14px;background:#fff;box-shadow:0 2px 12px rgba(0,0,0,.06);line-height:1.5}',
    '.mw-card h3{margin:0 0 10px;font-size:18px}',
    '.mw-badge{display:inline-block;padding:2px 8px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12px;margin-left:8px}',
    '.mw-muted{color:#6b7280;font-size:14px}',
    '.mw-lesson{background:#f9fafb;border-radius:10px;padding:12px 14px;margin:10px 0}',
    '.mw-lesson h3{font-size:15px;margin:10px 0 4px}',
    '.mw-task{border:1px solid #e5e7eb;border-radius:10px;padding:12px;margin:10px 0}',
    '.mw-task textarea,.mw-task input{width:100%;box-sizing:border-box;margin-top:6px;padding:8px;border:1px solid #d1d5db;border-radius:8px;font:inherit}',
    '.mw-btn{margin-top:8px;padding:8px 14px;border:0;border-radius:8px;background:#4f46e5;color:#fff;cursor:pointer}',
    '.mw-btn.sec{background:#e5e7eb;color:#111;margin-left:6px}',
    '.mw-ok{color:#15803d}.mw-bad{color:#b91c1c}',
    '.mw-plan li{margin:2px 0}',
    '.mw-progress{height:8px;background:#e5e7eb;border-radius:999px;overflow:hidden;margin:8px 0}',
    '.mw-progress>div{height:100%;background:#4f46e5;transition:width .4s}'
  ].join('\n');
  document.head.appendChild(css);

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[c]; }); }
  function md(s) {
    var lines = esc(s).split('\n'), out = [], inList = false;
    lines.forEach(function (ln) {
      var m;
      if ((m = ln.match(/^###\s+(.*)/))) { if (inList) { out.push('</ul>'); inList = false; } out.push('<h3>' + m[1] + '</h3>'); return; }
      if ((m = ln.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/))) { if (!inList) { out.push('<ul>'); inList = true; } out.push('<li>' + m[1] + '</li>'); return; }
      if (inList) { out.push('</ul>'); inList = false; }
      if (ln.trim()) out.push('<p>' + ln + '</p>');
    });
    if (inList) out.push('</ul>');
    return out.join('').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  }
  function katex(el) {
    try {
      if (window.renderMathInElement) {
        window.renderMathInElement(el, {delimiters: [{left: '$$', right: '$$', display: true}, {left: '$', right: '$', display: false}], throwOnError: false});
      }
    } catch (e) {}
  }
  function getJSON(url, opts) {
    return fetch(url, Object.assign({credentials: 'same-origin', headers: {'Accept': 'application/json', 'Content-Type': 'application/json'}}, opts || {}))
      .then(function (r) { return r.json().then(function (j) { j.__status = r.status; return j; }); });
  }

  var anchor = document.querySelector('[data-mw-anchor]') || document.querySelector('main') || document.body;
  var wrap = document.createElement('div');
  wrap.id = 'mw-wrap';
  anchor.insertBefore(wrap, anchor.firstChild);

  var curatorCard = document.createElement('div'); curatorCard.className = 'mw-card';
  var methodCard = document.createElement('div'); methodCard.className = 'mw-card';
  wrap.appendChild(curatorCard); wrap.appendChild(methodCard);

  function paywallHtml(title, d) {
    return '<h3>' + title + '</h3><p class="mw-muted">Доступно по подписке Premium. <a href="' + esc(d.upgrade_url || '/subscribe') + '">Оформить</a></p>';
  }

  /* ── Куратор ─────────────────────────────────────────── */
  getJSON('/method_week/api/curator_plan').then(function (d) {
    if (d.__status === 404) { curatorCard.style.display = 'none'; return; }
    if (d.__status === 402) { curatorCard.innerHTML = paywallHtml('Куратор', d); return; }
    var daily = d.daily || {}, month = d.month || {};
    var html = '<h3>Куратор — ' + esc(daily.date || '') + '</h3>';
    html += '<p>' + (daily.status_lines || []).map(esc).join(' ') + '</p>';
    (daily.plan_lines || []).forEach(function (ln, i) { html += '<p>' + (i === 0 ? '<b>' + esc(ln) + '</b>' : esc(ln)) + '</p>'; });
    if ((month.methods || []).length) {
      html += '<p class="mw-muted">План методов на ' + esc(month.month) + ' (выбран куратором по твоим результатам):</p><ol class="mw-plan">';
      month.methods.forEach(function (m, i) {
        var cur = (i === month.current_week);
        html += '<li>' + (cur ? '<b>' : '') + esc(m.code) + ' «' + esc(m.name) + '»' + (cur ? '</b> — эта неделя' : '') +
          (m.reason ? ' <span class="mw-muted">(' + esc(m.reason) + ')</span>' : '') + '</li>';
      });
      html += '</ol>';
    }
    curatorCard.innerHTML = html;
  }).catch(function () { curatorCard.style.display = 'none'; });

  /* ── Метод недели ────────────────────────────────────── */
  var pollTimer = null;
  function renderMethod(d) {
    if (d.__status === 404) { methodCard.style.display = 'none'; return; }
    if (d.__status === 402) { methodCard.innerHTML = paywallHtml('Метод недели', d); return; }
    if (d.status === 'no_plan') { methodCard.innerHTML = '<h3>Метод недели</h3><p class="mw-muted">' + esc(d.message) + '</p>'; return; }
    if (d.status === 'generating') {
      methodCard.innerHTML = '<h3>Метод недели: ' + esc(d.method_code) + ' «' + esc(d.method_name) + '»<span class="mw-badge">готовим</span></h3>' +
        '<div class="mw-progress"><div style="width:' + (d.progress_pct || 3) + '%"></div></div>' +
        '<p class="mw-muted">deepseek-v4-pro (thinking) пишет разбор, составляет 3 задачи и сам решает их для проверки. Обычно 2–6 минут. Шаг: ' + esc(d.current_step || '') + '</p>';
      clearTimeout(pollTimer);
      pollTimer = setTimeout(function () { getJSON('/method_week/api/today').then(renderMethod); }, 7000);
      return;
    }
    if (d.status === 'failed') { methodCard.innerHTML = '<h3>Метод недели</h3><p class="mw-bad">Не удалось подготовить: ' + esc(d.error || '') + '</p>'; return; }
    if (d.status !== 'ready') { methodCard.innerHTML = '<h3>Метод недели</h3><p class="mw-muted">' + esc(d.message || 'временно недоступен') + '</p>'; return; }

    var html = '<h3>Метод недели: ' + esc(d.method_code) + ' «' + esc(d.method_name) + '»<span class="mw-badge">' + d.progress.completed + '/' + d.progress.total + '</span></h3>';
    html += '<details open class="mw-lesson"><summary><b>Разбор метода</b></summary>' + md(d.lesson_md || '') + '</details>';
    (d.tasks || []).forEach(function (t) {
      html += '<div class="mw-task" data-pos="' + t.position + '"><b>Задача ' + t.position + '</b>' +
        (t.difficulty ? '<span class="mw-badge">сложность ' + esc(t.difficulty) + '</span>' : '') +
        '<div class="mw-stmt">' + md(t.statement) + '</div>';
      if (t.is_answered) {
        html += '<p class="' + (t.is_correct ? 'mw-ok' : 'mw-bad') + '">' + (t.is_correct ? 'Верно' : 'Неверно') + '. Твой ответ: ' + esc(t.user_answer) + '</p>' +
          (t.ai_feedback ? '<div>' + md(t.ai_feedback) + '</div>' : '') +
          '<details><summary>Решение</summary><div>' + md(t.solution || '') + '</div><p><b>Ответ:</b> ' + esc(t.correct_answer) + '</p></details>';
      } else {
        html += '<input class="mw-ans" placeholder="Ответ"><textarea class="mw-sol" rows="3" placeholder="Кратко опиши решение (обязательно)"></textarea>' +
          '<button class="mw-btn mw-submit">Проверить</button><button class="mw-btn sec mw-hint" data-n="1">Подсказка</button><div class="mw-res"></div>';
      }
      html += '</div>';
    });
    methodCard.innerHTML = html;
    katex(methodCard);

    methodCard.querySelectorAll('.mw-task').forEach(function (box) {
      var pos = box.getAttribute('data-pos');
      var btn = box.querySelector('.mw-submit'), hint = box.querySelector('.mw-hint');
      if (hint) hint.addEventListener('click', function () {
        var n = parseInt(hint.getAttribute('data-n'), 10) || 1;
        getJSON('/method_week/api/' + pos + '/hint?n=' + n).then(function (h) {
          var res = box.querySelector('.mw-res');
          res.innerHTML = '<p class="mw-muted">Подсказка ' + n + ': ' + esc(h.hint || h.message) + '</p>';
          katex(res);
          if (h.total && n < h.total) hint.setAttribute('data-n', String(n + 1));
        });
      });
      if (btn) btn.addEventListener('click', function () {
        var ans = box.querySelector('.mw-ans').value.trim(), sol = box.querySelector('.mw-sol').value.trim();
        var res = box.querySelector('.mw-res');
        if (!ans) { res.innerHTML = '<p class="mw-bad">Введи ответ.</p>'; return; }
        if (!sol) { res.innerHTML = '<p class="mw-bad">Опиши решение — проверяется ход, а не только ответ.</p>'; return; }
        btn.disabled = true; btn.textContent = 'Проверяем…';
        getJSON('/method_week/api/' + pos + '/submit', {method: 'POST', body: JSON.stringify({user_answer: ans, user_solution: sol})}).then(function (r) {
          btn.disabled = false; btn.textContent = 'Проверить';
          if (r.status === 'error') { res.innerHTML = '<p class="mw-bad">' + esc(r.message || r.error) + '</p>'; return; }
          getJSON('/method_week/api/today').then(renderMethod);
        }).catch(function () { btn.disabled = false; btn.textContent = 'Проверить'; res.innerHTML = '<p class="mw-bad">Ошибка сети.</p>'; });
      });
    });
  }
  getJSON('/method_week/api/today').then(renderMethod).catch(function () { methodCard.style.display = 'none'; });
})();
