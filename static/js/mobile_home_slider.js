/* ════════════════════════════════════════════════════════════════════════
 * mobile_home_slider.js
 * Мобильный «свайп-пейджер» главных разделов FORMYLA для шаблона "/".
 *
 * Подключается из templates/base.html с defer. Работает только на ≤768px;
 * на десктопе блок .mhome скрыт через CSS (.m-only), скрипт просто
 * молча выходит из init().
 *
 * Логика:
 *   - тач/мышь свайпает горизонтальную ленту .mhome-track (CSS scroll-snap);
 *   - JS только синхронизирует точки-индикатор + клавиатура + ARIA;
 *   - активный слайд сохраняется в sessionStorage между переходами.
 *
 * Никаких зависимостей.
 * ════════════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var STORE_KEY = 'mhome:lastSlide';
    var MOBILE_MAX = 768; // px

    function init() {
        var root  = document.getElementById('mHome');
        var track = document.getElementById('mHomeTrack');
        var dotsBox = document.getElementById('mHomeDots');
        if (!root || !track || !dotsBox) return;

        var slides = track.querySelectorAll('.mhome-slide');
        var dots   = dotsBox.querySelectorAll('.mhome-dot');
        if (!slides.length || slides.length !== dots.length) return;

        var current = 0;
        var pending = null;

        /* ── Восстановить активный слайд после возврата на страницу ─── */
        try {
            var saved = parseInt(sessionStorage.getItem(STORE_KEY) || '0', 10);
            if (saved > 0 && saved < slides.length) {
                // мгновенно, без анимации, чтобы пользователь сразу увидел нужную страницу
                track.style.scrollBehavior = 'auto';
                track.scrollLeft = slides[saved].offsetLeft;
                requestAnimationFrame(function () { track.style.scrollBehavior = ''; });
                current = saved;
                setActive(saved);
            }
        } catch (e) { /* sessionStorage может быть недоступен */ }

        /* ── Подсветка активной точки + ARIA ──────────────────────── */
        function setActive(idx) {
            current = idx;
            for (var i = 0; i < dots.length; i++) {
                var isActive = (i === idx);
                dots[i].classList.toggle('is-active', isActive);
                dots[i].setAttribute('aria-selected', isActive ? 'true' : 'false');
            }
            for (var j = 0; j < slides.length; j++) {
                slides[j].setAttribute('aria-hidden', j === idx ? 'false' : 'true');
            }
            try { sessionStorage.setItem(STORE_KEY, String(idx)); } catch (e) {}
        }

        /* ── Расчёт текущего слайда по scrollLeft (throttle через rAF) ── */
        function onScroll() {
            if (pending !== null) return;
            pending = requestAnimationFrame(function () {
                pending = null;
                var w = track.clientWidth;
                if (w <= 0) return;
                var idx = Math.round(track.scrollLeft / w);
                if (idx < 0) idx = 0;
                if (idx >= slides.length) idx = slides.length - 1;
                if (idx !== current) setActive(idx);
            });
        }
        track.addEventListener('scroll', onScroll, { passive: true });

        /* ── Клик/тап по точке -> программно листаем ──────────────── */
        dots.forEach(function (dot, i) {
            dot.addEventListener('click', function () {
                var slide = slides[i];
                if (!slide) return;
                track.scrollTo({ left: slide.offsetLeft, behavior: 'smooth' });
            });
        });

        /* ── Клавиатура (<-/->/Home/End), когда трек в фокусе ───── */
        track.addEventListener('keydown', function (e) {
            var key = e.key;
            var target = null;
            if (key === 'ArrowRight') target = Math.min(current + 1, slides.length - 1);
            else if (key === 'ArrowLeft') target = Math.max(current - 1, 0);
            else if (key === 'Home') target = 0;
            else if (key === 'End') target = slides.length - 1;
            if (target === null) return;
            e.preventDefault();
            track.scrollTo({ left: slides[target].offsetLeft, behavior: 'smooth' });
        });

        /* ── Resize: пересчитать позицию (на смену ориентации/брейкпоинта) ── */
        window.addEventListener('resize', function () {
            // если ушли в десктоп — сбрасываем scrollLeft, чтобы не залипал слайд
            if (window.innerWidth > MOBILE_MAX) {
                track.scrollLeft = 0;
                return;
            }
            // сохранить текущий активный слайд при ресайзе телефона/планшета
            var slide = slides[current];
            if (slide) {
                track.style.scrollBehavior = 'auto';
                track.scrollLeft = slide.offsetLeft;
                requestAnimationFrame(function () { track.style.scrollBehavior = ''; });
            }
        }, { passive: true });

        /* первая синхронизация */
        onScroll();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
