/**
 * Prep Wizard — vanilla JS for the 4-step plan creation wizard.
 */

// ─── State ───────────────────────────────────────────────────────────────────
const wizState = {
    step: 1,
    olympiadSlug: null,
    olympiadName: null,
    stages: [],
    selectedStage: null,
    selectedStageDate: null,
    baseline: null,       // 'radar' | 'adaptive_test'
    targetDate: null,     // ISO string
};

// ─── Step navigation ─────────────────────────────────────────────────────────
function goToStep(n) {
    if (n < 1 || n > 4) return;

    // Hide all blocks
    document.querySelectorAll('.wiz-block').forEach(b => b.classList.remove('active'));
    // Show target
    const target = document.getElementById('step-' + n);
    if (target) target.classList.add('active');

    // Update dots
    for (let i = 1; i <= 4; i++) {
        const dot = document.getElementById('dot-' + i);
        const line = document.getElementById('line-' + (i - 1));
        if (!dot) continue;
        dot.classList.remove('active', 'done');
        if (i < n) dot.classList.add('done');
        else if (i === n) dot.classList.add('active');
        if (line) {
            line.classList.remove('done');
            if (i <= n) line.classList.add('done');
        }
    }

    wizState.step = n;

    // Populate step-specific content
    if (n === 2) populateStages();
    if (n === 4) populateSummary();
}

// ─── Step 1: Select olympiad ─────────────────────────────────────────────────
function selectOlympiad(el) {
    // Deselect all
    document.querySelectorAll('.wiz-oly-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');

    wizState.olympiadSlug = el.dataset.slug;
    wizState.olympiadName = el.dataset.short || el.dataset.name;

    // Parse stages
    try {
        wizState.stages = JSON.parse(el.dataset.stages || '[]');
    } catch (e) {
        wizState.stages = [];
    }

    // Enable next
    const btn = document.getElementById('btn-next-1');
    if (btn) btn.disabled = false;
}

// ─── Step 2: Select stage ────────────────────────────────────────────────────
function populateStages() {
    const container = document.getElementById('stages-list');
    if (!container) return;
    container.innerHTML = '';

    wizState.stages.forEach((stage, idx) => {
        const name = typeof stage === 'object' ? stage.name : stage;
        const dateRange = typeof stage === 'object' ? (stage.date_range || '') : '';

        const div = document.createElement('div');
        div.className = 'wiz-stage-item';
        div.tabIndex = 0;
        div.setAttribute('aria-label', name);
        div.dataset.stageName = name;
        div.dataset.stageDate = dateRange;
        div.onclick = function () { selectStage(this); };
        div.onkeydown = function (e) { if (e.key === 'Enter') selectStage(this); };

        div.innerHTML = `
            <div class="wiz-stage-radio"></div>
            <div>
                <div class="wiz-stage-name">${name}</div>
                ${dateRange ? `<div class="wiz-stage-date"> ${dateRange}</div>` : ''}
            </div>
        `;
        container.appendChild(div);
    });

    // Reset selection
    wizState.selectedStage = null;
    const btn = document.getElementById('btn-next-2');
    if (btn) btn.disabled = true;
}

function selectStage(el) {
    document.querySelectorAll('.wiz-stage-item').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');

    wizState.selectedStage = el.dataset.stageName;
    wizState.selectedStageDate = el.dataset.stageDate;

    // Try to parse a target date from the date_range
    wizState.targetDate = parseDateFromRange(el.dataset.stageDate);

    const btn = document.getElementById('btn-next-2');
    if (btn) btn.disabled = false;
}

function parseDateFromRange(dateStr) {
    // Try to extract a date like "8 ноя 2026" or "14–20 апр 2027"
    // We'll use the last date mentioned
    if (!dateStr) {
        // Default: 3 months from now
        const d = new Date();
        d.setMonth(d.getMonth() + 3);
        return d.toISOString().split('T')[0];
    }

    const months = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04',
        'мая': '05', 'май': '05', 'июн': '06', 'июл': '07',
        'авг': '08', 'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12',
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
        'июня': '06', 'июля': '07', 'августа': '08', 'сентября': '09',
        'октября': '10', 'ноября': '11', 'декабря': '12',
    };

    // Match patterns like "8 ноя 2026" or "14 апр 2027"
    const re = /(\d{1,2})\s*[–\-]?\s*\d{0,2}\s*(янв|фев|мар|апр|мая|май|июн|июл|авг|сен|окт|ноя|дек|января|февраля|марта|апреля|июня|июля|августа|сентября|октября|ноября|декабря)\w*\s*(\d{4})/i;
    const m = dateStr.match(re);
    if (m) {
        const day = m[1].padStart(2, '0');
        const monthKey = m[2].toLowerCase().substring(0, 3);
        const month = months[monthKey] || months[m[2].toLowerCase()] || '01';
        const year = m[3];
        return `${year}-${month}-${day}`;
    }

    // Try just month+year: "Ноябрь 2026"
    const re2 = /(янв|фев|мар|апр|мая|май|июн|июл|авг|сен|окт|ноя|дек)\w*\s*(\d{4})/i;
    const m2 = dateStr.match(re2);
    if (m2) {
        const monthKey = m2[1].toLowerCase().substring(0, 3);
        const month = months[monthKey] || months[m2[1].toLowerCase()] || '01';
        const year = m2[2];
        return `${year}-${month}-15`; // middle of month
    }

    // Fallback: 3 months from now
    const d = new Date();
    d.setMonth(d.getMonth() + 3);
    return d.toISOString().split('T')[0];
}

// ─── Step 3: Baseline ────────────────────────────────────────────────────────
function selectBaseline(el) {
    if (el.classList.contains('disabled')) return;

    document.querySelectorAll('.wiz-baseline-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');

    wizState.baseline = el.dataset.baseline;

    const btn = document.getElementById('btn-next-3');
    if (btn) btn.disabled = false;

    // If adaptive_test selected, redirect to test
    if (wizState.baseline === 'adaptive_test') {
        // Store state in sessionStorage so we can return
        sessionStorage.setItem('prep_wizard_state', JSON.stringify(wizState));
        // Don't redirect immediately — let user click "Далее" first
    }
}

// ─── Step 4: Summary ─────────────────────────────────────────────────────────
function populateSummary() {
    const setEl = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val || '—';
    };

    setEl('sum-olympiad', wizState.olympiadName);
    setEl('sum-stage', wizState.selectedStage);
    setEl('sum-date', wizState.targetDate ? formatDate(wizState.targetDate) : '—');

    // Calculate days
    if (wizState.targetDate) {
        const today = new Date();
        const target = new Date(wizState.targetDate);
        const days = Math.max(7, Math.min(180, Math.ceil((target - today) / 86400000)));
        setEl('sum-days', days);
        setEl('mot-days', days);
        setEl('sum-tasks', days < 30 ? '7' : '5');
    }

    setEl('sum-baseline', wizState.baseline === 'adaptive_test' ? 'Адаптивный тест' : 'Текущий Радар');
}

function formatDate(isoStr) {
    if (!isoStr) return '—';
    const months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    const d = new Date(isoStr);
    return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

// ─── Submit ──────────────────────────────────────────────────────────────────
async function submitPlan() {
    const loader = document.getElementById('wiz-loader');
    const step4 = document.getElementById('step-4');

    // Show loader
    if (step4) step4.classList.remove('active');
    if (loader) loader.classList.add('active');

    try {
        const resp = await fetch('/prep/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                olympiad_slug: wizState.olympiadSlug,
                target_stage: wizState.selectedStage || '',
                target_date: wizState.targetDate,
                use_baseline: wizState.baseline || 'radar',
            }),
        });

        const data = await resp.json();

        if (resp.ok) {
            // Success — redirect to plan detail
            window.location.href = data.redirect_url || '/prep/';
        } else {
            // Error
            alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
            if (loader) loader.classList.remove('active');
            if (step4) step4.classList.add('active');
        }
    } catch (err) {
        alert('Ошибка сети: ' + err.message);
        if (loader) loader.classList.remove('active');
        if (step4) step4.classList.add('active');
    }
}

// ─── Keyboard support ────────────────────────────────────────────────────────
document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
        const activeStep = wizState.step;
        const nextBtn = document.getElementById('btn-next-' + activeStep);
        if (nextBtn && !nextBtn.disabled) nextBtn.click();
    }
});

// ─── Restore state from sessionStorage (after adaptive test redirect) ────────
(function restoreState() {
    const saved = sessionStorage.getItem('prep_wizard_state');
    if (saved) {
        try {
            const state = JSON.parse(saved);
            Object.assign(wizState, state);
            sessionStorage.removeItem('prep_wizard_state');
            // Go to step 4 (after test)
            if (wizState.olympiadSlug && wizState.selectedStage) {
                setTimeout(() => goToStep(4), 100);
            }
        } catch (e) { /* ignore */ }
    }
})();
