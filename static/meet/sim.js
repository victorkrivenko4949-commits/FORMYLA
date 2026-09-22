/* sim.js — демонстрационные данные и имитация участников */
(function () {
  const palette = ['linear-gradient(135deg,#38bdf8,#4c7dff)', 'linear-gradient(135deg,#8b5cf6,#ec4899)', 'linear-gradient(135deg,#38ef7d,#11998e)', 'linear-gradient(135deg,#f59e0b,#ef4444)', 'linear-gradient(135deg,#6366f1,#38bdf8)', 'linear-gradient(135deg,#f472b6,#8b5cf6)', 'linear-gradient(135deg,#14b8a6,#22c55e)', 'linear-gradient(135deg,#fb7185,#f59e0b)'];
  const solid = ['#38bdf8', '#8b5cf6', '#22c55e', '#f59e0b', '#6366f1', '#ec4899', '#14b8a6', '#fb7185'];

  const people = [
    { name: 'Мария Иванова', role: 'Преподаватель геометрии', status: 'online' },
    { name: 'Пётр Смирнов', role: 'Ученик · 9 класс', status: 'online' },
    { name: 'Дарья Кузнецова', role: 'Ученица · 10 класс', status: 'away' },
    { name: 'Илья Волков', role: 'Куратор подготовки', status: 'online' },
    { name: 'Анна Соколова', role: 'Ученица · 8 класс', status: 'busy' },
    { name: 'Максим Орлов', role: 'Ученик · 11 класс', status: 'offline' },
    { name: 'Елена Морозова', role: 'Родитель', status: 'online' },
    { name: 'Тимур Ахмедов', role: 'Ученик · 9 класс', status: 'offline' },
    { name: 'Ольга Лебедева', role: 'Методист', status: 'away' },
    { name: 'Никита Павлов', role: 'Ученик · 10 класс', status: 'online' },
  ];

  const initials = n => n.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  window.SIM = {
    initials,
    palette, solid,
    contacts: people.map((p, i) => ({ ...p, id: 'c' + i, initials: initials(p.name), color: palette[i % palette.length], solid: solid[i % solid.length] })),

    // Участники для встречи (без пользователя)
    makeParticipants(n) {
      return this.contacts.slice(0, n).map((c, i) => ({
        id: c.id, name: c.name, initials: c.initials, color: c.color, solid: c.solid,
        mic: i !== 2, cam: i % 3 !== 1, hand: false, host: false, cohost: i === 0,
        speaking: false, poor: i === 4, pinned: false, spotlight: false, room: null,
      }));
    },

    waitingNames: ['Григорий Новиков', 'Светлана Фёдорова', 'Артём Козлов', 'Виктория Белова'],

    chatLines: [
      'Всем привет! Слышно нормально?',
      'Да, всё отлично 👍',
      'Можно ещё раз показать построение из задачи 3?',
      'Сейчас открою доску и нарисую',
      'Спасибо, теперь понятно',
      'А где найти условие в календаре олимпиад?',
      'Ссылка в чате: formyla.net/olympiad-prep/calendar',
      'Записываю, потом пересмотрю',
      'Можно микрофон? У меня вопрос по неравенствам',
      'Давайте сделаем опрос, кто решил задачу 5',
      'Я сейчас в дороге, буду без камеры',
      'Отлично объяснено, спасибо!',
    ],

    captionLines: [
      'Итак, рассмотрим треугольник ABC и проведём биссектрису из вершины A.',
      'Обратите внимание, что точка пересечения лежит на описанной окружности.',
      'Это ключевая идея метода вспомогательной окружности.',
      'Давайте проверим, выполняется ли равенство углов.',
      'Теперь перейдём к задаче номер пять из вчерашнего среза.',
      'Кто хочет попробовать записать решение на доске?',
      'Хорошо, у нас осталось десять минут, подведём итоги.',
    ],

    meetings: [
      { id: 'm1', topic: 'Разбор задач дня · Геометрия 9 класс', host: 'Мария Иванова', when: offset(0, 30), dur: 60, recurring: 'Ежедневно', pw: '4821', waiting: true, record: true },
      { id: 'm2', topic: 'Куратор подготовки: индивидуальная консультация', host: 'Илья Волков', when: offset(0, 150), dur: 45, recurring: null, pw: '', waiting: false, record: false },
      { id: 'm3', topic: 'Вебинар «102 метода олимпиадной математики»: метод крайнего', host: 'Ольга Лебедева', when: offset(1, 60), dur: 90, recurring: 'Еженедельно, ср', pw: '7710', waiting: true, record: true },
      { id: 'm4', topic: 'Родительское собрание: план на четверть', host: 'Мария Иванова', when: offset(2, 120), dur: 40, recurring: null, pw: '', waiting: true, record: false },
    ],

    recordings: [
      { id: 'r1', topic: 'Разбор задач дня · Комбинаторика', date: offset(-1, -600), dur: '58:12', size: '412 МБ', src: null, demo: true },
      { id: 'r2', topic: 'Метод математической индукции', date: offset(-3, -300), dur: '1:24:05', size: '980 МБ', src: null, demo: true },
    ],
  };

  function offset(days, minutes) {
    const d = new Date(); d.setDate(d.getDate() + days); d.setMinutes(d.getMinutes() + minutes); d.setSeconds(0, 0); return d;
  }
  window.genMeetingId = () => `${rnd(100, 999)} ${rnd(1000, 9999)} ${rnd(1000, 9999)}`;
  function rnd(a, b) { return Math.floor(a + Math.random() * (b - a + 1)); }
  window.rnd = rnd;
})();
