/**
 * progress.js — График прогресса адаптивных тестов (Chart.js)
 * Открывается из профиля по кнопке "📈 Посмотреть прогресс"
 */

/** @type {Chart | null} */
let progressChartInstance = null;

/**
 * Открыть модальное окно с графиком прогресса
 */
function openProgressModal() {
    const overlay = document.getElementById('progressModal');
    const loading = document.getElementById('progressLoading');
    const chartWrapper = document.querySelector('.progress-chart-wrapper');
    const empty = document.getElementById('progressEmpty');
    const canvas = document.getElementById('progressChart');

    if (!overlay) return;

    // Сброс состояния
    overlay.classList.add('active');
    if (loading) loading.style.display = 'block';
    if (chartWrapper) chartStyle(chartWrapper, 'none');
    if (empty) empty.style.display = 'none';

    // Уничтожить старый график
    destroyChart();

    // Получить user_id из data-атрибута или URL
    const userId = getUserId();

    fetch(`/api/progress/${userId}`)
        .then(function (res) {
            if (!res.ok) {
                if (res.status === 403) throw new Error('Доступ запрещён');
                throw new Error('Ошибка загрузки данных');
            }
            return res.json();
        })
        .then(function (data) {
            if (loading) loading.style.display = 'none';

            if (!data.labels || data.labels.length === 0 || !data.datasets || data.datasets.length === 0) {
                // Нет данных
                if (empty) empty.style.display = 'block';
                return;
            }

            // Показываем canvas
            if (chartWrapper) chartWrapper.style.display = 'block';

            renderChart(canvas, data);
        })
        .catch(function (err) {
            console.error('[Progress]', err);
            if (loading) loading.style.display = 'none';
            if (empty) {
                empty.querySelector('p').textContent = '⚠️ ' + (err.message || 'Ошибка загрузки');
                empty.style.display = 'block';
            }
        });
}

/**
 * Закрыть модальное окно
 */
function closeProgressModal(event) {
    if (event && event.target !== document.getElementById('progressModal')) return;
    const overlay = document.getElementById('progressModal');
    if (overlay) overlay.classList.remove('active');
    destroyChart();
}

/**
 * Уничтожить экземпляр Chart.js
 */
function destroyChart() {
    if (progressChartInstance) {
        progressChartInstance.destroy();
        progressChartInstance = null;
    }
}

/**
 * Отрендерить линейный график
 */
function renderChart(canvas, data) {
    if (!canvas) return;

    var ctx = canvas.getContext('2d');
    if (!ctx) return;

    var isDark = document.documentElement.getAttribute('data-theme') !== 'light'
        || window.matchMedia('(prefers-color-scheme: dark)').matches;

    var gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
    var textColor = isDark ? '#cbd5e1' : '#475569';

    // Определяем, сколько точек на оси X
    var pointCount = data.labels ? data.labels.length : 0;

    progressChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: data.datasets.map(function (ds) {
                return {
                    label: ds.label,
                    data: ds.data,
                    borderColor: ds.borderColor,
                    backgroundColor: ds.backgroundColor || (ds.borderColor + '33'),
                    tension: ds.tension !== undefined ? ds.tension : 0.3,
                    spanGaps: ds.spanGaps !== undefined ? ds.spanGaps : true,
                    pointRadius: pointCount <= 2 ? 6 : (ds.pointRadius || 4),
                    pointHoverRadius: ds.pointHoverRadius || 7,
                    pointBackgroundColor: ds.borderColor,
                    pointBorderColor: isDark ? '#1e293b' : '#ffffff',
                    pointBorderWidth: 2,
                    fill: false,
                    borderWidth: 2
                };
            })
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: textColor,
                        padding: 16,
                        usePointStyle: true,
                        boxWidth: 10,
                        font: { size: 12 }
                    }
                },
                tooltip: {
                    backgroundColor: isDark ? '#1e293b' : '#ffffff',
                    titleColor: isDark ? '#f1f5f9' : '#0f172a',
                    bodyColor: textColor,
                    borderColor: isDark ? '#334155' : '#e2e8f0',
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: function (context) {
                            var val = context.parsed.y;
                            if (val === null || val === undefined) return context.dataset.label + ': —';
                            return context.dataset.label + ': ' + val.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    ticks: {
                        color: textColor,
                        maxRotation: 45,
                        font: { size: 11 }
                    }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: gridColor },
                    ticks: {
                        color: textColor,
                        stepSize: 20,
                        callback: function (value) {
                            return value + '%';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Правильных ответов (%)',
                        color: textColor,
                        font: { size: 11 }
                    }
                }
            }
        }
    });
}

/**
 * Получить user_id для API запроса
 */
function getUserId() {
    // Пытаемся найти user_id из data-атрибута на body (если есть)
    var body = document.body;
    if (body && body.dataset && body.dataset.userId) {
        return parseInt(body.dataset.userId, 10);
    }

    // Иначе берём из глобальной переменной (если установлена)
    if (typeof CURRENT_USER_ID !== 'undefined') {
        return CURRENT_USER_ID;
    }

    // fallback: парсим из URL профиля
    return window.location.pathname === '/profile'
        ? 0  // сервер сам поймёт current_user
        : 0;
}

/**
 * Хелпер для установки style.display
 */
function chartStyle(el, display) {
    if (el) el.style.display = display;
}

// Закрытие по Escape
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        closeProgressModal();
    }
});
