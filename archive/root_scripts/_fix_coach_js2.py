#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rewrite the first script block in coach.html to add DOMContentLoaded wrapper."""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'c:\Users\Victor\Desktop\Новая папка (2)\templates\prep\coach.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Find the opening <script> tag that starts with the greeting code
# (after the style block)
marker = '// \u2500\u2500\u2500 Dynamic greeting via API'
script_start = html.find('<script>\n\n' + marker[:20])
if script_start < 0:
    script_start = html.find('<script>\n' + marker[:5])

print(f'script_start: {script_start}')

# Find the closing </script> before Chart.js
chart_marker = '<!-- Chart.js for Radar Chart -->'
script_end = html.find('</script>\n\n' + chart_marker)
if script_end < 0:
    script_end = html.find('</script>\n' + chart_marker[:10])
print(f'script_end: {script_end}')

if script_start < 0 or script_end < 0:
    print('Could not find script boundaries!')
    sys.exit(1)

# Extract the old script block (including <script> and </script>)
old_script_block = html[script_start:script_end + len('</script>')]
print(f'Old block length: {len(old_script_block)}')

# Build new script block
new_script_block = '''<script>
console.log('[coach] inline script loaded...');
document.addEventListener('DOMContentLoaded', function() {
console.log('[coach] DOMContentLoaded fired');

// ---- Dynamic greeting via API --------------------------------------------------
var greetingEl = document.getElementById('greetingMsg');
var ctaRow = document.getElementById('ctaRow');
console.log('[coach] greetingEl:', greetingEl, 'ctaRow:', ctaRow);

function addCtaButton(text, href, cls) {
  if (!text || !href) return;
  var a = document.createElement('a');
  a.className = 'cta-btn' + (cls ? ' ' + cls : '');
  a.href = href;
  a.textContent = text;
  ctaRow.appendChild(a);
}

function addCtaAction(text, actionFn, cls) {
  if (!text) return;
  var btn = document.createElement('button');
  btn.className = 'cta-btn' + (cls ? ' ' + cls : '');
  btn.textContent = text;
  btn.addEventListener('click', actionFn);
  ctaRow.appendChild(btn);
}

var greetingController = new AbortController();
var greetingTimeout = setTimeout(function () { greetingController.abort(); }, 10000);
var greetingUrl = '{{ url_for("prep.coach_greeting") }}' + '?_t=' + Date.now();
console.log('[coach] fetching greeting from:', greetingUrl);
fetch(greetingUrl, { signal: greetingController.signal })
  .then(function (r) { clearTimeout(greetingTimeout); return r.json(); })
  .then(function (data) {
    console.log('[coach] greeting data, scenario:', data.scenario);
    greetingEl.innerHTML = data.greeting || ' Привет! Я твой ИИ-куратор FORMYLA.';
    ctaRow.innerHTML = '';
    // Render CTA buttons based on scenario
    if (data.scenario === 'need_grade') {
      addCtaButton(' Выбрать класс', '/profile', '');
    } else if (data.scenario === 'test_in_progress') {
      // Diagnostic test already running — hide greeting, focus input
      greetingEl.style.display = 'none';
      ctaRow.style.display = 'none';
      var input = document.getElementById('chatInput');
      if (input) input.focus();
    } else if (data.scenario === 'onboarding_test') {
      // Кнопка "Начать диагностику (21 задача)" — inline в чате
      addCtaAction(' Начать диагностику (21 задача)', function () {
        ctaRow.innerHTML = '';
        greetingEl.innerHTML = '⏳ Загружаю диагностические задачи…';
        // Start test via API — returns first task as a chat message
        fetch('{{ url_for("prep.coach_test_start") }}', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.reply) {
              // Hide greeting, show first task as bot message
              greetingEl.style.display = 'none';
              addMsg(data.reply, 'bot');
              // Focus chat input
              var input = document.getElementById('chatInput');
              if (input) input.focus();
            } else {
              greetingEl.innerHTML = '[ERROR] ' + (data.reply || 'Не удалось начать диагностику.');
            }
          })
          .catch(function () { greetingEl.innerHTML = '[ERROR] Ошибка соединения. Попробуй ещё раз.'; });
      }, '');
    } else if (data.scenario === 'daily_test') {
      addCtaAction(' Пройти тест по теме', function () {
        var subtopicKey = data.priority_subtopic ? data.priority_subtopic.key : '';
        var subtopicName = data.priority_subtopic ? data.priority_subtopic.name : 'математике';
        greetingEl.innerHTML = '⏳ Загружаю тест по теме <strong>' + subtopicName + '</strong>…';
        ctaRow.innerHTML = '';
        // Fetch subtopic test tasks from onboarding endpoint (reuse)
        fetch('{{ url_for("prep.coach_greeting") }}?action=subtopic_test&subtopic_key=' + subtopicKey)
          .then(function (r) { return r.json(); })
          .then(function (taskData) {
            if (taskData.tasks && taskData.tasks.length) {
              var html = '<div style="max-height:350px;overflow-y:auto;">';
              html += '<p><strong>Тест по теме «' + subtopicName + '»:</strong></p>';
              taskData.tasks.forEach(function (t, i) {
                html += '<div style="margin:8px 0;padding:8px;border:1px solid rgba(255,255,255,0.1);border-radius:8px;">';
                html += '<p><strong>Задача ' + (i+1) + ':</strong> ' + t.task_text + '</p>';
                html += '<div><button class="cta-btn" data-task="' + t.id + '" data-score="1">[OK] Правильно</button> ';
                html += '<button class="cta-btn secondary" data-task="' + t.id + '" data-score="0">[ERROR] Неверно</button></div>';
                html += '</div>';
              });
              html += '<div style="margin-top:12px;"><button class="cta-btn" id="finishDailyTest"> Завершить тест</button></div>';
              html += '</div>';
              greetingEl.innerHTML = html;
              document.getElementById('finishDailyTest').addEventListener('click', function () {
                var results = {};
                document.querySelectorAll('[data-task]').forEach(function (btn) {
                  var taskId = btn.getAttribute('data-task');
                  if (btn.classList.contains('cta-btn') && !btn.classList.contains('secondary')) {
                    results[taskId] = 1;
                  } else if (btn.classList.contains('secondary')) {
                    if (!results[taskId]) results[taskId] = 0;
                  }
                });
                fetch('{{ url_for("prep.coach_daily_submit") }}', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ subtopic_key: subtopicKey, results: results })
                })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                  if (res.status === 'ok') {
                    var msg = ' Уровень: ' + res.level + ' (окно ' + res.min_level + '–' + res.max_level + '). Всего ' + res.total_count + ' задач на сегодня.';
                    greetingEl.innerHTML = msg;
                    ctaRow.innerHTML = '';
                    addCtaAction(' Начать задачи дня', function () {
                      window.location.reload();
                    }, '');
                  } else {
                    greetingEl.innerHTML = '[ERROR] Ошибка: ' + (res.error || 'попробуй ещё раз');
                  }
                });
              });
            } else {
              greetingEl.innerHTML = ' Нет задач по этой теме. Попробуй другую.';
            }
          });
      }, '');
    } else if (data.scenario === 'daily_tasks_ready') {
      addCtaAction(' Продолжить задачи дня', function () {
        // Navigate to daily tasks page
        window.location.href = '/daily-tasks';
      }, '');
    } else if (data.scenario === 'day_summary') {
      if (data.cta_url && data.cta_text) {
        addCtaButton(data.cta_text, data.cta_url, '');
      }
      addCtaButton(' Профиль', '/profile', 'secondary');
    } else if (data.scenario === 'recommend_olympiad' || data.scenario === 'need_test') {
      // Legacy/backward-compatible
      if (data.recommended_olympiad) {
        addCtaButton(' Создать план подготовки', '/prep/new?olympiad=' + data.recommended_olympiad.slug, '');
        addCtaButton(' Другие олимпиады', '/prep/new', 'secondary');
      } else if (data.cta_url) {
        addCtaButton(data.cta_text || 'Далее', data.cta_url, '');
      } else {
        addCtaButton(' Создать план подготовки', '/prep/new', '');
      }

    // ── Monthly prep cycle scenarios ──────────────────────────────────
    } else if (data.scenario === 'prep_morning_test') {
      // Test day (days 1–7), test NOT taken yet -> offer inline test
      var prepInfo = data.prep_info || {};
      var topicTitle = prepInfo.subtopic_title || '';
      var remaining = prepInfo.remaining_tests || 0;
      addCtaAction(' Начать тест: «' + topicTitle + '»', function () {
        ctaRow.innerHTML = '';
        greetingEl.innerHTML = '⏳ Загружаю тест по теме <strong>' + topicTitle + '</strong>…';
        fetch('{{ url_for("prep.coach_greeting") }}?action=prep_test_tasks')
          .then(function (r) { return r.json(); })
          .then(function (taskData) {
            if (taskData.tasks && taskData.tasks.length) {
              var html = '<div style="max-height:350px;overflow-y:auto;">';
              html += '<p><strong> Тест по теме «' + (taskData.subtopic_title || topicTitle) + '»</strong></p>';
              html += '<p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">Отметь правильность каждой задачи (5 задач):</p>';
              taskData.tasks.forEach(function (t, i) {
                html += '<div style="margin:8px 0;padding:8px;border:1px solid rgba(255,255,255,0.1);border-radius:8px;">';
                html += '<p><strong>Задача ' + (i+1) + ':</strong> ' + (t.task_text || t.text || '') + '</p>';
                html += '<div><button class="cta-btn" data-task="' + t.id + '" data-score="1">[OK] Правильно</button> ';
                html += '<button class="cta-btn secondary" data-task="' + t.id + '" data-score="0">[ERROR] Неверно</button></div>';
                html += '</div>';
              });
              html += '<div style="margin-top:12px;"><button class="cta-btn" id="finishPrepTest"> Завершить тест</button></div>';
              html += '</div>';
              greetingEl.innerHTML = html;
              document.getElementById('finishPrepTest').addEventListener('click', function () {
                var results = {};
                document.querySelectorAll('[data-task]').forEach(function (btn) {
                  var taskId = btn.getAttribute('data-task');
                  if (!taskId) return;
                  if (btn.classList.contains('cta-btn') && !btn.classList.contains('secondary')) {
                    results[taskId] = 1;
                  } else if (btn.classList.contains('secondary')) {
                    if (!results[taskId]) results[taskId] = 0;
                  }
                });
                greetingEl.innerHTML = '⏳ Отправляю результаты теста…';
                fetch('{{ url_for("prep.coach_prep_submit_test") }}', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ results: results })
                })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                  if (res.status === 'ok') {
                    var msg = '[OK] <strong>Тест завершён!</strong><br>';
                    msg += 'Правильно: ' + res.correct + ' из ' + res.total + '<br>';
                    msg += ' Уровень: ' + res.level + '/8.';
                    if (res.generation_queued) {
                      msg += '<br><br> Задачи дня уже готовятся под твой уровень. Они придут вечером!';
                    }
                    greetingEl.innerHTML = msg;
                    ctaRow.innerHTML = '';
                    if (res.generation_queued) {
                      addCtaButton(' Перейти к задачам дня', '/daily-tasks', '');
                    }
                    addCtaButton(' Пройти адапт тест', '/adaptive-test', 'secondary');
                  } else {
                    greetingEl.innerHTML = '[ERROR] Ошибка: ' + (res.error || 'попробуй ещё раз');
                  }
                });
              });
            } else {
              greetingEl.innerHTML = ' Нет задач для теста. Попробуй позже.';
              ctaRow.innerHTML = '';
              ctaRow.style.display = 'none';
            }
          });
      }, '');
    } else if (data.scenario === 'prep_tasks_ready') {
      // Training day (days 8–30), tasks already generated
      if (data.cta_url && data.cta_text) {
        addCtaButton(data.cta_text, data.cta_url, '');
      }
      addCtaButton(' Пройти адапт тест', '/adaptive-test', 'secondary');

    } else if (data.scenario === 'prep_task_day') {
      // Training day, tasks not ready yet — waiting for evening cron
      if (data.cta_url && data.cta_text) {
        addCtaButton(data.cta_text, data.cta_url, '');
      }
      addCtaButton(' Пройти адапт тест', '/adaptive-test', 'secondary');

    } else if (data.scenario === 'prep_month_complete') {
      // Месяц завершён — показать следующие подтемы и CTA для старта нового месяца
      if (data.cta_url && data.cta_text) {
        addCtaButton(data.cta_text, data.cta_url, '');
      }
      addCtaButton(' Пройти адапт тест', '/adaptive-test', 'secondary');
    }
    if (ctaRow.children.length) {
      ctaRow.style.display = 'flex';
    } else {
      ctaRow.style.display = 'none';
    }
  })
  .catch(function () {
    console.log('[coach] greeting fetch failed, using fallback');
    greetingEl.textContent = ' Привет! Я твой ИИ-куратор FORMYLA. Задай мне вопрос!';
  });

}); // end DOMContentLoaded
</script>'''

html = html[:script_start] + new_script_block + html[script_end + len('</script>'):]

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'OK - replaced script block ({len(old_script_block)} -> {len(new_script_block)} chars)')
print('File saved successfully')
