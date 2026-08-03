/**
 * paywall.js — Модалка paywall для FORMYLA
 *
 * Использование:
 *   showPaywall({ feature, message, usage_today, limit, current_plan, upgrade_price })
 *
 * Вызывается автоматически из api.js при получении 403 с error='limit_reached'
 */

(function () {
    'use strict';

    // ── Создаём DOM модалки один раз ─────────────────────────────────────────

    function createPaywallModal() {
        if (document.getElementById('paywallModal')) return;

        const style = document.createElement('style');
        style.textContent = `
            #paywallOverlay {
                display: none;
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.75);
                backdrop-filter: blur(6px);
                z-index: 9999;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            #paywallOverlay.active { display: flex; }

            #paywallModal {
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                border: 1px solid rgba(56, 239, 125, 0.3);
                border-radius: 20px;
                padding: 36px 32px;
                max-width: 440px;
                width: 100%;
                box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6), 0 0 40px rgba(56, 239, 125, 0.08);
                position: relative;
                animation: paywallIn 0.25s ease;
            }

            @keyframes paywallIn {
                from { opacity: 0; transform: scale(0.92) translateY(16px); }
                to   { opacity: 1; transform: scale(1) translateY(0); }
            }

            #paywallModal .pw-close {
                position: absolute;
                top: 16px;
                right: 16px;
                background: none;
                border: none;
                color: #64748b;
                font-size: 20px;
                cursor: pointer;
                line-height: 1;
                padding: 4px 8px;
                border-radius: 6px;
                transition: color 0.2s, background 0.2s;
            }
            #paywallModal .pw-close:hover { color: #f1f5f9; background: rgba(255,255,255,0.08); }

            #paywallModal .pw-icon {
                font-size: 2.8em;
                text-align: center;
                margin-bottom: 12px;
            }

            #paywallModal .pw-title {
                font-size: 1.4em;
                font-weight: 800;
                color: #f1f5f9;
                text-align: center;
                margin-bottom: 8px;
            }

            #paywallModal .pw-message {
                font-size: 0.95em;
                color: #94a3b8;
                text-align: center;
                line-height: 1.5;
                margin-bottom: 20px;
            }

            #paywallModal .pw-usage-bar {
                background: rgba(255,255,255,0.06);
                border-radius: 8px;
                height: 8px;
                margin-bottom: 6px;
                overflow: hidden;
            }
            #paywallModal .pw-usage-fill {
                height: 100%;
                background: linear-gradient(90deg, #38ef7d, #11998e);
                border-radius: 8px;
                transition: width 0.4s ease;
            }
            #paywallModal .pw-usage-label {
                font-size: 0.8em;
                color: #64748b;
                text-align: right;
                margin-bottom: 20px;
            }

            #paywallModal .pw-features {
                list-style: none;
                padding: 0;
                margin: 0 0 24px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            #paywallModal .pw-features li {
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 0.9em;
                color: #cbd5e1;
            }
            #paywallModal .pw-features li .pw-feat-icon { color: #38ef7d; }

            #paywallModal .pw-btn-primary {
                display: block;
                width: 100%;
                padding: 14px 24px;
                background: linear-gradient(135deg, #38ef7d 0%, #11998e 100%);
                color: #0f172a;
                font-weight: 800;
                font-size: 1em;
                border: none;
                border-radius: 12px;
                cursor: pointer;
                text-align: center;
                text-decoration: none;
                transition: transform 0.2s, box-shadow 0.2s;
                box-shadow: 0 4px 20px rgba(56, 239, 125, 0.3);
                margin-bottom: 10px;
            }
            #paywallModal .pw-btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 28px rgba(56, 239, 125, 0.4);
            }

            #paywallModal .pw-btn-secondary {
                display: block;
                width: 100%;
                padding: 10px 24px;
                background: transparent;
                color: #64748b;
                font-size: 0.9em;
                border: none;
                cursor: pointer;
                text-align: center;
                transition: color 0.2s;
            }
            #paywallModal .pw-btn-secondary:hover { color: #94a3b8; }

            #paywallModal .pw-price-note {
                text-align: center;
                font-size: 0.8em;
                color: #475569;
                margin-top: 8px;
            }
        `;
        document.head.appendChild(style);

        const overlay = document.createElement('div');
        overlay.id = 'paywallOverlay';
        overlay.innerHTML = `
            <div id="paywallModal">
                <button class="pw-close" onclick="hidePaywall()" aria-label="Закрыть"></button>
                <div class="pw-icon" id="pwIcon"></div>
                <div class="pw-title" id="pwTitle">Лимит достигнут</div>
                <div class="pw-message" id="pwMessage"></div>
                <div class="pw-usage-bar" id="pwUsageBarWrap" style="display:none">
                    <div class="pw-usage-fill" id="pwUsageFill" style="width:0%"></div>
                </div>
                <div class="pw-usage-label" id="pwUsageLabel"></div>
                <ul class="pw-features">
                    <li><span class="pw-feat-icon"></span> Безлимит задач (до 500/день)</li>
                    <li><span class="pw-feat-icon"></span> Безлимит AI-разборов (до 200/мес)</li>
                    <li><span class="pw-feat-icon"></span> Расширенные разборы (8000 токенов)</li>
                    <li><span class="pw-feat-icon"></span> История тестов навсегда</li>
                </ul>
                <a href="/subscribe" class="pw-btn-primary" id="pwUpgradeBtn">
                     Попробовать Premium бесплатно
                </a>
                <button class="pw-btn-secondary" onclick="hidePaywall()">
                    Продолжить с бесплатным тарифом
                </button>
                <div class="pw-price-note" id="pwPriceNote">390 руб/мес · сейчас бесплатно в бета</div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Закрытие по клику на оверлей
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) hidePaywall();
        });

        // Закрытие по Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') hidePaywall();
        });
    }

    // ── Публичные функции ─────────────────────────────────────────────────────

    /**
     * Показать paywall модалку.
     *
     * @param {Object} opts
     * @param {string} opts.feature        - 'task' | 'ai_explanation'
     * @param {string} opts.message        - Текст ошибки от сервера
     * @param {number} opts.usage_today    - Использовано сегодня
     * @param {number} opts.limit          - Лимит
     * @param {string} opts.current_plan   - 'free' | 'premium_monthly'
     * @param {string} opts.upgrade_price  - '390 руб/мес'
     * @param {string} opts.upgrade_url    - '/subscribe'
     */
    window.showPaywall = function (opts) {
        createPaywallModal();

        const overlay = document.getElementById('paywallOverlay');
        const icon = document.getElementById('pwIcon');
        const title = document.getElementById('pwTitle');
        const msg = document.getElementById('pwMessage');
        const barWrap = document.getElementById('pwUsageBarWrap');
        const fill = document.getElementById('pwUsageFill');
        const label = document.getElementById('pwUsageLabel');
        const upgradeBtn = document.getElementById('pwUpgradeBtn');
        const priceNote = document.getElementById('pwPriceNote');

        // Иконка и заголовок по типу фичи
        if (opts.feature === 'ai_explanation') {
            icon.textContent = '';
            title.textContent = 'Лимит AI-разборов исчерпан';
        } else if (opts.feature === 'task') {
            icon.textContent = '';
            title.textContent = 'Лимит задач на сегодня';
        } else {
            icon.textContent = '';
            title.textContent = 'Лимит достигнут';
        }

        // Сообщение
        msg.textContent = opts.message || 'Оформите Premium для продолжения.';

        // Прогресс-бар
        if (opts.usage_today !== undefined && opts.limit) {
            const pct = Math.min(100, Math.round(opts.usage_today / opts.limit * 100));
            barWrap.style.display = 'block';
            fill.style.width = pct + '%';
            label.textContent = `Использовано: ${opts.usage_today} / ${opts.limit}`;
        } else {
            barWrap.style.display = 'none';
            label.textContent = '';
        }

        // Кнопка
        if (opts.upgrade_url) {
            upgradeBtn.href = opts.upgrade_url;
        }

        // Цена
        if (opts.upgrade_price) {
            priceNote.textContent = opts.upgrade_price + ' · сейчас бесплатно в бета';
        }

        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    };

    window.hidePaywall = function () {
        const overlay = document.getElementById('paywallOverlay');
        if (overlay) {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    };

})();
