/*!
 * FORMYLA — WhatsApp-style emoji picker
 * Self-contained: no dependencies. Public API:
 *   EmojiPicker.attach({ button, target, anchor })
 *     - button: HTMLElement that toggles the picker (e.g.  button)
 *     - target: HTMLTextAreaElement|HTMLInputElement to insert emoji into
 *     - anchor: (optional) element relative to which the popup is positioned;
 *               defaults to `button`.
 *
 *   EmojiPicker.close()    — hide the picker if open
 *
 * Inserts an emoji at the current caret position in `target`, preserves
 * focus and dispatches `input` so any listeners (auto-grow, send-enable)
 * pick up the change.
 */
(function (global) {
  'use strict';

  // Curated WhatsApp-style groups.
  var GROUPS = [
    {
      key: 'recent', label: 'Недавние', icon: '',
      emojis: [] // filled from localStorage at render time
    },
    {
      key: 'smile', label: 'Смайлы и люди', icon: '',
      emojis: [
        '','','','','','','','','','','','','',
        '','','','','','️','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','️','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','️','','','','','','','','',
        '','','','','','','','',''
      ]
    },
    {
      key: 'gesture', label: 'Жесты и тело', icon: '',
      emojis: [
        '','','️','','','','','','️','','','','',
        '','','','','','️','','','','','','','',
        '','','','','','️','','','','','','','',
        '','','','','','','','','','️','','','',
        ''
      ]
    },
    {
      key: 'heart', label: 'Сердца и любовь', icon: '️',
      emojis: [
        '️','','','','','','','','','','️','','',
        '','','','','','','️','','','','','','',
        '','','','','','','⭐',''
      ]
    },
    {
      key: 'animal', label: 'Животные и природа', icon: '',
      emojis: [
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','️','️','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','‍','',
        '‍⬛','','','','','','','️','','','','','',
        '','','','️','','','','','','','','','',
        '️','','','','','','','','','','','','',
        '','','','','','','','','⭐','','','','️',
        '','','️','','️','️','','️','️','️','️','️','️',
        '️','️','️','','','','','','️',''
      ]
    },
    {
      key: 'food', label: 'Еда и напитки', icon: '',
      emojis: [
        '','','','','','','','','','','','','',
        '','','','','','','','','','','️','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','','','','','',''
      ]
    },
    {
      key: 'activity', label: 'Активности', icon: '',
      emojis: [
        '','','','','','','','','','','','','',
        '','','','','','','','','','','','','',
        '','','','','️','','','️','','','️','','',
        '️','','','️','','','','','','','','','',
        '','','','','','️','️','️','','️','','','',
        '','','','','','','','','','','','','',
        '','','️','','','','',''
      ]
    },
    {
      key: 'object', label: 'Объекты', icon: '',
      emojis: [
        '⌚','','','','⌨️','️','️','️','️','️','️','','',
        '','','','','','','','️','️','','️','','',
        '','','️','️','️','','⏱️','⏲️','⏰','️','⌛','⏳','',
        '','','','','️','','','️','','','','','',
        '','','','','️','','','','','','️','️','️',
        '','','️','','','️','','','','','','','️',
        '️','️','','️','','️','','','','','','️','',
        '','️','','','','','','','','','','️','',
        '','','','','','','','','','','','','',
        '','️','','️','','','️','️','','','','️','',
        '','️','','','','','','','','','','','',
        '️','','','','','','','','️','','','','',
        '','','','','','','','','','','️','️','',
        '','️','','️','️','️','','','','️','️','','',
        '','','','','','','','','','','','','️',
        '','','','','','️','️','️','️','️','️','','️',
        '','','','','',''
      ]
    },
    {
      key: 'symbol', label: 'Символы', icon: '[OK]',
      emojis: [
        '️','','','','','','','','','','️','','',
        '','','','','','','️','️','️','️','️','️','',
        '','️','️','','','','','','','','','','','',
        '','','','🆔','️','🉑','️','️','','','🈶','🈚','🈸',
        '🈺','🈷️','️','🆚','','🉐','㊙️','㊗️','🈴','🈵','🈹','🈲','🅰️',
        '🅱️','🆎','🆑','🅾️','🆘','[ERROR]','⭕','','','','','','',
        '️','','','','','','','','','','','','‼️',
        '⁉️','','','〽️','[!]️','','','️','','️','[OK]','🈯','',
        '️','️','[ERROR]','','','Ⓜ️','','','','','','🅿️','',
        '🈳','🈂️','','','','','','','','','','','',
        '','🈁','','ℹ️','','','','🆖','🆗','🆙','🆒','🆕','🆓',
        '0️⃣','1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','','','#️⃣',
        '*️⃣','▶️','⏸️','⏯️','⏹️','⏺️','⏭️','⏮️','⏩','⏪','⏫','⏬','◀️',
        '','','️','⬅️','⬆️','⬇️','️','️','️','️','️','<->️','️',
        '️','⤴️','⤵️','','','','','','','','','','',
        '️','️','','','™️','©️','®️','〰️','','','','','',
        '','','[OK]️','️','','','','','','','','','',
        '','','','','','','','','','▪️','▫️','◾','◽',
        '◼️','◻️','','','','','','','','⬛','⬜','','',
        '','','','','','','️‍️','','','️','️','️','️',
        '️','🃏','','🀄','','','','','','','','','',
        '','',''
      ]
    }
  ];

  var RECENT_KEY = 'formyla_emoji_recent';
  var RECENT_MAX = 32;

  function loadRecent() {
    try {
      var raw = localStorage.getItem(RECENT_KEY);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr.slice(0, RECENT_MAX) : [];
    } catch (_) {
      return [];
    }
  }

  function pushRecent(emoji) {
    var arr = loadRecent().filter(function (e) { return e !== emoji; });
    arr.unshift(emoji);
    if (arr.length > RECENT_MAX) arr = arr.slice(0, RECENT_MAX);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(arr)); } catch (_) {}
    return arr;
  }

  // Singleton DOM
  var pop = null;
  var tabsEl = null;
  var bodyEl = null;
  var searchEl = null;
  var currentTarget = null;
  var currentButton = null;
  var currentAnchor = null;
  var activeGroup = 'smile';
  var searchTerm = '';
  var lastSelectionStart = null;
  var lastSelectionEnd = null;

  function buildDom() {
    if (pop) return;
    pop = document.createElement('div');
    pop.className = 'fm-emoji-pop';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Эмодзи');
    pop.hidden = true;
    pop.innerHTML =
      '<div class="fm-emoji-search-row">' +
        '<input type="text" class="fm-emoji-search" placeholder="Поиск эмодзи…" autocomplete="off" />' +
      '</div>' +
      '<div class="fm-emoji-body"></div>' +
      '<div class="fm-emoji-tabs"></div>';
    document.body.appendChild(pop);

    tabsEl = pop.querySelector('.fm-emoji-tabs');
    bodyEl = pop.querySelector('.fm-emoji-body');
    searchEl = pop.querySelector('.fm-emoji-search');

    GROUPS.forEach(function (g) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'fm-emoji-tab';
      b.dataset.group = g.key;
      b.title = g.label;
      b.textContent = g.icon;
      b.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        activeGroup = g.key;
        searchTerm = '';
        if (searchEl) searchEl.value = '';
        renderActive();
      });
      tabsEl.appendChild(b);
    });

    searchEl.addEventListener('input', function () {
      searchTerm = (searchEl.value || '').trim().toLowerCase();
      renderActive();
    });

    bodyEl.addEventListener('click', function (e) {
      var b = e.target.closest('.fm-emoji-btn');
      if (!b) return;
      e.preventDefault();
      e.stopPropagation();
      insertEmoji(b.dataset.emoji);
    });

    // Prevent clicks inside picker from bubbling to document handler that closes it.
    pop.addEventListener('mousedown', function (e) { e.stopPropagation(); });
    pop.addEventListener('click', function (e) { e.stopPropagation(); });

    // Track caret position whenever target is interacted with, so we can
    // restore it when the user clicks an emoji (which steals focus briefly).
    document.addEventListener('selectionchange', function () {
      if (!currentTarget) return;
      if (document.activeElement === currentTarget) {
        lastSelectionStart = currentTarget.selectionStart;
        lastSelectionEnd = currentTarget.selectionEnd;
      }
    });
  }

  function renderActive() {
    if (!bodyEl) return;

    // Update tab highlight
    Array.prototype.forEach.call(tabsEl.children, function (tab) {
      tab.classList.toggle('active', tab.dataset.group === activeGroup && !searchTerm);
    });

    var html = '';
    if (searchTerm) {
      // Naive search across all groups by emoji char (we don't have keywords).
      // Allows users to filter using the actual emoji glyph; still useful for
      // narrowing huge lists quickly.
      html += '<div class="fm-emoji-section-title">Поиск</div>';
      html += '<div class="fm-emoji-grid">';
      var seen = {};
      GROUPS.forEach(function (g) {
        var list = g.key === 'recent' ? loadRecent() : g.emojis;
        list.forEach(function (em) {
          if (seen[em]) return;
          if (em.indexOf(searchTerm) === -1) return;
          seen[em] = 1;
          html += emojiBtn(em);
        });
      });
      html += '</div>';
    } else {
      var group = GROUPS.find(function (g) { return g.key === activeGroup; });
      if (group) {
        var list = group.key === 'recent' ? loadRecent() : group.emojis;
        html += '<div class="fm-emoji-section-title">' + group.label + '</div>';
        if (!list.length) {
          html += '<div class="fm-emoji-empty">Здесь будут ваши недавно использованные эмодзи.</div>';
        } else {
          html += '<div class="fm-emoji-grid">';
          list.forEach(function (em) { html += emojiBtn(em); });
          html += '</div>';
        }
      }
    }
    bodyEl.innerHTML = html;
    bodyEl.scrollTop = 0;
  }

  function emojiBtn(em) {
    var safe = em.replace(/"/g, '&quot;');
    return '<button type="button" class="fm-emoji-btn" data-emoji="' + safe + '" title="' + safe + '">' + em + '</button>';
  }

  function insertEmoji(emoji) {
    if (!currentTarget || !emoji) return;
    var t = currentTarget;
    var start = (lastSelectionStart != null) ? lastSelectionStart : (t.selectionStart != null ? t.selectionStart : t.value.length);
    var end   = (lastSelectionEnd   != null) ? lastSelectionEnd   : (t.selectionEnd   != null ? t.selectionEnd   : t.value.length);
    var before = t.value.slice(0, start);
    var after = t.value.slice(end);
    t.value = before + emoji + after;
    var caret = start + emoji.length;
    try {
      t.focus();
      t.setSelectionRange(caret, caret);
    } catch (_) {}
    lastSelectionStart = caret;
    lastSelectionEnd = caret;
    // Notify listeners (auto-grow, save-draft, send button enable).
    try {
      t.dispatchEvent(new Event('input', { bubbles: true }));
    } catch (_) {
      var ev = document.createEvent('Event');
      ev.initEvent('input', true, true);
      t.dispatchEvent(ev);
    }
    pushRecent(emoji);
    // If we're currently viewing the "recent" group, re-render to surface it.
    if (activeGroup === 'recent' && !searchTerm) renderActive();
  }

  function positionPopup() {
    if (!pop || !currentAnchor) return;
    var r = currentAnchor.getBoundingClientRect();
    var popW = pop.offsetWidth || 340;
    var popH = pop.offsetHeight || 380;
    var margin = 8;
    // Default: above the anchor, aligned to its left edge.
    var top = r.top - popH - margin;
    var left = r.left;
    if (top < margin) {
      // Not enough room above — place below.
      top = r.bottom + margin;
    }
    var maxLeft = window.innerWidth - popW - margin;
    if (left > maxLeft) left = maxLeft;
    if (left < margin) left = margin;
    pop.style.top = Math.max(margin, top) + 'px';
    pop.style.left = left + 'px';
  }

  function open(opts) {
    buildDom();
    currentTarget = opts.target || null;
    currentButton = opts.button || null;
    currentAnchor = opts.anchor || opts.button || null;
    // Remember caret so insertion happens at the right place even though
    // the user temporarily clicks the picker (which can blur the textarea).
    if (currentTarget && document.activeElement === currentTarget) {
      lastSelectionStart = currentTarget.selectionStart;
      lastSelectionEnd = currentTarget.selectionEnd;
    } else if (currentTarget) {
      lastSelectionStart = currentTarget.value ? currentTarget.value.length : 0;
      lastSelectionEnd = lastSelectionStart;
    }
    // Default group: recent if available, otherwise smileys.
    activeGroup = loadRecent().length ? 'recent' : 'smile';
    searchTerm = '';
    if (searchEl) searchEl.value = '';
    pop.hidden = false;
    renderActive();
    // Position after render to use real dimensions.
    requestAnimationFrame(positionPopup);
    if (currentButton) currentButton.setAttribute('aria-expanded', 'true');
  }

  function close() {
    if (!pop || pop.hidden) return;
    pop.hidden = true;
    if (currentButton) currentButton.setAttribute('aria-expanded', 'false');
    currentTarget = null;
    currentButton = null;
    currentAnchor = null;
  }

  function isOpen() {
    return pop && !pop.hidden;
  }

  // Close on outside click / Esc / scroll-away.
  document.addEventListener('mousedown', function (e) {
    if (!isOpen()) return;
    if (pop.contains(e.target)) return;
    if (currentButton && currentButton.contains(e.target)) return;
    close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isOpen()) {
      close();
      e.preventDefault();
    }
  });
  window.addEventListener('resize', function () { if (isOpen()) positionPopup(); });
  window.addEventListener('scroll', function () { if (isOpen()) positionPopup(); }, true);

  function attach(opts) {
    if (!opts || !opts.button || !opts.target) return;
    var btn = opts.button;
    var tgt = opts.target;
    btn.setAttribute('aria-haspopup', 'dialog');
    btn.setAttribute('aria-expanded', 'false');
    btn.addEventListener('mousedown', function (e) {
      // Capture caret BEFORE focus moves to button.
      if (document.activeElement === tgt) {
        lastSelectionStart = tgt.selectionStart;
        lastSelectionEnd = tgt.selectionEnd;
      }
    });
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (isOpen() && currentButton === btn) {
        close();
      } else {
        open({ button: btn, target: tgt, anchor: opts.anchor || btn });
      }
    });
  }

  global.EmojiPicker = {
    attach: attach,
    open: open,
    close: close,
    isOpen: isOpen
  };
}(window));
