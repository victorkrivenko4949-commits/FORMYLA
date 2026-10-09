#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "templates", "olympiad_solutions.html")

template = r'''{% extends "base.html" %}

{% block title %}Решения — {{ olympiad.full_title }}{% endblock %}

{% block content %}
<div style="margin-bottom: 16px;">
    <a href="/olympiads" class="btn-back-catalog"
       style="display:inline-flex; align-items:center; gap:8px;
              padding:10px 18px; background:rgba(56,189,248,0.12);
              border:1px solid rgba(56,189,248,0.35); color:#e2e8f0;
              border-radius:10px; text-decoration:none; font-weight:600;
              font-size:0.95em; transition: all .15s ease;">
        <span style="font-size:1.1em;"><-</span> Назад к каталогу
    </a>
</div>
<style>
    .btn-back-catalog:hover {
        background: rgba(56,189,248,0.22) !important;
        border-color: rgba(56,189,248,0.6) !important;
        color: #fff !important;
        transform: translateX(-2px);
    }
</style>

<h1 class="page-title">{{ olympiad.full_title }}</h1>
<p class="page-subtitle">
    {{ combo.year }} год, {{ combo.grade }} класс — {{ combo.round_title | default('') }}
</p>
<p style="color: #888; margin-bottom: 20px;">Ответы и подробные решения</p>

{% for day_block in day_blocks %}
{% if day_block.day is not none and day_blocks|length > 1 %}
<div style="background:linear-gradient(135deg, rgba(56,189,248,0.15), rgba(99,102,241,0.10)); padding:16px 20px; margin:24px 0 16px 0; border-radius:12px; border:1px solid rgba(56,189,248,0.25); text-align:center
