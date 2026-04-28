ам# -*- coding: utf-8 -*-
"""Скрипт для записи templates/friends.html с кликабельными карточками"""

TEMPLATE = r"""{% extends "base.html" %}
{% block title %}Друзья — FORMYLA{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/friends.css') }}?v={{ asset_version }}">
{% endblock %}

{% block content %}
<div class="friends-page">

  <div class="friends-hero">
    <h1>👥 Мои друзья</h1>
    <p>Соревнуйся с друзьями и достигай новых высот вместе!</p>
  </div>

  <!-- ══ Входящие запросы ══ -->
  {% if incoming %}
  <section class="friends-section">
    <h2>📩 Тебя хотят добавить <span class="count-badge">{{ incoming|length }}</span></h2>
    <div class="requests-grid">
      {% for req in incoming %}
      <article class="request-card">
        <div class="req-avatar">
          {% if req.requester.avatar_url %}
          <img src="{{ req.requester.avatar_url }}" alt="avatar" class="avatar">
          {% else %}
          <div class="avatar-placeholder">{{ (req.requester.name or req.requester.email)[0].upper() }}</div>
          {% endif %}
        </div>
        <div class="req-info">
          <h3>{{ req.requester.name or req.requester.email }}</h3>
          {% if req.requester.nickname %}<p class="req-nick">@{{ req.requester.nickname }}</p>{% endif %}
          <p class="req-stats">Уровень {{ req.requester.current_level }} · {{ req.requester.experience_points }} XP</p>
        </div>
        <div class="req-actions">
          <button class="btn-accept" data-rid="{{ req.id }}" onclick="acceptRequest(this)">✅ Принять</button>
          <button class="btn-decline" data-rid="{{ req.id }}" onclick="declineRequest(this)">❌ Отклонить</button>
        </div>
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <!-- ══ Отправленные запросы ══ -->
  {% if outgoing %}
  <section class="friends-section">
    <h2>📤 Ожидают ответа <span class="count-badge">{{ outgoing|length }}</span></h2>
    <div class="requests-grid">
      {% for req in outgoing %}
      <article class="request-card">
        <div class="req-avatar">
          {% if req.addressee.avatar_url %}
          <img src="{{ req.addressee.avatar_url }}" alt="avatar" class="avatar">
          {% else %}
          <div class="avatar-placeholder">{{ (req.addressee.name or req.addressee.email)[0].upper() }}</div>
          {% endif %}
        </div>
        <div class="req-info">
          <h3>{{ req.addressee.name or req.addressee.email }}</h3>
          {% if req.addressee.nickname %}<p class="req-nick">@{{ req.addressee.nickname }}</p>{% endif %}
        </div>
        <button class="btn-cancel" data-rid="{{ req.id }}" onclick="cancelRequest(this)">Отменить</button>
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <!-- ══ Поиск пользователей ══ -->
  <section class="friends-section">
    <h2>🔍 Найти пользователя</h2>
    <div class="friends-search-wrap">
      <input type="text" id="user-search" placeholder="Введи имя или никнейм..." autocomplete="off">
      <div class="search-results" id="search-results"></div>
    </div>
  </section>

  <!-- ══ Список друзей ══ -->
  <section class="friends-section">
    <h2>✅ Мои друзья
      {% if friends %}<span class="count-badge">{{ friends|length }}</span>{% endif %}
    </h2>
    {% if friends %}
    <div class="friends-grid" id="friends-grid">
      {% for f in friends %}
      <a href="{{ url_for('public_profile', user_id=f.id) }}" class="friend-card" id="fc-{{ f.id }}">
        {% if f.avatar_url %}
          <img src="{{ f.avatar_url }}" alt="avatar" class="fc-avatar">
        {% else %}
          <div class="fc-avatar-ph">{{ (f.name or f.email)[0].upper() }}</div>
        {% endif %}
        <div class="fc-name">{{ f.name or f.email }}</div>
        {% if f.nickname %}<div class="fc-nick">@{{ f.nickname }}</div>{% endif %}
        <div class="fc-level">⭐ {{ f.current_level }} ур. · {{ f.experience_points }} XP</div>
        <div class="fc-actions">
          <button class="fc-btn fc-btn-remove"
                  data-uid="{{ f.id }}"
                  onclick="removeFriend(event, this)">✕ Удалить</button>
        </div>
      </a>
      {% endfor %}
    </div>
    {% else %}
    <div class="friends-empty">
      <div class="fe-icon">👥</div>
      <p>У тебя пока нет друзей. Найди их через поиск выше!</p>
    </div>
    {% endif %}
  </section>

</div><!-- /friends-page -->

<!-- Toast -->
<div id="friends-toast" style="display:none" class="friends-toast"></div>

<script>
// ── Toast ──
function showToast(msg, ok) {
  var t = document.getElementById('friends-toast');
  t.textContent = msg;
  t.className = 'friends-toast ' + (ok ? 'friends-toast-ok' : 'friends-toast-err');
  t.style.display = 'block';
  setTimeout(function(){ t.style.display = 'none'; }, 3000);
}

function doFetch(url, cb) {
  fetch(url, {method:'POST', headers:{'X-{