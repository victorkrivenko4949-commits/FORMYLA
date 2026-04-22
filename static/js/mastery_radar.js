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

    new Chart(el, {
        type: 'radar',
        data: {
            labels: data.map(d => d.name),
            datasets: [{
                label: 'Уровень',
                data: data.map(d => Math.round(d.value * 100)),
                backgroundColor: 'rgba(56,239,125,0.2)',
                borderColor: '#38ef7d',
                pointBackgroundColor: '#38ef7d',
                pointBorderColor: '#000',
                pointRadius: 5,
                pointHoverRadius: 7,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.r.toFixed(0)}%`
                    }
                }
            },
            scales: {
                r: {
                    min: 0,
                    max: 100,
                    ticks: {
                        stepSize: 20,
                        color: 'rgba(255,255,255,0.4)',
                        backdropColor: 'transparent',
                        font: { size: 10 }
                    },
                    grid:       { color: 'rgba(56,239,125,0.15)' },
                    angleLines: { color: 'rgba(56,239,125,0.2)' },
                    pointLabels: {
                        color: '#38ef7d',
                        font: { size: 13, weight: '600' }
                    }
                }
            }
        }
    });
});
