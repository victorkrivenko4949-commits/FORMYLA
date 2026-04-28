/**
 * profile_view.js — SPA-загрузка профиля друга
 * Fetch /api/profile/<nickname> → рендер секций
 */
(function () {
    'use strict';

    /* ── Утилиты ── */

    function escapeHtml(str) {
        if (!str) return '';
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(str));
        return d.innerHTML;
    }

    function formatTime(sec) {
        if (sec == null) return '—';
        if (sec < 60) return sec + ' с';
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function formatDate(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        var dd = d.getDate();
        var months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
                      'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
        return dd + ' ' + months[d.getMonth()];
    }

    function $(id) { return document.getElementById(id); }

    /* ── Инициализация ── */

    var root = document.getElementById('profile-view-app');
    if (!root) return;

    var nickname = root.getAttribute('data-nickname');
    if (!nickname) return;

    var elLoading = $('pv-loading');
    var elError   = $('pv-error');
    var elErrMsg  = $('pv-error-msg');
    var elContent = $('pv-content');

    function showError(msg) {
        elLoading.style.display = 'none';
        elContent.style.display = 'none';
        elErrMsg.textContent = msg;
        elError.style.display = 'block';
    }

    function showContent() {
        elLoading.style.display = 'none';
        elError.style.display = 'none';
        elContent.style.display = 'block';
    }

    /* ── Fetch данных ── */

    fetch('/api/profile/' + encodeURIComponent(nickname))
        .then(function (res) {
            if (res.status === 404) throw { code: 404, msg: 'Пользователь не найден' };
            if (res.status === 403) throw { code: 403, msg: 'Доступ запрещён — вы не друзья' };
            if (!res.ok) throw { code: res.status, msg: 'Ошибка загрузки (' + res.status + ')' };
            return res.json();
        })
        .then(function (data) {
            renderProfile(data);
            showContent();
        })
        .catch(function (err) {
            var msg = (err && err.msg) ? err.msg : 'Не удалось загрузить профиль';
            showError(msg);
        });

    /* ── Рендер профиля ── */

    function renderProfile(d) {
        // Header
        var avatarEl = $('pv-avatar');
        avatarEl.src = d.avatar_url || '/static/default_avatar.png';
        avatarEl.onerror = function () { this.src = '/static/default_avatar.png'; };

        $('pv-nickname').textContent = '@' + escapeHtml(d.nickname || '');
        $('pv-name').textContent = d.name || '';

        // Stats
        var r = d.rating || {};
        $('pv-level').textContent = r.current_level || 1;
        $('pv-xp').textContent = (r.experience_points || 0).toLocaleString('ru-RU');
        $('pv-solved').textContent = (r.total_problems_solved || 0).toLocaleString('ru-RU');

        var s = d.streak || {};
        $('pv-streak').textContent = s.current || 0;

        // Topics
        renderTopics(d.progress_by_topic || []);

        // Heatmap
        renderHeatmap(d.activity_30d || []);

        // Recent
        renderRecent(d.recent_results || []);
    }

    /* ── Topics bars ── */

    function renderTopics(topics) {
        var wrap = $('pv-topics');
        var empty = $('pv-topics-empty');
        if (!topics.length) { empty.style.display = 'block'; return; }

        var html = '';
        for (var i = 0; i < topics.length; i++) {
            var t = topics[i];
            var pct = t.accuracy || 0;
            html += '<div class="pv-topic-row">'
                + '<span class="pv-topic-name">' + escapeHtml(t.topic_name_ru) + '</span>'
                + '<div class="pv-topic-bar-wrap">'
                + '  <div class="pv-topic-bar" style="width:' + pct + '%"></div>'
                + '</div>'
                + '<span class="pv-topic-pct">' + pct + '%</span>'
                + '<span class="pv-topic-detail">ур.' + (t.current_level || '—')
                + ' · ' + (t.tasks_correct || 0) + '/' + (t.tasks_attempted || 0) + '</span>'
                + '</div>';
        }
        wrap.innerHTML = html;
    }

    /* ── Heatmap 30 дней ── */

    function renderHeatmap(days) {
        var wrap = $('pv-heatmap');
        if (!days.length) { wrap.innerHTML = '<p class="pv-empty">Нет данных</p>'; return; }

        // Определяем макс для уровней
        var maxCount = 1;
        for (var i = 0; i < days.length; i++) {
            if (days[i].count > maxCount) maxCount = days[i].count;
        }

        var html = '';
        for (var i = 0; i < days.length; i++) {
            var c = days[i].count;
            var level = 0;
            if (c > 0) {
                var ratio = c / maxCount;
                if (ratio <= 0.25) level = 1;
                else if (ratio <= 0.5) level = 2;
                else if (ratio <= 0.75) level = 3;
                else level = 4;
            }
            var dateLabel = formatDate(days[i].date);
            html += '<div class="pv-hm-cell" data-level="' + level + '">'
                + '<span class="pv-tooltip">' + dateLabel + ': ' + c + ' задач</span>'
                + '</div>';
        }
        wrap.innerHTML = html;

        // Легенда
        var legend = document.createElement('div');
        legend.className = 'pv-heatmap-legend';
        legend.innerHTML = '<span>Меньше</span>'
            + '<span class="pv-hm-legend-box" style="background:#252545"></span>'
            + '<span class="pv-hm-legend-box" style="background:rgba(56,239,125,.2)"></span>'
            + '<span class="pv-hm-legend-box" style="background:rgba(56,239,125,.4)"></span>'
            + '<span class="pv-hm-legend-box" style="background:rgba(56,239,125,.6)"></span>'
            + '<span class="pv-hm-legend-box" style="background:rgba(56,239,125,.85)"></span>'
            + '<span>Больше</span>';
        wrap.parentNode.appendChild(legend);
    }

    /* ── Recent results ── */

    function renderRecent(results) {
        var wrap = $('pv-recent');
        var empty = $('pv-recent-empty');
        if (!results.length) { empty.style.display = 'block'; return; }

        var typeLabels = {
            'adaptive': 'Адаптивный',
            'mock': 'Пробник',
            'daily': 'Ежедневная',
            'practice': 'Практика'
        };

        var html = '';
        for (var i = 0; i < results.length; i++) {
            var r = results[i];
            var icon = r.is_correct ? '✅' : '❌';
            var topicText = escapeHtml(r.topic || typeLabels[r.test_type] || r.test_type || '—');
            var diffText = r.difficulty ? ('ур.' + r.difficulty) : '';
            var timeText = formatTime(r.time_spent_sec);
            var dateText = formatDate(r.created_at);

            html += '<div class="pv-result-row">'
                + '<span class="pv-result-icon">' + icon + '</span>'
                + '<span class="pv-result-topic">' + topicText + '</span>'
                + '<span class="pv-result-diff">' + diffText + '</span>'
                + '<span class="pv-result-time">' + timeText + '</span>'
                + '<span class="pv-result-date">' + dateText + '</span>'
                + '</div>';
        }
        wrap.innerHTML = html;
    }

})();
