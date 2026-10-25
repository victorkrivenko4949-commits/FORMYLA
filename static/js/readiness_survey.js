(function () {
  'use strict';
  if (window.ftReadinessLoaded) return;
  window.ftReadinessLoaded = true;
  var checking = false, answered = false, queued = false, token = '';
  var overlay, previousFocus, previousOverflow, waitingTimer;
  var intakePage = /^\/intake(?:\/|$)/.test(location.pathname);

  function check() {
    if (checking || answered || queued || overlay) return;
    checking = true;
    fetch('/api/readiness-survey/pending', {credentials: 'same-origin', cache: 'no-store'})
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) {
        if (data.pending) { token = data.csrf; queued = true; show(); }
      })
      .catch(function () { setTimeout(check, 15000); })
      .finally(function () { checking = false; });
  }

  function show() {
    if (!queued || answered || overlay) return;
    // Do not cover an already visible 25-minute survey.
    if (window.ftFb && window.ftFb.shown) {
      clearTimeout(waitingTimer);
      waitingTimer = setTimeout(show, 300);
      return;
    }
    // CONFIRM_LINK_V1: не накрываем уведомление о запросах учителя/родителя —
    // дождёмся, пока ученик ответит на него, и покажем опрос готовности после.
    var lr = document.getElementById('ft-linkreq-overlay');
    if (lr && lr.style.display === 'flex') {
      clearTimeout(waitingTimer);
      waitingTimer = setTimeout(show, 300);
      return;
    }
    queued = false;
    previousFocus = document.activeElement;
    previousOverflow = document.body.style.overflow;
    overlay = document.createElement('div');
    overlay.id = 'ft-readiness-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:41000;background:rgba(5,8,18,.78);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;';
    overlay.innerHTML = '<form role="dialog" aria-modal="true" aria-labelledby="ft-readiness-title" style="background:var(--card,#141a2e);color:var(--text,#e2e8f0);border:1px solid rgba(244,185,66,.45);border-radius:16px;max-width:440px;width:100%;padding:26px 24px;box-shadow:0 18px 60px rgba(0,0,0,.55);max-height:90vh;overflow:auto;">' +
      '<h2 id="ft-readiness-title" style="font-size:20px;font-weight:800;margin:0 0 12px;">Олимпиады требуют регулярной подготовки. Ты готов заходить каждый день и заниматься?</h2>' +
      '<fieldset style="border:0;padding:0;margin:0;"><legend style="font-size:14px;margin-bottom:10px;">Выбери один вариант</legend>' +
      '<label style="display:block;padding:12px 0;cursor:pointer;"><input type="radio" name="readiness" value="yes" required> Да, готов!</label>' +
      '<label style="display:block;padding:12px 0;cursor:pointer;"><input type="radio" name="readiness" value="try"> Постараюсь, но не обещаю каждый день.</label>' +
      '<label style="display:block;padding:12px 0;cursor:pointer;"><input type="radio" name="readiness" value="not_yet"> Пока не готов.</label></fieldset>' +
      '<p style="font-size:14px;color:var(--muted,#94a3b8);margin:16px 0;">Если есть вопросы, напиши в поддержку — контакты есть на странице <a href="/about" target="_blank" rel="noopener" style="color:#f4b942;">«О сайте»</a>.</p>' +
      '<button type="submit" style="width:100%;padding:12px;border:0;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;background:linear-gradient(135deg,#F4B942,#e09a1f);color:#1a1205;">Отправить</button>' +
      '<p id="ft-readiness-error" role="alert" style="color:#f87171;font-size:13px;margin:10px 0 0;"></p></form>';
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    overlay.querySelector('input').focus();
    overlay.querySelector('form').addEventListener('submit', submit);
    overlay.addEventListener('click', function (event) { event.stopPropagation(); });
    document.addEventListener('keydown', trapFocus, true);
  }

  function trapFocus(event) {
    if (!overlay) return;
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (event.key !== 'Tab') return;
    var nodes = Array.from(overlay.querySelectorAll('input, a, button:not(:disabled)'));
    var first = nodes[0], last = nodes[nodes.length - 1];
    if (event.shiftKey && (document.activeElement === first || !overlay.contains(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !overlay.contains(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  }

  function submit(event) {
    event.preventDefault();
    var selected = overlay.querySelector('input:checked');
    var button = overlay.querySelector('button');
    var error = overlay.querySelector('#ft-readiness-error');
    if (!selected || button.disabled) return;
    button.disabled = true; button.textContent = 'Отправляю...'; error.textContent = '';
    var headers = {'Content-Type': 'application/json', 'X-Readiness-CSRF': token};
    var csrf = document.querySelector('meta[name="csrf-token"]');
    if (csrf) headers['X-CSRFToken'] = csrf.content;
    fetch('/api/readiness-survey', {
      method: 'POST', credentials: 'same-origin', headers: headers,
      body: JSON.stringify({answer: selected.value})
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || !data.ok) throw new Error(data.error || 'Не удалось сохранить ответ. Попробуй ещё раз.');
      });
    }).then(function () {
      answered = true;
      overlay.remove(); overlay = null;
      document.removeEventListener('keydown', trapFocus, true);
      document.body.style.overflow = window.ftFb && window.ftFb.shown ? 'hidden' : previousOverflow;
      if (previousFocus && previousFocus.isConnected && !(window.ftFb && window.ftFb.shown)) previousFocus.focus();
    }).catch(function (err) {
      error.textContent = err.message || 'Ошибка сети. Попробуй ещё раз.';
      button.disabled = false; button.textContent = 'Отправить';
    });
  }

  if (intakePage) {
    var card = document.getElementById('intake-card');
    // The intake page renders its finish screen without navigation.
    // Observe that screen; the server independently rejects skipped/unfinished intake.
    function finished() {
      if (card && card.querySelector('.intake-finish button[onclick="showDailyTasksConfirm()"]')) check();
    }
    if (card) {
      var observer = new MutationObserver(finished);
      observer.observe(card, {childList: true, subtree: true});
      finished();
    }
  } else {
    check();
  }
})();
