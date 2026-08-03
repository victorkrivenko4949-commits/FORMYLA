/**
 * Reusable "Поделиться с другом" widget for FORMYLA.
 *
 * Usage: anywhere on a task page place a button like:
 *   <button class="share-friend-btn"
 *           data-task-id="123"
 *           data-task-source="adaptive"
 *           data-task-topic="Алгебра"
 *           data-task-grade="9"
 *           data-task-difficulty="4"
 *           data-task-url="/adaptive_task/123"
 *           data-task-preview="Найдите все натуральные ...">
 *      Поделиться с другом
 *   </button>
 *
 * The script auto-binds .share-friend-btn elements after DOMContentLoaded.
 * You can also call window.shareTaskWithFriend({...}) manually.
 */
(function(){
  'use strict';

  const ENDPOINT_FRIENDS = '/api/social/friends/list';
  const ENDPOINT_SEND = (fid) => `/api/chat/${fid}/send`;

  let modalEl = null;
  let currentTask = null;
  let selectedFriendIds = new Set();
  let friendsCache = null;

  function ensureModal(){
    if (modalEl) return modalEl;
    const el = document.createElement('div');
    el.id = 'shareFriendOverlay';
    el.style.cssText = 'position:fixed;inset:0;z-index:11000;background:rgba(0,0,0,0.7);backdrop-filter:blur(6px);display:none;align-items:center;justify-content:center;padding:20px;';
    el.innerHTML = `
      <div style="background:#1e293b;border:1px solid rgba(255,255,255,.08);border-radius:16px;max-width:480px;width:100%;max-height:85vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.5);">
        <div style="padding:18px 20px;border-bottom:1px solid rgba(255,255,255,.06);display:flex;align-items:center;justify-content:space-between;">
          <h3 style="margin:0;color:#f1f5f9;font-size:1.05em;"> Поделиться с другом</h3>
          <button id="sfClose" style="background:none;border:none;color:#94a3b8;font-size:1.4em;cursor:pointer;">×</button>
        </div>
        <div style="padding:10px 16px;border-bottom:1px solid rgba(255,255,255,.06);">
          <input id="sfSearch" placeholder="Поиск друга…" autocomplete="off"
                 style="width:100%;padding:8px 12px;background:rgba(15,23,42,.65);border:1px solid rgba(255,255,255,.08);border-radius:10px;color:#e5e7eb;font-size:14px;outline:none;">
        </div>
        <div id="sfList" style="overflow-y:auto;flex:1;padding:8px 12px;"></div>
        <div style="border-top:1px solid rgba(255,255,255,.06);padding:12px 16px;display:flex;flex-direction:column;gap:8px;">
          <input id="sfNote" placeholder="Комментарий (необязательно)…"
                 style="padding:8px 12px;background:rgba(15,23,42,.65);border:1px solid rgba(255,255,255,.08);border-radius:10px;color:#e5e7eb;font-size:13px;outline:none;">
          <button id="sfSend" disabled
                  style="padding:10px 16px;background:linear-gradient(135deg,#4aa8ff,#8b5cf6);color:#fff;border:none;border-radius:10px;font-weight:600;cursor:pointer;opacity:.5;">
            Отправить выбранным (0)
          </button>
        </div>
      </div>`;
    document.body.appendChild(el);

    el.addEventListener('click', (e) => { if (e.target === el) close(); });
    el.querySelector('#sfClose').onclick = close;
    el.querySelector('#sfSearch').addEventListener('input', filterList);
    el.querySelector('#sfSend').onclick = sendToSelected;

    modalEl = el;
    return el;
  }

  function escHtml(s){
    return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  async function loadFriends(){
    if (friendsCache) return friendsCache;
    try{
      const r = await fetch(ENDPOINT_FRIENDS);
      const data = await r.json();
      if (data && data.success){
        friendsCache = data.friends || [];
        return friendsCache;
      }
      return [];
    }catch(e){
      console.error('share_with_friend: friends load failed', e);
      return [];
    }
  }

  function renderList(friends){
    const box = modalEl.querySelector('#sfList');
    if (!friends.length){
      box.innerHTML = `<div style="padding:30px 12px;color:#94a3b8;text-align:center;font-size:.9em;">
        У вас пока нет друзей.<br><a href="/friends" style="color:#8b5cf6;">Добавить друзей -></a>
      </div>`;
      return;
    }
    box.innerHTML = '';
    for (const f of friends){
      const row = document.createElement('div');
      row.dataset.fid = f.id;
      row.dataset.name = (f.name || f.nickname || f.email || '').toLowerCase();
      row.style.cssText = 'display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;cursor:pointer;transition:background .12s;';
      const checked = selectedFriendIds.has(f.id);
      row.innerHTML = `
        <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#4aa8ff,#8b5cf6);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;overflow:hidden;flex-shrink:0;">
          ${f.avatar_url ? `<img src="${escHtml(f.avatar_url)}" alt="" style="width:100%;height:100%;object-fit:cover;">` : escHtml((f.name||f.nickname||f.email||'?')[0].toUpperCase())}
        </div>
        <div style="flex:1;min-width:0;">
          <div style="color:#e5e7eb;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(f.name || f.nickname || f.email || 'Без имени')}</div>
          ${f.nickname ? `<div style="color:#94a3b8;font-size:.78em;">@${escHtml(f.nickname)}</div>` : ''}
        </div>
        <input type="checkbox" ${checked?'checked':''} style="width:18px;height:18px;cursor:pointer;accent-color:#8b5cf6;">
      `;
      row.onclick = (e) => {
        if (e.target.tagName !== 'INPUT'){
          const cb = row.querySelector('input[type=checkbox]');
          cb.checked = !cb.checked;
        }
        const cb = row.querySelector('input[type=checkbox]');
        if (cb.checked) selectedFriendIds.add(f.id);
        else selectedFriendIds.delete(f.id);
        updateSendBtn();
        row.style.background = cb.checked ? 'rgba(139,92,246,.12)' : '';
      };
      if (checked) row.style.background = 'rgba(139,92,246,.12)';
      box.appendChild(row);
    }
  }

  function filterList(){
    const q = (modalEl.querySelector('#sfSearch').value || '').toLowerCase().trim();
    modalEl.querySelectorAll('#sfList > div[data-fid]').forEach(row => {
      row.style.display = (!q || row.dataset.name.includes(q)) ? '' : 'none';
    });
  }

  function updateSendBtn(){
    const btn = modalEl.querySelector('#sfSend');
    const n = selectedFriendIds.size;
    btn.disabled = n === 0;
    btn.style.opacity = n === 0 ? '.5' : '1';
    btn.textContent = `Отправить выбранным (${n})`;
  }

  async function sendToSelected(){
    if (!currentTask || !selectedFriendIds.size) return;
    const note = (modalEl.querySelector('#sfNote').value || '').trim();
    const btn = modalEl.querySelector('#sfSend');
    btn.disabled = true;
    btn.textContent = 'Отправка…';

    const ids = Array.from(selectedFriendIds);
    let ok = 0, fail = 0;
    for (const fid of ids){
      try{
        const r = await fetch(ENDPOINT_SEND(fid), {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ kind:'task_share', task: currentTask, note: note }),
        });
        if (r.ok) ok++; else fail++;
      }catch(e){ fail++; }
    }
    if (typeof window.showToast === 'function'){
      window.showToast(
        fail ? `Отправлено ${ok}/${ids.length}` : `Отправлено ${ok} друзьям [OK]`,
        fail ? 'warn' : 'success'
      );
    } else {
      alert(fail ? `Отправлено ${ok}/${ids.length} (часть не доставлена)` : `Задача отправлена ${ok} друзьям [OK]`);
    }
    close();
  }

  function close(){
    if (modalEl) modalEl.style.display = 'none';
    selectedFriendIds.clear();
    currentTask = null;
  }

  async function open(task){
    if (!task) return;
    currentTask = task;
    selectedFriendIds.clear();
    ensureModal();
    modalEl.style.display = 'flex';
    modalEl.querySelector('#sfNote').value = '';
    modalEl.querySelector('#sfSearch').value = '';
    updateSendBtn();
    modalEl.querySelector('#sfList').innerHTML = '<div style="padding:30px;color:#94a3b8;text-align:center;">Загрузка друзей…</div>';
    const friends = await loadFriends();
    renderList(friends);
  }

  function parseTaskFromBtn(btn){
    const ds = btn.dataset || {};
    return {
      id: ds.taskId ? parseInt(ds.taskId, 10) : null,
      source: ds.taskSource || 'task',
      topic: ds.taskTopic || null,
      grade: ds.taskGrade ? parseInt(ds.taskGrade, 10) : null,
      difficulty: ds.taskDifficulty ? parseInt(ds.taskDifficulty, 10) : null,
      url: ds.taskUrl || window.location.pathname,
      preview: ds.taskPreview || null,
    };
  }

  function bindAll(){
    document.querySelectorAll('.share-friend-btn').forEach(btn => {
      if (btn._sfBound) return;
      btn._sfBound = true;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        open(parseTaskFromBtn(btn));
      });
    });
  }

  /**
   * AUTO-INJECT: на страницах задач, где нет явной кнопки .share-friend-btn,
   * добавляем плавающую круглую кнопку (FAB) внизу слева — чтобы поделиться
   * с другом можно было с любой задачи на сайте, без правки шаблона.
   *
   * Эвристика: распознаём task-страницу по URL и/или наличию контейнера с
   * условием задачи в DOM.
   */
  const TASK_URL_PATTERNS = [
    /^\/problem\/\d+/,
    /^\/problems\/\d+/,
    /^\/adaptive_task\/\d+/,
    /^\/adaptive_test_simple(\/|$)/,
    /^\/adaptive_test(\/|$)/,
    /^\/daily\/task\/\d+/,
    /^\/daily(\/|$)/,
    /^\/exam(\/|$)/,
    /^\/free_mock(\/|$)/,
    /^\/olympiad(\/|$)/,
    /^\/secret(\/|$)/,
    /^\/practice(\/|$)/,
    /^\/subtopic(\/|$)/,
    /^\/algebra(\/|$)/,
    /^\/geometry(\/|$)/,
    /^\/number_theory(\/|$)/,
    /^\/combinatorics(\/|$)/,
  ];

  function looksLikeTaskPage(){
    const path = window.location.pathname || '';
    if (TASK_URL_PATTERNS.some(re => re.test(path))) return true;
    // Запасной DOM-эвристик: есть блок с условием задачи
    return !!(document.querySelector('.problem-text, .problem-card, #taskTextBlock, [data-task-text]'));
  }

  function extractTaskFromPage(){
    // Пытаемся вытащить полезные метаданные со страницы
    const path = window.location.pathname || '';

    // 1) ID задачи из URL: /problem/123, /adaptive_task/45, /daily/task/3
    let taskId = null, source = 'task';
    let m;
    if ((m = path.match(/^\/problem(?:s)?\/(\d+)/))){ taskId = +m[1]; source = 'problem'; }
    else if ((m = path.match(/^\/adaptive_task\/(\d+)/))){ taskId = +m[1]; source = 'adaptive'; }
    else if ((m = path.match(/^\/daily\/task\/(\d+)/))){ taskId = +m[1]; source = 'daily'; }
    else if (/^\/olympiad/.test(path)) source = 'olympiad';
    else if (/^\/exam|^\/free_mock/.test(path)) source = 'mock';
    else if (/^\/secret/.test(path)) source = 'secret';

    // 2) Берём текст условия из первого подходящего контейнера
    const containers = [
      '#taskTextBlock',
      '.problem-text',
      '[data-task-text]',
      '.task-text',
      '.olympiad-task-text',
    ];
    let preview = null;
    for (const sel of containers){
      const el = document.querySelector(sel);
      if (el){
        preview = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
        if (preview.length > 280) preview = preview.slice(0, 280) + '…';
        break;
      }
    }
    // Если ничего не нашли — пробуем title страницы
    if (!preview){
      const ti = document.title.replace(/—.*FORMYLA\s*$/i, '').trim();
      if (ti && ti.length > 4) preview = ti;
    }

    return {
      id: taskId,
      source,
      url: path + (window.location.search || ''),
      preview: preview || null,
    };
  }

  function injectFloatingButton(){
    // Не повторяем, если уже добавлена кнопка (явная или плавающая)
    if (document.querySelector('.share-friend-btn, #shareFriendFab')) return;
    if (!looksLikeTaskPage()) return;

    const fab = document.createElement('button');
    fab.id = 'shareFriendFab';
    fab.type = 'button';
    fab.title = 'Поделиться задачей с другом';
    fab.innerHTML = `
      <span style="font-size:18px;line-height:1;"></span>
      <span class="sf-fab-label">Поделиться с другом</span>`;
    fab.style.cssText = [
      'position:fixed',
      'bottom:90px',         // выше нижней навигации/тьютора
      'left:20px',
      'z-index:9500',
      'display:inline-flex',
      'align-items:center',
      'gap:8px',
      'padding:10px 16px',
      'border-radius:999px',
      'background:linear-gradient(135deg,#4aa8ff,#8b5cf6)',
      'color:#fff',
      'border:none',
      'cursor:pointer',
      'font-weight:600',
      'font-size:13px',
      'box-shadow:0 6px 20px rgba(139,92,246,.4)',
      'transition:transform .2s, box-shadow .2s',
    ].join(';');

    fab.onmouseenter = () => {
      fab.style.transform = 'translateY(-2px)';
      fab.style.boxShadow = '0 10px 24px rgba(139,92,246,.55)';
    };
    fab.onmouseleave = () => {
      fab.style.transform = '';
      fab.style.boxShadow = '0 6px 20px rgba(139,92,246,.4)';
    };

    fab.onclick = (e) => {
      e.preventDefault();
      open(extractTaskFromPage());
    };

    // На мобильных делаем компактную версию (только иконка)
    const mobileStyle = document.createElement('style');
    mobileStyle.textContent = `
      @media (max-width: 720px) {
        #shareFriendFab .sf-fab-label { display: none; }
        #shareFriendFab {
          width: 52px; height: 52px;
          padding: 0 !important;
          justify-content: center;
          bottom: 100px !important;
        }
        #shareFriendFab span:first-child { font-size: 22px !important; }
      }
    `;
    document.head.appendChild(mobileStyle);

    document.body.appendChild(fab);
  }

  // Public API
  window.shareTaskWithFriend = open;
  window.rebindShareWithFriend = bindAll;
  window.shareWithFriendInjectFAB = injectFloatingButton;

  function bootstrap(){
    bindAll();
    // На task-страницах добавляем плавающую кнопку «Поделиться» с задержкой,
    // чтобы дать SPA/динамическому контенту подтянуться.
    setTimeout(injectFloatingButton, 200);
    // Повторно после загрузки всех изображений/MathJax — на случай если
    // условие задачи рендерится с задержкой
    setTimeout(() => { bindAll(); injectFloatingButton(); }, 1200);
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
})();
