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

// Values now come in canonical 1..4 scale from level_by_section mu.
// If the data was already 0..4 (from level_engine), use directly.
// If data appears in 0..1 scale (old TopicMastery), map to 1..4.
const values = data.map(d => {
    const v = d.value || 0;
    // Heuristic: if all values <= 1.0, treat as 0..1 ratio and scale to 4
    if (v <= 1.0 && data.every(dd => (dd.value || 0) <= 1.0)) {
        return Math.round(v * 4);
    }
    // Already in 1..4 scale from level_engine
    return Math.round(v);
});
const names = data.map(d => d.name || '');
// Wrap long topic labels into multiple lines so they are not clipped
function wrapLabel(label, maxLen) {
const s = String(label);
// If label is a single long word, break it into pieces
if (!s.includes(' ')) {
const lines = [];
for (let i = 0; i < s.length; i += maxLen) {
lines.push(s.slice(i, i + maxLen));
}
return lines;
}
const words = s.split(' ');
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
const wrappedLabels = names.map(n => wrapLabel(n, 14));

const pointColors = values.map(v => {
    if (v >= 4) return '#38ef7d';
    if (v >= 2) return '#fbbf24';
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
      max: 4,
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
          if (v >= 4) return '#38ef7d';
          if (v >= 2) return '#fbbf24';
if (v > 0) return '#f87171';
return 'rgba(255,255,255,0.45)';
},
font: { size: 11, weight: '600' },
padding: 10,
}
}
}
}
});
});
