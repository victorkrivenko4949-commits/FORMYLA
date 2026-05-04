#!/usr/bin/env python3
"""Generate the new about.html page for FORMYLA."""
import os, pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent
out = BASE / "templates" / "about.html"

P1 = '''{% extends "base.html" %}
{% block title %}О проекте FORMYLA{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/about.css') }}?v={{ asset_version }}">
{% endblock %}
{% block content %}
<div class="about-page">

  <section class="about-hero">
    <h1 class="about-title">FORMYLA</h1>
    <p class="about-subtitle">Единственная в России ИИ-платформа для подготовки к математическим олимпиадам с 7 специализированными агентами</p>
  </section>

  <section class="about-section">
    <div class="stats{
