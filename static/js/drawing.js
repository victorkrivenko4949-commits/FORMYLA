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
        counter.textContent = len + ' / 2000 символов';
        if (len > 2000)        counter.style.color = '#fca5a5';
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

    // ── Submit ───────────────────────────────────────────────────────────
    function submit() {
        hideError();
        var problem = (textArea.value || '').trim();
        if (problem.length < 10) {
            showError('Условие слишком короткое — нужно хотя бы 10 символов.');
            return;
        }
        if (problem.length > 2000) {
            showError('Условие слишком длинное — максимум 2000 символов.');
            return;
        }

        setBusy(true);
        resultWrap.hidden = true;

        fetch('/api/drawing/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem: problem })
        })
        .then(function (r) {
            return r.json().then(function (data) {
                return { ok: r.ok, status: r.status, data: data };
            });
        })
        .then(function (res) {
            setBusy(false);
            if (!res.ok) {
                var msg = (res.data && res.data.error)
                    || ('Ошибка ' + res.status + '. Попробуйте ещё раз.');
                if (res.data && res.data.detail) {
                    msg += '  (' + res.data.detail + ')';
                }
                showError(msg);
                return;
            }

            var data = res.data || {};
            var src = data.image_url || data.data_url
                   || (data.image_b64 ? ('data:image/png;base64,' + data.image_b64) : null);

            if (!src) {
                showError('Сервер не вернул изображение.');
                return;
            }

            img.src = src;
            // Prefer data-URL for direct download (works even if the static
            // file was not persisted on disk).
            downloadBtn.href = data.data_url
                            || (data.image_b64
                                ? ('data:image/png;base64,' + data.image_b64)
                                : src);
            downloadBtn.setAttribute('download', 'drawing.png');

            if (meta) {
                var parts = [];
                if (data.model)              parts.push('Модель: ' + data.model);
                if (typeof data.cost_usd === 'number' && data.cost_usd > 0) {
                    parts.push('Стоимость: $' + data.cost_usd.toFixed(4));
                }
                meta.textContent = parts.join(' • ');
            }

            resultWrap.hidden = false;
            resultWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
        })
        .catch(function (err) {
            setBusy(false);
            showError('Сетевая ошибка: ' + (err && err.message ? err.message : err));
        });
    }

    btn.addEventListener('click', submit);
    if (regenBtn) regenBtn.addEventListener('click', submit);

    // Ctrl/Cmd+Enter — quick submit
    textArea.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            submit();
        }
    });
})();
