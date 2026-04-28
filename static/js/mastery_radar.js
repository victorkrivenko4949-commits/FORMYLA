// Mastery Radar Chart — FORMYLA
document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById('masteryRadar');
    if (!el) return;

    let data;
    try {
        data = JSON.parse(el.dataset.mastery || '[]');
    } catch (e) {
        console.error('Failed to parse mastery data:', e);
        return;
    }

    if (!data || data.length === 0) return;

    // Determine which topics are "passed" (value > 0) vs "not passed"
    const values = data.map(d => Math.round(d.value * 100));
    const maxVal = Math.max(...values, 1);

    // Dynamic colors: strong topics get solid fill, weak ones get dashed look
    const pointColors = values.map(v => {
        if (v >= 60) return '#38ef7d';      // strong — green
        if (v >= 30) return '#fbbf24';      // medium — yellow
        if (v > 0)   return '#f87171';      // weak — red
        return 'rgba(255,255,255,0.25)';    // not started — dim
    });

    const pointRadius = values.map(v => v > 0 ? 6 : 4);

    new Chart(el, {
        type: 'radar',
        data: {
            labels: data.map(d => d.name),
            datasets: [{
                label: 'Уровень',
                data: values,
                backgroundColor: 'rgba(56,239,125,0.12)',
                borderColor: '#38ef7d',
                pointBackgroundColor: pointColors,
                pointBorderColor: pointColors.map(c =>
                    c === 'rgba(255,255,255,0.25)' ? 'rgba(255,255,255,0.4)' : '#000'
                ),
                pointRadius: pointRadius,
                pointHoverRadius: 8,
                borderWidth: 2.5,
                pointStyle: values.map(v => v > 0 ? 'circle' : 'crossRot'),
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(10,15,25,0.9)',
                    titleColor: '#38ef7d',
                    bodyColor: '#fff',
                    borderColor: 'rgba(56,239,125,0.3)',
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: (ctx) => {
                            const v = ctx.parsed.r;
                            if (v === 0) return '✗ Не пройдено';
                            return `${v.toFixed(0)}%`;
                        }
                    }
                }
            },
            scales: {
                r: {
                    min: 0,
                    max: 100,
                    ticks: {
                        stepSize: 20,
                        color: 'rgba(255,255,255,0.3)',
                        backdropColor: 'transparent',
                        font: { size: 10 }
                    },
                    grid: {
                        color: 'rgba(56,239,125,0.12)',
                        lineWidth: 1,
                    },
                    angleLines: {
                        color: 'rgba(56,239,125,0.18)',
                        lineWidth: 1,
                    },
                    pointLabels: {
                        color: (ctx) => {
                            const v = values[ctx.index] || 0;
                            if (v >= 60) return '#38ef7d';
                            if (v >= 30) return '#fbbf24';
                            if (v > 0)   return '#f87171';
                            return 'rgba(255,255,255,0.45)';
                        },
                        font: {
                            size: 13,
                            weight: '600'
                        },
                        padding: 14,
                    }
                }
            }
        }
    });
});
