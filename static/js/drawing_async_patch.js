/* drawing_async_patch.js
 * Patches drawing.js: POST /api/drawing/generate now returns task_id immediately.
 * Polls GET /api/drawing/status/<task_id> every 2.5s until completed or error.
 * Include this script AFTER drawing.js in the drawing.html template.
 */
document.addEventListener('DOMContentLoaded', function () {
    var btn          = document.getElementById('generateBtn');
    var regenBtn     = document.getElementById('regenerateBtn');
    var regenFreshBtn = document.getElementById('regenerateFreshBtn');
    var genFreshTopBtn = document.getElementById('generateFreshTopBtn');
    var textArea     = document.getElementById('problemText');
    var loader       = document.getElementById('drawingLoader');
    var errorBox     = document.getElementById('drawingError');
    var resultWrap   = document.getElementById('drawingResultWrap');
    var img          = document.getElementById('drawing-result');
    var downloadBtn  = document.getElementById('downloadBtn');
    var meta         = document.getElementById('drawingMeta');

    if (!btn || !textArea) return;

    var attachedImageDataUrl = null;
    // Inherit attached image from drawing.js scope via closure — not possible,
    // so we read it from the preview element if present.
    function getAttachedImage() {
        var box = document.getElementById('drwAttachPreview');
        if (!box || box.hidden) return null;
        var im = box.querySelector('img');
        return im ? im.src : null;
    }

    function showError(msg) {
        if (errorBox) { errorBox.textContent = msg; errorBox.hidden = false; }
    }
    function hideError() {
        if (errorBox) { errorBox.hidden = true; errorBox.textContent = ''; }
    }
    function setBusy(busy, label) {
        if (btn) {
            btn.disabled = busy;
            btn.textContent = busy ? (label || 'Generating...') : '\u2728 Generate drawing';
        }
        if (loader) loader.hidden = !busy;
    }

    var _pollTimer = null;
    var _pollStart = 0;
    var POLL_INTERVAL = 2500;
    var POLL_TIMEOUT  = 300000;  // 5 min — pipeline may run multiple LLM rounds
    var _hardTimeoutFired = false;

    function stopPolling() {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    }

    function pollStatus(taskId) {
        stopPolling();
        _pollStart = Date.now();
        _hardTimeoutFired = false;
        _pollTimer = setInterval(function () {
            if (Date.now() - _pollStart > POLL_TIMEOUT) {
                if (!_hardTimeoutFired) {
                    _hardTimeoutFired = true;
                    // Don't stop polling — keep waiting in case server still works
                    setBusy(false);
                    if (errorBox) {
                        errorBox.textContent = '⏳ Генерация занимает больше времени (' + Math.round((Date.now() - _pollStart)/1000) + 'c). Ожидание продолжается…';
                        errorBox.hidden = false;
                    }
                }
                // Keep polling despite timeout — server may still complete
            }
            fetch('/api/drawing/status/' + taskId, { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d.status === 'completed') {
                        stopPolling();
                        setBusy(false);
                        hideError();
                        var res = d.result || {};
                        var src = res.image_url || res.data_url
                               || (res.image_b64 ? 'data:image/png;base64,' + res.image_b64 : null);
                        if (!src) { showError('Server returned no image.'); return; }
                        if (img) img.src = src;
                        if (downloadBtn) {
                            downloadBtn.href = res.data_url || (res.image_b64 ? 'data:image/png;base64,' + res.image_b64 : src);
                            downloadBtn.setAttribute('download', 'drawing.png');
                        }
                        if (meta) {
                            var parts = [];
                            if (res.model) parts.push('Model: ' + res.model);
                            if (typeof res.cost_usd === 'number' && res.cost_usd > 0)
                                parts.push('Cost: $' + res.cost_usd.toFixed(4));
                            meta.textContent = parts.join(' \u2022 ');
                        }
                        if (resultWrap) {
                            resultWrap.hidden = false;
                            resultWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                        // Refresh history strip
                        if (typeof loadHistory === 'function') loadHistory();
                    } else if (d.status === 'error') {
                        stopPolling();
                        setBusy(false);
                        hideError();
                        showError(d.error || 'Ошибка генерации. Попробуйте ещё раз.');
                    }
                    // else still processing — keep polling
                })
                .catch(function (err) {
                    console.error('[drawing_async] poll error', err);
                });
        }, POLL_INTERVAL);
    }

    function submitAsync(bypassCache) {
        hideError();
        var problem = (textArea.value || '').trim();
        var imageDataUrl = getAttachedImage();
        var hasImage = !!imageDataUrl;
        if (!hasImage && problem.length < 10) {
            showError('Condition too short (min 10 chars).');
            return;
        }
        if (problem.length > 4000) {
            showError('Condition too long (max 4000 chars).');
            return;
        }
        setBusy(true, '\u23f3 Generating...');
        if (resultWrap) resultWrap.hidden = true;
        stopPolling();

        var payload = { problem: problem, bypass_cache: !!bypassCache };
        if (hasImage) payload.image_b64 = imageDataUrl;

        fetch('/api/drawing/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; }); })
        .then(function (res) {
            if (!res.ok) {
                setBusy(false);
                showError((res.data && res.data.error) || ('Error ' + res.status));
                return;
            }
            var taskId = res.data && res.data.task_id;
            if (!taskId) {
                // Legacy sync response (cache hit returns image directly)
                setBusy(false);
                var d = res.data || {};
                var src = d.image_url || d.data_url || (d.image_b64 ? 'data:image/png;base64,' + d.image_b64 : null);
                if (src && img) {
                    img.src = src;
                    if (downloadBtn) { downloadBtn.href = src; downloadBtn.setAttribute('download', 'drawing.png'); }
                    if (resultWrap) { resultWrap.hidden = false; resultWrap.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
                    if (typeof loadHistory === 'function') loadHistory();
                } else {
                    showError('Server returned no image.');
                }
                return;
            }
            // Async path: poll for result
            pollStatus(taskId);
        })
        .catch(function (err) {
            setBusy(false);
            showError('Network error. Check your connection and try again.');
            console.error('[drawing_async] submit error', err);
        });
    }

    // Override all generate buttons
    function rebind(el, bypass) {
        if (!el) return;
        var clone = el.cloneNode(true);
        el.parentNode.replaceChild(clone, el);
        clone.addEventListener('click', function () { submitAsync(bypass); });
    }
    rebind(btn, false);
    rebind(regenBtn, false);
    rebind(regenFreshBtn, true);
    rebind(genFreshTopBtn, true);

    // Ctrl/Cmd+Enter
    textArea.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            submitAsync(false);
        }
    });
});