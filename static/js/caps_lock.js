/**
 * Глобальный Caps Lock для полей ввода ответов и решений
 * Поддерживает кириллицу и сохраняет позицию курсора
 */

// Глобальный флаг состояния Caps Lock
window.capsLockOn = false;

/**
 * Переключает состояние Caps Lock и обновляет UI всех кнопок
 */
function toggleCapsLock() {
    window.capsLockOn = !window.capsLockOn;
    
    // Обновляем все кнопки Caps Lock на странице
    const buttons = document.querySelectorAll('.caps-toggle-btn');
    buttons.forEach(btn => {
        if (window.capsLockOn) {
            btn.classList.add('active');
            btn.setAttribute('aria-pressed', 'true');
            btn.title = 'Caps Lock включен (нажмите для выключения)';
        } else {
            btn.classList.remove('active');
            btn.setAttribute('aria-pressed', 'false');
            btn.title = 'Caps Lock выключен (нажмите для включения)';
        }
    });
    
    console.log(`[Caps Lock] ${window.capsLockOn ? 'Включен' : 'Выключен'}`);
}

/**
 * Обработчик ввода для автоматического преобразования в uppercase
 * @param {Event} event - событие input
 */
function handleCapsLockInput(event) {
    if (!window.capsLockOn) return;
    
    const input = event.target;
    const start = input.selectionStart;
    const end = input.selectionEnd;
    
    // Преобразуем текст в uppercase (работает для кириллицы)
    const newValue = input.value.toUpperCase();
    
    // Обновляем значение только если оно изменилось
    if (input.value !== newValue) {
        input.value = newValue;
        
        // Восстанавливаем позицию курсора
        input.setSelectionRange(start, end);
    }
}

/**
 * Инициализация Caps Lock функционала
 * Вызывается автоматически при загрузке страницы
 */
function initCapsLock() {
    // Находим все поля ввода ответов и решений
    const inputs = document.querySelectorAll('.answer-input, .solution-input, input[name="answer"], textarea[name="solution"]');
    
    // Добавляем обработчик input для каждого поля
    inputs.forEach(input => {
        input.addEventListener('input', handleCapsLockInput);
    });
    
    // Добавляем обработчик клика для всех кнопок Caps Lock
    const buttons = document.querySelectorAll('.caps-toggle-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleCapsLock();
        });
    });
    
    console.log(`[Caps Lock] Инициализировано для ${inputs.length} полей ввода`);
}

// Автоматическая инициализация при загрузке DOM
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCapsLock);
} else {
    // DOM уже загружен
    initCapsLock();
}

// Экспорт для использования в других скриптах
window.toggleCapsLock = toggleCapsLock;
window.initCapsLock = initCapsLock;
