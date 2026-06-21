// Mastery Radar Chart - FORMYLA
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

const values = data.map(d => Math.round((d.value || 0) * 8));
const names = data.map(d => d.name || '');
// Wrap long topic labels into multiple lines so they are not clipped
function wrapLabel(label, maxLen) {
const words = String(label).split(' ');
const lines = [];
let cur = '';
for (const w of words) {
if ((cur + ' ' + w).trim().length > maxLen && cur) {
lines.push(cur.trim());
cur = w;
} else {
cur = (cur + ' ' + w).trim();
}
}
if (cur) lines.push(cur.trim());
return lines;
}
const wrappedLabels = names.map(n => wrapLabel(n, 16));

const pointColors = values.map(v => {
    if (v >= 6) return '#38ef7d';
    if (v >= 3) return '#fbbf24';
    if (v > 0) return '#f87171';
    return 'rgba(255,255,255,0.25)';
});

const pointRadius = values.map(v => v > 0 ? 6 : 4);

new Chart(el, {
type: 'radar',
data: {
labels: wrappedLabels,
datasets: [{
label: 'Uroven',
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
layout: { padding: 24 },
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
title: (items) => {
if (!items.length) return '';
const lbl = items[0].label;
return Array.isArray(lbl) ? lbl.join(' ') : lbl;
},
label: (ctx) => {
const v = ctx.parsed.r;
if (v === 0) return 'Ne proydeno';
return `${v.toFixed(0)}%`;
}
}
}
},
scales: {
r: {
      min: 1,
      max: 8,
ticks: {
        stepSize: 1,
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
          if (v >= 6) return '#38ef7d';
          if (v >= 3) return '#fbbf24';
if (v > 0) return '#f87171';
return 'rgba(255,255,255,0.45)';
},
font: { size: 12, weight: '600' },
padding: 10,
}
}
}
}
});
});
