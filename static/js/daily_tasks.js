// Daily Tasks JavaScript
// Handles all interactions for the AI-generated daily math problems feature
// Pattern: fetch().then() (no async/await), DOMContentLoaded, setInterval polling

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
        case 'no_set':
            showEmptyState();
            break;
        case 'generating':
            showGeneratingState(data);
            startPolling();
            break;
        case 'ready':
        case 'partial':
            showReadyState(data);
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

function showEmptyState() {
    var el = document.getElementById('dt-empty-state');
    if (el) el.classList.remove('dt-hidden');
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
        if (item.is_flagged) card.classList.add('dt-flagged');
        if (item.user_answer !== null) card.classList.add('dt-done');

        // Number badge
        var number = document.createElement('div');
        number.className = 'dt-card-number';
        number.textContent = index + 1;

        // Header: topic + difficulty
        var header = document.createElement('div');
        header.className = 'dt-card-header';

        var topicBadge = document.createElement('span');
        topicBadge.className = 'dt-topic-badge';
        topicBadge.textContent = item.topic || '';

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

function renderDifficultyStars(level) {
    if (!level && level !== 0) return '';
    var num = typeof level === 'number' ? level : parseInt(level);
    if (isNaN(num)) return String(level);
    var stars = '';
    for (var i = 0; i < Math.min(num, 5); i++) stars += '★';
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

    // Hide other states, show generating
    var emptyState = document.getElementById('dt-empty-state');
    var readyState = document.getElementById('dt-ready-state');
    var genState = document.getElementById('dt-generating-state');
    if (emptyState) emptyState.classList.add('dt-hidden');
    if (readyState) readyState.classList.add('dt-hidden');
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
        }
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

function startElapsedTimer() {
    if (window.dtElapsedInterval) clearInterval(window.dtElapsedInterval);
    window.dtElapsedStart = Date.now();
    var elEl = document.getElementById('dt-elapsed');
    if (elEl) elEl.textContent = 'прошло 0:00';
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
    'gemini_plan': 'Claude Sonnet 4.5 планирует задачи',
    'opus_generate': 'Claude Sonnet 4.5 пишет задачи (5 потоков)',
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
    if (title) title.textContent = 'Задача ' + (index + 1) + ' · ' + (item.topic || '');
    if (difficulty) difficulty.textContent = renderDifficultyStars(item.difficulty);

    // Show overlay — remove dt-hidden so dt-open can take effect
    overlay.classList.remove('dt-hidden');

    // Build modal content
    var html = '';

    // Task info chips
    html += '<div class="dt-task-info">';
    html += '<span class="dt-info-chip">📚 <strong>' + escapeHtml(item.topic || '') + '</strong></span>';
    html += '<span class="dt-info-chip">📊 Сложность: <strong>' + (item.difficulty || '?') + '/5</strong></span>';
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
            resultHtml += '<div class="dt-result-correct-answer">Правильный ответ: ' + escapeHtml(result.correct_answer) + '</div>';
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

        // Reload page after brief delay to update card statuses
        setTimeout(function() {
            location.reload();
        }, 2500);
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
 * Экранирует HTML-спецсимволы, но СОХРАНЯЕТ LaTeX-конструкции
 * \(...\), \[...\], $...$, $$...$$ — чтобы KaTeX потом их корректно отрендерил.
 * Без этого `<` в `x < 5` ломает innerHTML, а `\(` экранируется в тег.
 */
function escapeHtmlPreserveLatex(text) {
    if (!text) return '';
    // Просто экранируем спецсимволы HTML — LaTeX в \(...\) их не использует.
    // Бэкслеши, фигурные скобки, кириллица — всё проходит как есть.
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}
