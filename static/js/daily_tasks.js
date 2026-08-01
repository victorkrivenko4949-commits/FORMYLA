// Daily Tasks JavaScript
// Handles all interactions for the AI-generated daily math problems feature
// Pattern: fetch().then() (no async/await), DOMContentLoaded, setInterval polling

// Returns the topic selected in the UI (e.g. "Number Theory" day), or '' if none.
function getSelectedTopic() {
    var el = document.getElementById('dt-topic-input');
    if (el && typeof el.value === 'string') return el.value.trim();
    if (el && el.dataset && el.dataset.topic) return el.dataset.topic.trim();
    return '';
}

document.addEventListener('DOMContentLoaded', function() {
    // ── Read initial data from JSON script tag ──
    var dataEl = document.getElementById('dt-init-data');
    if (!dataEl) return;

    var data;
    try {
        data = JSON.parse(dataEl.textContent);
    } catch (e) {
        console.error('Failed to parse initial data:', e);
        return;
    }

    // ── Route to the correct state ──
    switch (data.status) {
        case 'blocked':
            showBlockedState(data);
            break;
        case 'no_set':
            showEmptyState();
            break;
        case 'generating':
            showGeneratingState(data);
            // Fix «прошло X:XX» сбрасывается при F5: даже на загрузке
            // страницы в состоянии 'generating' нужно сразу запустить
            // таймер — иначе он стоит на «прошло 0:00» до первого
            // polling-ответа (5 с тишины) и потом всё равно начнёт с 0.
            // Инициализируем по серверным данным (started_at / elapsed_seconds),
            // чтобы цифра соответствовала реальному прошедшему времени.
            startElapsedTimer({
                serverStartedAt: data.started_at,
                elapsedSeconds: data.elapsed_seconds
            });
            startPolling();
            break;
        case 'ready':
        case 'partial':
            showReadyState(data);
            break;
        case 'failed':
            // Раньше падало в default → showEmptyState() → пустой блок без ошибки.
            // Теперь показываем понятное сообщение об ошибке + кнопку «Повторить».
            showFailedState(data);
            break;
        default:
            console.warn('Unknown daily tasks status:', data.status);
            showEmptyState();
    }

    // ── Modal close handlers ──
    var closeBtn = document.getElementById('dt-modal-close');
    var overlay = document.getElementById('dt-modal-overlay');

    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            closeModal();
        });
    }

    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                closeModal();
            }
        });
    }

    // ── Enter key support in answer input ──
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            var input = document.getElementById('dt-answer-input');
            if (input && !input.disabled && document.activeElement === input && window.dtCurrentItemId) {
                submitAnswer(window.dtCurrentItemId);
            }
        }
    });
});

// ── State Display Functions ──

function showBlockedState(data) {
    var el = document.getElementById('dt-blocked-state');
    if (el) {
        // Update message with theme title
        var msgEl = document.getElementById('dt-blocked-message');
        if (msgEl && data.blocked_theme_title) {
            msgEl.textContent = 'Сначала утренний срез: «' + data.blocked_theme_title + '». 5 задач, примерно 15 минут.';
        }
        // Update probe link
        var linkEl = document.getElementById('dt-probe-link');
        if (linkEl && data.probe_url) {
            linkEl.href = data.probe_url;
        }
        el.classList.remove('dt-hidden');
    }
}

function showEmptyState() {
    var el = document.getElementById('dt-empty-state');
    if (el) el.classList.remove('dt-hidden');
}

/**
 * Показать состояние «генерация провалилась».
 *
 * Берём сообщение из data.error_message (приходит из routes.py для
 * status='failed') либо data.summary, либо общий fallback. Кнопка
 * «Попробовать снова» вызывает startGeneration() — он сам сбросит
 * failed-сет и запустит новую генерацию. Failed-сет НЕ считается
 * израсходованной попыткой 1/день (см. routes.regenerate).
 */
function showFailedState(data) {
    var el = document.getElementById('dt-failed-state');
    var empty = document.getElementById('dt-empty-state');
    var msg = (data && (data.error_message || data.summary)) || '';
    msg = String(msg || '').replace(/^❌\s*/, '');  // убираем дубликат значка

    if (el) {
        // Заполняем сообщение, если шаблон содержит #dt-failed-message
        var msgEl = document.getElementById('dt-failed-message');
        if (msgEl && msg) {
            msgEl.textContent = msg;
        }
        el.classList.remove('dt-hidden');
        return;
    }

    // Fallback: на старых шаблонах рисуем поверх empty-state.
    if (empty) {
        empty.classList.remove('dt-hidden');
        var title = empty.querySelector('.dt-empty-title');
        var sub = empty.querySelector('.dt-empty-sub');
        var btn = empty.querySelector('.dt-btn-primary');
        if (title) title.textContent = '❌ Не удалось сгенерировать задачи';
        if (sub) {
            sub.innerHTML = '';
            if (msg) {
                var p = document.createElement('div');
                p.style.cssText = 'color:#ff9b9b;margin-bottom:14px;line-height:1.45;';
                p.textContent = msg;
                sub.appendChild(p);
            }
            var hint = document.createElement('div');
            hint.style.cssText = 'color:rgba(255,255,255,0.55);font-size:14px;';
            hint.textContent = 'Это не отняло твою дневную попытку — можешь попробовать снова.';
            sub.appendChild(hint);
        }
        if (btn) btn.textContent = '🔄 Попробовать снова';
    }
}

function showGeneratingState(data) {
    var el = document.getElementById('dt-generating-state');
    if (el) el.classList.remove('dt-hidden');
    updateProgress(data);
}

function showReadyState(data) {
    var el = document.getElementById('dt-ready-state');
    if (el) el.classList.remove('dt-hidden');

    // Summary card
    if (data.summary) {
        var summaryCard = document.getElementById('dt-summary-card');
        if (summaryCard) {
            summaryCard.classList.remove('dt-hidden');
            var summaryText = document.getElementById('dt-summary-text');
            if (summaryText) summaryText.textContent = data.summary;
        }
    }

    // Partial notice
    if (data.status === 'partial') {
        var notice = document.getElementById('dt-partial-notice');
        if (notice) notice.classList.remove('dt-hidden');
    }

    // Date badge
    if (data.date) {
        var dateBadge = document.getElementById('dt-date');
        if (dateBadge) {
            var parts = data.date.split('-');
            dateBadge.textContent = parts[2] + '.' + parts[1] + '.' + parts[0];
        }
    }

    // Progress badge
    var progressBadge = document.getElementById('dt-progress-summary');
    if (progressBadge && data.progress) {
        progressBadge.textContent = data.progress.completed + '/' + data.progress.total;
    }

    // Task grid
    if (data.items) {
        renderTaskGrid(data.items);
    }
}

// ── Task Grid Rendering ──

function renderTaskGrid(items) {
    // Шаблон использует id="dt-task-grid" (см. templates/daily_tasks_page.html:253)
    var grid = document.getElementById('dt-task-grid') ||
               document.getElementById('dt-grid');
    if (!grid) {
        console.warn('Task grid container not found (looked for #dt-task-grid and #dt-grid)');
        return;
    }
    grid.innerHTML = '';

    items.forEach(function(item, index) {
        var card = document.createElement('div');
        card.className = 'dt-card';
        // Store item ID on the card so we can find it later for in-place updates
        card.setAttribute('data-item-id', item.id);
        if (item.is_flagged) card.classList.add('dt-flagged');
        if (item.user_answer !== null) card.classList.add('dt-done');
        // PR percent_to_level + calibration — серая рамка/бейдж для калибровочных
        if (item.is_calibration) card.classList.add('dt-calibration');

        // Number badge
        var number = document.createElement('div');
        number.className = 'dt-card-number';
        number.textContent = index + 1;

        // Header: topic + difficulty
        var header = document.createElement('div');
        header.className = 'dt-card-header';

        var topicBadge = document.createElement('span');
        topicBadge.className = 'dt-topic-badge';
        topicBadge.textContent = item.subtopic || '';

        var difficulty = document.createElement('span');
        difficulty.className = 'dt-difficulty';
        difficulty.textContent = renderDifficultyStars(item.difficulty);

        header.appendChild(topicBadge);
        header.appendChild(difficulty);

        // Preview text (truncated in CSS).
        // Используем innerHTML+KaTeX вместо textContent+stripLatex,
        // чтобы формулы \(x^2\) рендерились красиво, как в учебнике.
        var preview = document.createElement('div');
        preview.className = 'dt-card-preview';
        preview.innerHTML = escapeHtmlPreserveLatex(item.task_text || '');

        // Status row
        var statusRow = document.createElement('div');
        statusRow.className = 'dt-card-status';

        if (item.user_answer !== null) {
            if (item.is_correct) {
                statusRow.classList.add('dt-correct');
                statusRow.textContent = '✅ Верно';
            } else {
                statusRow.classList.add('dt-incorrect');
                statusRow.textContent = '❌ Неверно';
            }
        } else {
            statusRow.classList.add('dt-pending');
            statusRow.textContent = '⏳ Ожидает ответа';
        }

        if (item.is_flagged) {
            var flagBadge = document.createElement('span');
            flagBadge.className = 'dt-flag-badge';
            flagBadge.textContent = '⚠️ Флаг';
            statusRow.appendChild(flagBadge);
        }

        if (item.is_calibration) {
            var calBadge = document.createElement('span');
            calBadge.className = 'dt-calibration-badge';
            calBadge.title = 'Тест по этой теме не пройден — задача калибровочная';
            calBadge.textContent = '🧪 Калибровка';
            statusRow.appendChild(calBadge);
        }

        // Assemble card
        card.appendChild(number);
        card.appendChild(header);
        card.appendChild(preview);
        card.appendChild(statusRow);

        // Click to open modal
        card.addEventListener('click', function() {
            openTaskModal(item, index);
        });

        // Stagger entrance animation
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        (function(c, i) {
            setTimeout(function() {
                c.style.transition = 'all 0.5s ease';
                c.style.opacity = '1';
                c.style.transform = 'translateY(0)';
            }, 100 * i);
        })(card, index);

        grid.appendChild(card);
    });

    // КРИТИЧНО: рендерим LaTeX внутри только что добавленных карточек.
    // KaTeX auto-render отрабатывает только на DOMContentLoaded, а карточки
    // добавляются JS'ом ПОСЛЕ этого события — поэтому формулы оставались
    // сырым текстом (a_1, n^3 и т.п.). Вызываем renderMath(grid) явно.
    if (typeof renderMath === 'function') {
        renderMath(grid);
    }
}

// Шкала сложности — 8-балльная (см. validators.py: VALID_DIFFICULTY_RANGE = (1, 8)
// и opus_generate.md §8: L1-L2 простые / L3-L4 учебник / L5-L6 муниципал-регион ВсОШ /
// L7-L8 финал ВсОШ). Поэтому рисуем до 8 звёзд, без капа на 5.
function renderDifficultyStars(level) {
    if (!level && level !== 0) return '';
    var num = typeof level === 'number' ? level : parseInt(level);
    if (isNaN(num)) return String(level);
    var stars = '';
    for (var i = 0; i < Math.min(num, 8); i++) stars += '★';
    return stars;
}

function stripLatex(text) {
    if (!text) return '';
    // Remove display math $$...$$, inline math $...$, and \[ \] \( \)
    return text
        .replace(/\$\$/g, '')
        .replace(/\$/g, '')
        .replace(/\\\[/g, '')
        .replace(/\\\]/g, '')
        .replace(/\\\(/g, '')
        .replace(/\\\)/g, '');
}

// ── Generation ──

function startGeneration() {
    // Disable all generate buttons
    var genBtn = document.getElementById('dt-btn-generate');
    var regenBtn = document.getElementById('dt-btn-regenerate');
    if (genBtn) genBtn.disabled = true;
    if (regenBtn) regenBtn.disabled = true;

    // Hide other states (including failed), show generating
    var emptyState = document.getElementById('dt-empty-state');
    var readyState = document.getElementById('dt-ready-state');
    var failedState = document.getElementById('dt-failed-state');
    var genState = document.getElementById('dt-generating-state');
    if (emptyState) emptyState.classList.add('dt-hidden');
    if (readyState) readyState.classList.add('dt-hidden');
    if (failedState) failedState.classList.add('dt-hidden');
    if (genState) genState.classList.remove('dt-hidden');

    // Reset progress display
    var fill = document.getElementById('dt-progress-fill');
    var stepName = document.getElementById('dt-step-name');
    var eta = document.getElementById('dt-eta');
    if (fill) fill.style.width = '0%';
    if (stepName) stepName.textContent = 'Запуск…';
    if (eta) eta.textContent = '~3 мин';

    // Start elapsed timer
    startElapsedTimer();

    // POST to regenerate endpoint
    fetch('/daily_tasks/regenerate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
            body: JSON.stringify({ topic: getSelectedTopic() })
    })
    .then(function(response) {
        if (!response.ok) {
            return response.json().then(function(err) {
                throw new Error(err.message || 'Ошибка генерации');
            });
        }
        return response.json();
    })
    .then(function() {
        // Start polling
        startPolling();
        pollJobStatus(); // immediate first poll
    })
    .catch(function(error) {
        console.error('Generation error:', error);
        if (genBtn) genBtn.disabled = false;
        if (regenBtn) regenBtn.disabled = false;
        if (stepName) stepName.textContent = '❌ ' + error.message;
    });
}

// ── Polling + Elapsed timer ──

function startPolling() {
    if (window.dtPollInterval) clearInterval(window.dtPollInterval);
    window.dtPollInterval = setInterval(pollJobStatus, 5000);
}

function stopPolling() {
    if (window.dtPollInterval) {
        clearInterval(window.dtPollInterval);
        window.dtPollInterval = null;
    }
}

// Elapsed timer ticking every second
function formatMMSS(totalSeconds) {
    var s = Math.max(0, Math.floor(totalSeconds));
    var mins = Math.floor(s / 60);
    var secs = s % 60;
    return mins + ':' + (secs < 10 ? '0' : '') + secs;
}

// Fix «прошло X:XX» сбрасывается при F5.
// Раньше: window.dtElapsedStart = Date.now() — локальная метка, при F5
// она пропадала и таймер начинал с 0, хотя на сервере генерация уже шла.
// Теперь принимаем опциональный объект {serverStartedAt, elapsedSeconds}
// от бэкенда (см. daily_tasks/routes.py и daily_tasks/services.py:_serialize_job)
// и считаем смещение так, чтобы «локальное время старта» соответствовало
// реальному моменту начала генерации на сервере.
function startElapsedTimer(opts) {
    if (window.dtElapsedInterval) clearInterval(window.dtElapsedInterval);

    var nowMs = Date.now();
    var startMs = nowMs;  // дефолт — стартуем «сейчас»

    if (opts && typeof opts === 'object') {
        // Приоритет 1: ISO-строка started_at от сервера (UTC с 'Z').
        if (opts.serverStartedAt) {
            var parsed = Date.parse(opts.serverStartedAt);
            if (!isNaN(parsed)) {
                startMs = parsed;
            }
        }
        // Приоритет 2 / fallback: серверно посчитанные elapsed_seconds.
        // Используем, если ISO не парсится ИЛИ часы клиента сильно
        // разошлись с серверными (>30 сек) — в этом случае серверный
        // elapsed заведомо точнее.
        if (opts.elapsedSeconds !== undefined &&
            opts.elapsedSeconds !== null &&
            opts.elapsedSeconds >= 0) {
            var fromElapsed = nowMs - (opts.elapsedSeconds * 1000);
            if (startMs === nowMs ||
                Math.abs(fromElapsed - startMs) > 30000) {
                startMs = fromElapsed;
            }
        }
    }

    window.dtElapsedStart = startMs;
    var elEl = document.getElementById('dt-elapsed');
    if (elEl) {
        var initSec = (Date.now() - window.dtElapsedStart) / 1000;
        elEl.textContent = 'прошло ' + formatMMSS(initSec);
    }
    window.dtElapsedInterval = setInterval(function () {
        var el = document.getElementById('dt-elapsed');
        if (!el) return;
        var sec = (Date.now() - window.dtElapsedStart) / 1000;
        el.textContent = 'прошло ' + formatMMSS(sec);
    }, 1000);
}

function stopElapsedTimer() {
    if (window.dtElapsedInterval) {
        clearInterval(window.dtElapsedInterval);
        window.dtElapsedInterval = null;
    }
}

function pollJobStatus() {
    fetch('/daily_tasks/job_status')
        .then(function(response) {
            if (response.status === 404) {
                stopPolling();
                location.reload();
                return null;
            }
            return response.json();
        })
        .then(function(data) {
            if (!data) return;

            if (data.state === 'completed') {
                stopPolling();
                location.reload();
            } else if (data.state === 'failed') {
                stopPolling();
                var stepName = document.getElementById('dt-step-name');
                if (stepName) stepName.textContent = '❌ Ошибка генерации';
                setTimeout(function() {
                    location.reload();
                }, 3000);
            } else {
                // Синхронизация таймера «прошло X:XX» с сервером.
                // Если по каким-то причинам локальный отсчёт ушёл далеко
                // от серверного (>3 сек) — подкручиваем dtElapsedStart,
                // чтобы цифра не отставала / не убегала.
                if (data.started_at || data.elapsed_seconds !== undefined) {
                    var expectedStart = null;
                    if (data.started_at) {
                        var p = Date.parse(data.started_at);
                        if (!isNaN(p)) expectedStart = p;
                    }
                    if (expectedStart === null &&
                        data.elapsed_seconds !== undefined &&
                        data.elapsed_seconds !== null) {
                        expectedStart = Date.now() - data.elapsed_seconds * 1000;
                    }
                    if (expectedStart !== null) {
                        if (!window.dtElapsedInterval) {
                            // Таймер ещё не идёт (например, перешли в это
                            // состояние без startElapsedTimer) — запустим.
                            startElapsedTimer({
                                serverStartedAt: data.started_at,
                                elapsedSeconds: data.elapsed_seconds
                            });
                        } else if (window.dtElapsedStart &&
                                   Math.abs(expectedStart - window.dtElapsedStart) > 3000) {
                            window.dtElapsedStart = expectedStart;
                        }
                    }
                }
                updateProgress(data);
            }
        })
        .catch(function(error) {
            console.error('Poll error:', error);
        });
}

// Маппинг ключевых слов из current_step → data-step для подсветки
function detectPipelineStep(currentStep, progressPct) {
    if (!currentStep) {
        // fallback по проценту
        if (progressPct < 10) return 'profile';
        if (progressPct < 30) return 'gemini';
        if (progressPct < 60) return 'opus';
        if (progressPct < 80) return 'audit';
        if (progressPct < 95) return 'fix';
        return 'persist';
    }
    var s = currentStep.toLowerCase();
    if (s.indexOf('opus_fix') >= 0) return 'fix';
    if (s.indexOf('opus_generate') >= 0) return 'opus';
    if (s.indexOf('gemini_plan') >= 0 || s.indexOf('gemini') >= 0) return 'gemini';
    if (s.indexOf('gpt_audit') >= 0 || s.indexOf('gpt') >= 0 || s.indexOf('audit') >= 0 || s.indexOf('аудит') >= 0) return 'audit';
    if (s.indexOf('persist') >= 0 || s.indexOf('сохран') >= 0 || s.indexOf('финал') >= 0) return 'persist';
    if (s.indexOf('профил') >= 0 || s.indexOf('profile') >= 0 || s.indexOf('старт') >= 0 || s.indexOf('queued') >= 0) return 'profile';
    if (s.indexOf('план') >= 0) return 'gemini';
    if (s.indexOf('опус') >= 0 || s.indexOf('opus') >= 0) return s.indexOf('исправ') >= 0 ? 'fix' : 'opus';
    if (s.indexOf('генерац') >= 0) return 'opus';
    if (s.indexOf('исправ') >= 0 || s.indexOf('fix') >= 0) return 'fix';
    return null;
}

// Перевод технического current_step → человеко-читаемая строка
var DT_STEP_HUMAN = {
    'queued': 'Запуск…',
    'build_profile': 'Анализ твоего профиля',
    'profile': 'Анализ твоего профиля',
    'gemini_plan': 'Claude Sonnet 4.6 планирует задачи',
    'opus_generate': 'Claude Sonnet 4.6 пишет задачи (5 потоков)',
    'gpt_audit': 'Claude Opus 4.8 Fast проверяет качество (5 потоков)',
    'opus_fix': 'Claude Opus 4.8 Fast исправляет замечания',
    'rescue_pass': 'Rescue: повторная генерация проблемных задач',
    'persist': 'Сохраняем результат…',
    'completed': 'Готово!',
    'failed': 'Ошибка'
};
function humanizeStep(raw) {
    if (!raw) return 'Запуск…';
    var key = String(raw).trim().toLowerCase();
    if (DT_STEP_HUMAN[key]) return DT_STEP_HUMAN[key];
    // Если уже на русском (например «Анализ профиля») — оставляем как есть
    if (/[А-Яа-я]/.test(raw)) return raw;
    // Заменяем подчёркивания на пробелы, делаем первую букву большой
    var pretty = String(raw).replace(/_/g, ' ');
    return pretty.charAt(0).toUpperCase() + pretty.slice(1);
}

// Порядок шагов
var DT_PIPELINE_ORDER = ['profile', 'gemini', 'opus', 'audit', 'fix', 'persist'];

function updatePipelineSteps(activeStep) {
    if (!activeStep) return;
    var activeIdx = DT_PIPELINE_ORDER.indexOf(activeStep);
    if (activeIdx < 0) return;
    var steps = document.querySelectorAll('.dt-pipeline-step');
    for (var i = 0; i < steps.length; i++) {
        var s = steps[i];
        var key = s.getAttribute('data-step');
        var idx = DT_PIPELINE_ORDER.indexOf(key);
        s.classList.remove('is-active');
        s.classList.remove('is-done');
        if (idx < activeIdx) {
            s.classList.add('is-done');
        } else if (idx === activeIdx) {
            s.classList.add('is-active');
        }
    }
}

function updateProgress(data) {
    var fill = document.getElementById('dt-progress-fill');
    var progressText = document.getElementById('dt-progress-text');
    var stepName = document.getElementById('dt-step-name');
    var eta = document.getElementById('dt-eta');

    if (fill && data.progress_pct !== undefined) {
        fill.style.width = Math.min(data.progress_pct, 100) + '%';
    }

    if (progressText && data.progress_pct !== undefined) {
        progressText.textContent = Math.round(data.progress_pct) + '%';
    }

    if (stepName && data.current_step) {
        stepName.textContent = humanizeStep(data.current_step);
    }

    // ETA: используем eta_seconds от backend, иначе оцениваем от прогресса + elapsed
    if (eta) {
        var remaining = null;
        if (data.eta_seconds !== undefined && data.eta_seconds !== null && data.eta_seconds > 0) {
            remaining = Math.round(data.eta_seconds);
        } else if (data.eta_seconds === 0 || (data.progress_pct !== undefined && data.progress_pct >= 99)) {
            eta.textContent = 'почти готово…';
            remaining = -1;
        } else if (window.dtElapsedStart && data.progress_pct !== undefined && data.progress_pct > 1) {
            // Оценка: elapsed * (100 - pct) / pct
            var elapsedSec = (Date.now() - window.dtElapsedStart) / 1000;
            var pct = Math.max(1, Math.min(99, data.progress_pct));
            remaining = Math.round(elapsedSec * (100 - pct) / pct);
        }
        if (remaining !== null && remaining > 0) {
            var mins = Math.floor(remaining / 60);
            var secs = remaining % 60;
            if (mins > 0) {
                eta.textContent = 'осталось ~' + mins + ':' + (secs < 10 ? '0' : '') + secs;
            } else {
                eta.textContent = 'осталось ~' + secs + ' сек';
            }
        }
    }

    // Подсвечиваем активный шаг pipeline
    var activeStep = detectPipelineStep(data.current_step, data.progress_pct || 0);
    updatePipelineSteps(activeStep);
}

// ── Task Modal ──

function openTaskModal(item, index) {
    var overlay = document.getElementById('dt-modal-overlay');
    var title = document.getElementById('dt-modal-title');
    var difficulty = document.getElementById('dt-modal-difficulty');
    var body = document.getElementById('dt-modal-body');

    if (!overlay || !body) return;

    // Set title
    if (title) title.textContent = 'Задача ' + (index + 1) + ' · ' + (item.subtopic || '');
    if (difficulty) difficulty.textContent = renderDifficultyStars(item.difficulty);

    // Show overlay — remove dt-hidden so dt-open can take effect
    overlay.classList.remove('dt-hidden');

    // Build modal content
    var html = '';

    // Task info chips
    html += '<div class="dt-task-info">';
    html += '<span class="dt-info-chip">📚 <strong>' + escapeHtml(item.subtopic || '') + '</strong></span>';
    // Шкала difficulty — 8-балльная (см. renderDifficultyStars() и validators.py).
    html += '<span class="dt-info-chip">📊 Сложность: <strong>' + (item.difficulty || '?') + '/8</strong></span>';
    html += '</div>';

    // Flagged warning
    if (item.is_flagged) {
        html += '<div class="dt-flagged-warning">';
        html += '<span class="dt-flag-icon">⚠️</span>';
        html += '<span>Решение этой задачи не гарантировано — качество проверяется. Отнесись к ней критически.</span>';
        html += '</div>';
    }

    // Reason hint
    if (item.reason) {
        html += '<div class="dt-reason-text">💡 ' + escapeHtml(item.reason) + '</div>';
    }

    // Main task text (contains LaTeX — render raw, KaTeX handles it)
    html += '<div class="dt-task-text">' + item.task_text + '</div>';

    // Answer form or result
    if (item.user_answer === null) {
        html += '<div class="dt-answer-form" id="dt-answer-form-' + item.id + '">';
        // Сначала показываем требования к формату ответа — ученик увидит их
        // ДО ввода и сможет записать ответ правильно с первого раза.
        html += buildAnswerFormatHint(item.correct_answer);
        html += '<label class="dt-answer-label">✏️ Твой ответ:</label>';
        html += '<input type="text" class="dt-answer-input" id="dt-answer-input" placeholder="Введи ответ..." autocomplete="off">';
        html += '<div class="dt-answer-actions">';
        html += '<button class="dt-btn-check" id="dt-btn-check" onclick="submitAnswer(\'' + item.id + '\')">✅ Проверить</button>';
        html += '<button class="dt-btn-hint" id="dt-btn-hint" onclick="getHint(\'' + item.id + '\')">💡 Подсказка</button>';
        html += '</div>';
        html += '<div id="dt-hint-container"></div>';
        html += '</div>';

        // Auto-focus after render
        (function(id) {
            setTimeout(function() {
                var inp = document.getElementById('dt-answer-input');
                if (inp) inp.focus();
            }, 350);
        })(item.id);
    } else {
        // Already answered — show result
        var resultClass = item.is_correct ? 'dt-correct' : 'dt-incorrect';
        var resultIcon = item.is_correct ? '✅' : '❌';
        var resultText = item.is_correct ? 'Верно!' : 'Неверно';

        html += '<div class="dt-result ' + resultClass + '">';
        html += '<div class="dt-result-icon">' + resultIcon + '</div>';
        html += '<div class="dt-result-text">' + resultText + '</div>';
        if (item.correct_answer) {
            html += '<div class="dt-result-correct-answer">Правильный ответ: ' + escapeHtml(item.correct_answer) + '</div>';
        }
        // Если ответ не принят — показываем требования к формату записи,
        // чтобы ученик понял, в каком виде ожидался ответ.
        if (!item.is_correct && item.correct_answer) {
            html += buildAnswerFormatHint(item.correct_answer);
        }
        if (item.solution) {
            html += '<div class="dt-result-solution"><strong>📖 Решение:</strong><br>' + item.solution + '</div>';
        }
        html += '</div>';
    }

    body.innerHTML = html;

    // Show modal
    overlay.classList.add('dt-open');

    // Render LaTeX (KaTeX or fallback)
    renderMath(body);

    // Store current item ID for answer submission
    window.dtCurrentItemId = item.id;
}

function closeModal() {
    var overlay = document.getElementById('dt-modal-overlay');
    if (overlay) {
        overlay.classList.remove('dt-open');
        overlay.classList.add('dt-hidden');
    }
    window.dtCurrentItemId = null;
}

// ── Answer Submission ──

function submitAnswer(itemId) {
    var input = document.getElementById('dt-answer-input');
    var btn = document.getElementById('dt-btn-check');
    var hintBtn = document.getElementById('dt-btn-hint');

    if (!input || !input.value.trim()) return;

    var answer = input.value.trim();
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Проверка...';
    }
    if (hintBtn) hintBtn.disabled = true;

    fetch('/daily_tasks/' + itemId + '/submit', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            answer: answer,
            time_spent_seconds: 0
        })
    })
    .then(function(response) {
        if (!response.ok) {
            return response.json().then(function(err) {
                throw new Error(err.message || 'Ошибка проверки');
            });
        }
        return response.json();
    })
    .then(function(result) {
        var form = document.getElementById('dt-answer-form-' + itemId);
        if (!form) return;

        var resultClass = result.is_correct ? 'dt-correct' : 'dt-incorrect';
        var resultIcon = result.is_correct ? '✅' : '❌';
        var resultText = result.is_correct ? 'Верно!' : 'Неверно';

        var resultHtml = '<div class="dt-result ' + resultClass + '">';
        resultHtml += '<div class="dt-result-icon">' + resultIcon + '</div>';
        resultHtml += '<div class="dt-result-text">' + resultText + '</div>';
        if (result.correct_answer) {
            resultHtml += '<div class="dt-result-correct-answer">Правильный ответ: ' + escapeHtmlPreserveLatex(result.correct_answer) + '</div>';
        }
        if (!result.is_correct && result.correct_answer) {
            resultHtml += buildAnswerFormatHint(result.correct_answer);
        }
        if (result.solution) {
            resultHtml += '<div class="dt-result-solution"><strong>📖 Решение:</strong><br>' + result.solution + '</div>';
        }
        if (result.explanation) {
            resultHtml += '<div class="dt-result-solution"><strong>📝 Объяснение:</strong><br>' + result.explanation + '</div>';
        }
        resultHtml += '</div>';

        form.innerHTML = resultHtml;

        // Render LaTeX in result (KaTeX or fallback)
        renderMath(form);

        // ── Update the task card in-place (no page reload) ──────────
        // Find the card by matching item ID from the modal's data attribute
        updateTaskCardInPlace(itemId, result.is_correct);

        // Update progress badge without page reload
        var progressBadge = document.getElementById('dt-progress-summary');
        if (progressBadge) {
            var parts = progressBadge.textContent.split('/');
            var completed = parseInt(parts[0] || '0', 10) + 1;
            var total = parseInt(parts[1] || '0', 10);
            progressBadge.textContent = completed + '/' + total;
        }
    })
    .catch(function(error) {
        console.error('Submit error:', error);
        if (btn) {
            btn.disabled = false;
            btn.textContent = '✅ Проверить';
        }
        if (hintBtn) hintBtn.disabled = false;
    });
}


/**
 * Update the task card in the grid after an answer is submitted,
 * so the user sees the result without a page reload.
 * Tasks remain visible all day with their ✅/❌ status.
 */
function updateTaskCardInPlace(itemId, isCorrect) {
    // Find all cards in the grid
    var grid = document.getElementById('dt-task-grid');
    if (!grid) return;

    var cards = grid.querySelectorAll('.dt-card');
    // We need to find which card corresponds to this itemId.
    // The cards don't store itemId directly, so we look for the modal
    // that was opened for this item and find its card by position.
    // Alternative: store itemId as data attribute on the card.

    // Store itemId on the currently opened card via the modal
    var overlay = document.getElementById('dt-modal-overlay');
    if (overlay) {
        // Find the card whose click would open this item's modal.
        // Since we just answered, the modal is still open — we can
        // find the card by iterating and matching the click handler's item.
        // Simpler approach: mark the card when modal opens.
        var activeCard = findCardByItemId(itemId);
        if (activeCard) {
            activeCard.classList.add('dt-done');
            var statusRow = activeCard.querySelector('.dt-card-status');
            if (statusRow) {
                statusRow.className = 'dt-card-status';
                if (isCorrect) {
                    statusRow.classList.add('dt-correct');
                    statusRow.textContent = '✅ Верно';
                } else {
                    statusRow.classList.add('dt-incorrect');
                    statusRow.textContent = '❌ Неверно';
                }
            }
        }
    }
}


/**
 * Find a task card in the grid by matching its item ID.
 * Cards store their itemId in a data attribute set by openTaskModal.
 */
function findCardByItemId(itemId) {
    var grid = document.getElementById('dt-task-grid');
    if (!grid) return null;
    var cards = grid.querySelectorAll('.dt-card');
    for (var i = 0; i < cards.length; i++) {
        if (cards[i].getAttribute('data-item-id') === String(itemId)) {
            return cards[i];
        }
    }
    return null;
}

// ── Hints ──

function getHint(itemId) {
    var btn = document.getElementById('dt-btn-hint');
    var container = document.getElementById('dt-hint-container');

    if (!btn || !container) return;

    btn.disabled = true;
    btn.textContent = '⏳ Загрузка...';

    fetch('/daily_tasks/' + itemId + '/hint')
        .then(function(response) {
            if (!response.ok) {
                return response.json().then(function(err) {
                    throw new Error(err.message || 'Ошибка загрузки подсказки');
                });
            }
            return response.json();
        })
        .then(function(data) {
            var hintText = data.hint || data.text || 'Подсказка недоступна';
            container.innerHTML = '<div class="dt-hint-box"><strong>💡 Подсказка:</strong><br>' + hintText + '</div>';

            // Render LaTeX in hint (KaTeX or fallback)
            renderMath(container);

            btn.textContent = '💡 Подсказка получена';
        })
        .catch(function(error) {
            console.error('Hint error:', error);
            btn.disabled = false;
            btn.textContent = '💡 Подсказка';
            container.innerHTML = '<div class="dt-hint-box">⚠️ ' + error.message + '</div>';
        });
}

// ── Utilities ──

/** Log whether KaTeX auto-render is loaded */
(function checkKaTeX() {
    if (typeof renderMathInElement !== 'undefined') {
        console.log('[DT] ✓ KaTeX auto-render loaded (renderMathInElement available)');
    } else if (typeof katex !== 'undefined') {
        console.warn('[DT] ⚠ katex loaded but auto-render missing');
    } else {
        console.warn('[DT] ✗ KaTeX CDN not loaded — using fallback LaTeX rendering');
    }
})();

/**
 * Fallback LaTeX → styled spans when KaTeX CDN is unavailable.
 * Converts \(...\) to <span class="dt-latex-fallback">...</span>
 * and \[...\] to <div class="dt-latex-fallback dt-latex-display">...</div>.
 */
function renderLatexFallback(root) {
    if (!root) return;
    // Inline: \(...\)
    root.innerHTML = root.innerHTML.replace(/\\\(([\s\S]*?)\\\)/g, function(m, inner) {
        return '<span class="dt-latex-fallback">' + inner.trim() + '</span>';
    });
    // Display: \[...\]
    root.innerHTML = root.innerHTML.replace(/\\\[([\s\S]*?)\\\]/g, function(m, inner) {
        return '<div class="dt-latex-fallback dt-latex-display">' + inner.trim() + '</div>';
    });
}

/**
 * Attempts KaTeX rendering; falls back to simple styled spans if unavailable.
 */
function renderMath(root, opts) {
    // Апгрейд: «тяжёлые» формулы (\frac, \sqrt, \sum и т.п.) в инлайн $...$
// выносим в display $$...$$, чтобы высокая дробь рендерилась отдельным
// блоком, а не втискивалась в строку. Работает для всех путей (модалка/карточки).
    if (root && root.innerHTML && root.innerHTML.indexOf('$') !== -1) {
        root.innerHTML = root.innerHTML.replace(/(^|[^$])\$([^$]*?)\$(?!\$)/g, function(m, pre, inner) {
            if (/\\(frac|dfrac|sqrt|sum|int|prod|lim|binom|over)\b/.test(inner)) {
                return pre + '$$' + inner + '$$';
            }
            return m;
        });
    }
    // Апгрейд для inline \(...\): тяжёлые формулы выносим в display \[...\].
    if (root && root.innerHTML && root.innerHTML.indexOf('\\(') !== -1) {
        root.innerHTML = root.innerHTML.replace(/\\\(([\s\S]*?)\\\)/g, function(m, inner) {
            if (/\\(frac|dfrac|sqrt|sum|int|prod|lim|binom|over)\b/.test(inner)) {
                return '\\[' + inner + '\\]';
                }
            return m;
            });
        }
    if (typeof renderMathInElement !== 'undefined') {
        try {
            renderMathInElement(root, opts || {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false},
                    {left: '\\[', right: '\\]', display: true},
                    {left: '\\(', right: '\\)', display: false}
                ],
                throwOnError: false
            });
        } catch (e) {
            console.warn('[DT] KaTeX render error, using fallback:', e);
            renderLatexFallback(root);
        }
    } else {
        renderLatexFallback(root);
    }
}

function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

/**
 * Эвристика: по формату правильного ответа подсказываем ученику,
 * в каком виде нужно записать ответ при проверке.
 *
 * Возвращает HTML-блок с инструкциями (или пустую строку, если ответ
 * не задан). Используется и до ввода ответа (как guidance), и после
 * неверной попытки (как объяснение, почему ответ не принят).
 */
function buildAnswerFormatHint(correctAnswer) {
    if (!correctAnswer) return '';
    var raw = String(correctAnswer).trim();
    if (!raw) return '';

    var rules = [];
    var multiVar = /([A-Za-zА-Яа-я])\s*=\s*[^,;]+(\s*[,;]\s*[A-Za-zА-Яа-я]\s*=\s*[^,;]+)+/;

    if (multiVar.test(raw)) {
        rules.push('Запишите все неизвестные через запятую, например: <code>x = 4, y = 2</code>');
        rules.push('Используйте знак <code>=</code> между переменной и её значением');
        rules.push('Соблюдайте порядок переменных, указанный в условии задачи');
    } else if (/^[A-Za-zА-Яа-я]\s*=\s*\S+/.test(raw)) {
        rules.push('Запишите ответ в виде <code>' + raw.charAt(0) + ' = …</code> (с переменной и знаком равенства)');
    } else if (/^[^=]+,[^=]+/.test(raw) && raw.indexOf('=') === -1) {
        rules.push('Перечислите все значения через запятую, например: <code>' + escapeHtmlPreserveLatex(raw) + '</code>');
    } else if (/^[\[\(]\s*(?:-?\d+(?:[.,]\d+)?|[-+]?\\infty|[-+]?∞)\s*[;,]\s*(?:-?\d+(?:[.,]\d+)?|[-+]?\\infty|[-+]?∞)\s*[\)\]]\s*$/.test(raw)) {
        // Только настоящий интервал: '(a;b)', '[a;b]', '(-∞;2]', '[1;5)' и т.п.
        // Перечисление [1, 2, 5] больше не триггерит эту ветку — оно уходит выше
        // в «перечислите значения через запятую» (если без знаков =).
        rules.push('Запишите ответ интервалом, например: <code>(-∞; 2]</code> или <code>[1; 5)</code>');
    } else if (/\\frac|\//.test(raw)) {
        rules.push('Дробь записывайте через <code>/</code> (например <code>3/4</code>) или используйте <code>\\frac{a}{b}</code>');
        rules.push('Сократите дробь, если это возможно');
    } else if (/^-?\d+[\.,]\d+$/.test(raw)) {
        rules.push('Десятичную дробь пишите через запятую или точку, например: <code>' + escapeHtmlPreserveLatex(raw) + '</code>');
    } else if (/^-?\d+$/.test(raw)) {
        rules.push('Ответ — целое число. Запишите только число, без единиц измерения и пояснений');
    }

    if (/\\sqrt|√/.test(raw)) {
        rules.push('Корень записывайте как <code>\\sqrt{…}</code> (например <code>\\sqrt{3}</code>) или символом <strong>√</strong>');
    }

    rules.push('Лишних пробелов и пояснений быть не должно — только сам ответ');

    var html = '';
    html += '<div class="dt-answer-format-hint">';
    html += '<div class="dt-answer-format-title">📐 Требования к ответу:</div>';
    html += '<ul class="dt-answer-format-list">';
    for (var i = 0; i < rules.length; i++) {
        html += '<li>' + rules[i] + '</li>';
    }
    html += '</ul>';
    html += '</div>';
    return html;
}

/**
 * Экранирует HTML-спецсимволы, но СОХРАНЯЕТ LaTeX-конструкции
 * \(...\), \[...\], $...$, $$...$$ — чтобы KaTeX потом их корректно отрендерил.
 * Без этого `<` в `x < 5` ломает innerHTML, а `\(` экранируется в тег.
 */
function escapeHtmlPreserveLatex(text) {
    if (!text) return '';
    
// Апгрейд: «тяжёлые» формулы (\frac, \sqrt, \sum, \int, \prod, \lim, дроби)
// внутри инлайн $...$ выносим в display $$...$$ — иначе высокая дробь
// втискивается в строку и ломает поток текста. Пользователь хочет блок.
text = String(text).replace(/(^|[^$])\$([^$\n]*?)\$(?!\$)/g, function(m, pre, inner) {
    if (/\\(frac|dfrac|sqrt|sum|int|prod|lim|binom|over)\b/.test(inner)) {
        return pre + '$$' + inner + '$$';
    }
    return m;
});

    // Просто экранируем спецсимволы HTML — LaTeX в \(...\) их не использует.
    // Бэкслеши, фигурные скобки, кириллица — всё проходит как есть.
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
