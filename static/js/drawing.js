/* FORMYLA — Drawing playground client */
(function () {
    'use strict';

    var $ = function (id) { return document.getElementById(id); };

    var textArea     = $('problemText');
    var btn          = $('generateBtn');
    var regenBtn     = $('regenerateBtn');
    var loader       = $('drawingLoader');
    var errorBox     = $('drawingError');
    var resultWrap   = $('drawingResultWrap');
    var img          = $('drawing-result');
    var downloadBtn  = $('downloadBtn');
    var counter      = $('charCounter');
    var meta         = $('drawingMeta');

    if (!textArea || !btn) return;

    // ── Character counter ────────────────────────────────────────────────
    function updateCounter() {
        var len = textArea.value.length;
        counter.textContent = len + ' / 4000 символов';
        if (len > 4000)        counter.style.color = '#fca5a5';
        else if (len >= 10)    counter.style.color = '#86efac';
        else                   counter.style.color = '';
    }
    textArea.addEventListener('input', updateCounter);
    updateCounter();

    // ── UI helpers ───────────────────────────────────────────────────────
    function showError(msg) {
        errorBox.textContent = msg;
        errorBox.hidden = false;
    }
    function hideError() {
        errorBox.hidden = true;
        errorBox.textContent = '';
    }
    function setBusy(busy) {
        btn.disabled = busy;
        btn.textContent = busy ? '⏳ Генерируем…' : '✨ Сгенерировать чертёж';
        loader.hidden  = !busy;
    }

    // ── History strip ────────────────────────────────────────────────────
    var historyWrap = $('drawingHistoryWrap');
    var historyList = $('drawingHistoryList');

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function fmtDate(iso) {
        if (!iso) return '';
        return iso.replace('T', ' ').slice(0, 16);
    }
    function renderHistory(items) {
        if (!historyWrap || !historyList) return;
        if (!items || !items.length) {
            historyWrap.hidden = true;
            return;
        }
        var html = items.slice(0, 5).map(function(it) {
            var problem = escapeHtml(it.problem || '');
            var preview = problem.length > 80 ? problem.slice(0, 80) + '…' : problem;
            return ''
                + '<div class="drw-strip-card" data-id="' + it.id + '" '
                + '   data-problem="' + problem + '" '
                + '   data-img="' + escapeHtml(it.image_url) + '" '
                + '   title="' + problem + '">'
                + '  <img src="' + escapeHtml(it.image_url) + '" alt="">'
                + '  <div class="drw-strip-meta">' + preview + '</div>'
                + '  <button type="button" class="drw-strip-del" title="Удалить" data-id="' + it.id + '">×</button>'
                + '</div>';
        }).join('');
        historyList.innerHTML = html;
        historyWrap.hidden = false;
    }
    function loadHistory() {
        if (!historyWrap) return;
        fetch('/api/drawing/history?limit=5', { credentials: 'same-origin' })
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(j) { renderHistory(j && j.items); })
            .catch(function() {});
    }
    if (historyList) {
        historyList.addEventListener('click', function(e) {
            var del = e.target.closest('.drw-strip-del');
            if (del) {
                e.stopPropagation();
                if (!confirm('Удалить этот чертёж?')) return;
                var did = del.getAttribute('data-id');
                fetch('/api/drawing/history/' + did, {
                    method: 'DELETE',
                    credentials: 'same-origin'
                })
                .then(function(r) { return r.json(); })
                .then(function(j) {
                    if (j && j.ok) loadHistory();
                    else alert('Не удалось удалить.');
                })
                .catch(function() {});
                return;
            }
            var card = e.target.closest('.drw-strip-card');
            if (!card) return;
            var problem = card.getAttribute('data-problem') || '';
            var imgUrl = card.getAttribute('data-img');
            if (problem) {
                textArea.value = problem;
                updateCounter();
            }
            if (imgUrl && img) {
                img.src = imgUrl;
                if (downloadBtn) downloadBtn.href = imgUrl;
                resultWrap.hidden = false;
                resultWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    }
    // Prefill from sessionStorage (set by /drawing/history page).
    try {
        var prefill = sessionStorage.getItem('drw_prefill_problem');
        if (prefill) {
            textArea.value = prefill;
            updateCounter();
            sessionStorage.removeItem('drw_prefill_problem');
        }
    } catch (e) {}

    // Initial load of the history strip.
    loadHistory();

    // ── Submit ───────────────────────────────────────────────────────────
    // ── Image attach (photo of the problem) ──────────────────────────────
    var attachedImageDataUrl = null;   // full data:image/...;base64,...
    var attachedImageName    = null;

    function setAttachedImage(dataUrl, name) {
        attachedImageDataUrl = dataUrl || null;
        attachedImageName    = name || null;
        var box = document.getElementById('drwAttachPreview');
        if (!box) return;
        if (!attachedImageDataUrl) {
            box.hidden = true;
            box.innerHTML = '';
            return;
        }
        box.hidden = false;
        box.innerHTML =
            '<img src="' + attachedImageDataUrl + '" alt="фото условия" />'
          + '<div class="drw-attach-info">'
          +   '<span>📎 ' + (attachedImageName || 'фото условия')
          +   '</span>'
          +   '<button type="button" class="drw-attach-rm" '
          +           'aria-label="Убрать фото">✕</button>'
          + '</div>';
        var rm = box.querySelector('.drw-attach-rm');
        if (rm) rm.addEventListener('click', function () {
            setAttachedImage(null, null);
        });
    }

    function readFileAsDataUrl(file) {
        return new Promise(function (res, rej) {
            var fr = new FileReader();
            fr.onload  = function () { res(fr.result); };
            fr.onerror = function () { rej(fr.error); };
            fr.readAsDataURL(file);
        });
    }

    function handleImageFile(file) {
        if (!file) return;
        if (!file.type || file.type.indexOf('image/') !== 0) {
            showError('Поддерживаются только изображения (PNG/JPEG/WEBP).');
            return;
        }
        if (file.size > 8 * 1024 * 1024) {
            showError('Файл больше 8 МБ. Уменьши скриншот.');
            return;
        }
        readFileAsDataUrl(file).then(function (durl) {
            hideError();
            setAttachedImage(durl, file.name || ('clip.' +
                (file.type.split('/')[1] || 'png')));
        }).catch(function () {
            showError('Не удалось прочитать файл.');
        });
    }

    // File-input button.
    var fileInput  = document.getElementById('drwAttachFile');
    var attachBtn  = document.getElementById('drwAttachBtn');
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', function () { fileInput.click(); });
        fileInput.addEventListener('change', function () {
            if (fileInput.files && fileInput.files[0]) {
                handleImageFile(fileInput.files[0]);
                fileInput.value = '';
            }
        });
    }

    // Ctrl/Cmd+V paste a screenshot directly into the textarea.
    textArea.addEventListener('paste', function (ev) {
        var items = ev.clipboardData && ev.clipboardData.items;
        if (!items) return;
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            if (it && it.kind === 'file' && it.type.indexOf('image/') === 0) {
                ev.preventDefault();
                handleImageFile(it.getAsFile());
                return;
            }
        }
    });

    // Drag-and-drop a file directly onto the textarea / its wrapper.
    var dropTarget = textArea.closest('.drawing-form') || textArea;
    ['dragenter', 'dragover'].forEach(function (evt) {
        dropTarget.addEventListener(evt, function (ev) {
            if (ev.dataTransfer && Array.prototype.indexOf.call(
                    ev.dataTransfer.types || [], 'Files') !== -1) {
                ev.preventDefault();
                dropTarget.classList.add('drw-drop-hover');
            }
        });
    });
    ['dragleave', 'drop'].forEach(function (evt) {
        dropTarget.addEventListener(evt, function (ev) {
            dropTarget.classList.remove('drw-drop-hover');
            if (evt === 'drop'
                && ev.dataTransfer && ev.dataTransfer.files
                && ev.dataTransfer.files[0]) {
                ev.preventDefault();
                handleImageFile(ev.dataTransfer.files[0]);
            }
        });
    });

    // ── Safe JSON parser: reads body as text, tries JSON, falls back ────
    function parseResponse(r) {
        var ct = (r.headers.get('Content-Type') || '').toLowerCase();
        return r.text().then(function (bodyText) {
            // If the server returned HTML (error page, proxy error, etc.)
            // we cannot parse it as JSON — treat as a non-JSON error.
            if (ct.indexOf('application/json') === -1) {
                // Try to detect Cloudflare / nginx / Flask error pages
                var snippet = bodyText.length > 200
                    ? bodyText.slice(0, 200) + '…'
                    : bodyText;
                return {
                    ok: false,
                    status: r.status,
                    data: {
                        error: 'Сервер вернул неожиданный ответ (HTML вместо JSON). '
                            + 'Статус: ' + r.status + '. '
                            + 'Возможно, проблема с сетью или прокси.',
                        _body_snippet: snippet,
                    }
                };
            }
            try {
                var data = JSON.parse(bodyText);
                return { ok: r.ok, status: r.status, data: data };
            } catch (e) {
                // JSON parse failed despite correct Content-Type
                var snippet2 = bodyText.length > 200
                    ? bodyText.slice(0, 200) + '…'
                    : bodyText;
                return {
                    ok: false,
                    status: r.status,
                    data: {
                        error: 'Ошибка обработки ответа сервера. Попробуйте ещё раз.',
                        _body_snippet: snippet2,
                    }
                };
            }
        });
    }

    // ── Polling state ──────────────────────────────────────────────────────
    var _pollTimer = null;
    var _pollStartedAt = 0;
    var _POLL_INTERVAL = 2000;   // ms between polls
        var _POLL_TIMEOUT = 600000;    // 600 s (10 min) — max wait before showing timeout

    function _pollStop() {
        if (_pollTimer) {
            clearInterval(_pollTimer);
            _pollTimer = null;
        }
    }

    function _renderResult(result) {
        // result is the object returned by the status endpoint under "result" key
        var src = result.image_url || result.data_url
               || (result.image_b64 ? ('data:image/png;base64,' + result.image_b64) : null);
        if (!src) {
            showError('Сервер не вернул изображение.');
            setBusy(false);
            return;
        }
        img.src = src;
        downloadBtn.href = result.data_url
                        || (result.image_b64
                            ? ('data:image/png;base64,' + result.image_b64)
                            : src);
        downloadBtn.setAttribute('download', 'drawing.png');

        if (meta) {
            var parts = [];
            if (result.model)              parts.push('Модель: ' + result.model);
            if (typeof result.cost_usd === 'number' && result.cost_usd > 0) {
                parts.push('Стоимость: $' + result.cost_usd.toFixed(4));
            }
            meta.textContent = parts.join(' • ');
        }

        resultWrap.hidden = false;
        resultWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
        loadHistory();
        setBusy(false);
    }

    function _pollStatus(taskId) {
        fetch('/api/drawing/status/' + encodeURIComponent(taskId), {
            credentials: 'same-origin'
        })
        .then(function (r) { return parseResponse(r); })
        .then(function (res) {
            if (!res.ok || !res.data) {
                _pollStop();
                setBusy(false);
                showError('Ошибка при проверке статуса генерации. Попробуйте ещё раз.');
                return;
            }
            var data = res.data;
            var status = data.status || 'pending';

            // Check timeout (>300 s (5 min) since first POST)
            if (Date.now() - _pollStartedAt > _POLL_TIMEOUT) {
                _pollStop();
                setBusy(false);
                showError(
                    '⏱ Генерация заняла слишком долго (>10 минут). '
                    + 'Попробуйте ещё раз или упростите условие задачи.'
                );
                // Notify server the task timed out from the client perspective
                // (the server thread still runs but we stop waiting).
                return;
            }

            if (status === 'completed') {
                _pollStop();
                _renderResult(data.result || {});
            } else if (status === 'error') {
                _pollStop();
                setBusy(false);
                showError(data.error || 'Ошибка генерации. Попробуйте ещё раз.');
            } else {
                // Still processing — keep polling (timer already running)
            }
        })
        .catch(function () {
            _pollStop();
            setBusy(false);
            showError('Сетевая ошибка при проверке статуса. Попробуйте ещё раз.');
        });
    }

    function submit(bypassCache) {
        hideError();
        _pollStop();

        var problem = (textArea.value || '').trim();
        var hasImage = !!attachedImageDataUrl;
        // If a photo is attached, we relax the 10-char minimum on text.
        if (!hasImage && problem.length < 10) {
            showError('Условие слишком короткое — нужно хотя бы 10 символов.');
            return;
        }
        if (problem.length > 4000) {
            showError('Условие слишком длинное — максимум 4000 символов.');
            return;
        }

        setBusy(true);
        resultWrap.hidden = true;

        var payload = {
            problem: problem,
            bypass_cache: !!bypassCache
        };
        if (hasImage) {
            payload.image_b64 = attachedImageDataUrl;
        }
        try {
            console.log('[drawing] submit',
                'problem_len=', problem.length,
                'has_image=', hasImage,
                'image_b64_len=', hasImage ? attachedImageDataUrl.length : 0,
                'bypass=', !!bypassCache);
        } catch (e) {}

        fetch('/api/drawing/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function (r) {
            return parseResponse(r);
        })
        .then(function (res) {
            if (!res.ok) {
                setBusy(false);
                var msg = (res.data && res.data.error)
                    || ('Ошибка ' + res.status + '. Попробуйте ещё раз.');
                if (res.data && res.data.detail) {
                    msg += '  (' + res.data.detail + ')';
                }
                showError(msg);
                return;
            }

            var data = res.data || {};
            var taskId = data.task_id;
            if (!taskId) {
                setBusy(false);
                showError('Сервер не вернул идентификатор задачи.');
                return;
            }

            // Start polling
            _pollStartedAt = Date.now();
            _pollTimer = setInterval(function () {
                _pollStatus(taskId);
            }, _POLL_INTERVAL);
            // Also fire immediately so the first check happens straight away
            _pollStatus(taskId);
        })
        .catch(function (err) {
            setBusy(false);
            showError('Сетевая ошибка. Проверьте подключение к интернету и попробуйте ещё раз.');
        });
    }

    btn.addEventListener('click', function () {
        console.log('[drawing.js] Generate button clicked');
        submit(false);
    });
    if (regenBtn) {
        regenBtn.addEventListener('click', function () {
            console.log('[drawing.js] Regenerate button clicked');
            submit(false);
        });
    }
    console.log('[drawing.js] Event listeners attached successfully');

    // Two "force-fresh" buttons:
    //   #regenerateFreshBtn   — inside the result block (post-success)
    //   #generateFreshTopBtn  — in the main form (always visible)
    // Both call submit(true) which sets bypass_cache=true on the POST.
    var regenFreshBtn = $('regenerateFreshBtn');
    if (regenFreshBtn) {
        regenFreshBtn.addEventListener('click', function () { submit(true); });
    }
    var generateFreshTopBtn = $('generateFreshTopBtn');
    if (generateFreshTopBtn) {
        generateFreshTopBtn.addEventListener('click', function () { submit(true); });
    }

    // Ctrl/Cmd+Enter — quick submit (uses cache)
    textArea.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            submit(false);
        }
    });
})();
