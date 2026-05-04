#!/usr/bin/env python3
"""Generate updated about.css for FORMYLA."""
import pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent
out = BASE / "static" / "css" / "about.css"

css = """/* ═══════════════════════════════════════════════════════
   СТРАНИЦА "О САЙТЕ" — FORMYLA v2
   ═══════════════════════════════════════════════════════ */

.about-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 40px 20px 80px;
}

/* ── Hero ── */
.about-hero {
  text-align: center;
  padding: 60px 0 40px;
}
.about-title {
  font-size: 3rem;
  font-weight: 900;
  font-style: italic;
  background: linear-gradient(135deg, #38ef7d, #11998e);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 12px;
}
.about-subtitle {
  font-size: 1.15rem;
  color: #94a3b8;
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.6;
}

/* ── Sections ── */
.about-section {
  margin-bottom: 48px;
}
.about-section h2 {
  font-size: 1.5rem;
  margin-bottom: 16px;
  color: #e2e8f0;
}
.about-section p {
  color: #94a3b8;
  line-height: 1.7;
  font-size: 15px;
}

/* ── Stats Grid ── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.stat-card {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 16px;
  padding: 24px;
  text-align: center;
}
.stat-num {
  font-size: 2.2rem;
  font-weight: 800;
  background: linear-gradient(135deg, #38ef7d, #11998e);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.stat-label {
  font-size: 14px;
  color: #94a3b8;
  margin-top: 4px;
}

/* ── Steps Grid ── */
.steps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.step-card {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 16px;
  padding: 24px;
  position: relative;
  transition: transform 0.2s, box-shadow 0.2s;
}
.step-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}
.step-number {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #38ef7d, #11998e);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 1.1rem;
  color: #0f172a;
  margin-bottom: 12px;
}
.step-card h3 {
  font-size: 1.05rem;
  color: #e2e8f0;
  margin-bottom: 8px;
}
.step-card p {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.6;
}

/* ── Comparison Table ── */
.comparison-table-wrapper {
  overflow-x: auto;
  margin-top: 16px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}
.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.comparison-table th,
.comparison-table td {
  padding: 12px 16px;
  text-align: center;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  color: #94a3b8;
}
.comparison-table th {
  background: rgba(30, 41, 59, 0.8);
  color: #e2e8f0;
  font-weight: 600;
  font-size: 13px;
}
.comparison-table td:first-child {
  text-align: left;
  font-weight: 500;
  color: #cbd5e1;
}
.comparison-table .highlight-col {
  background: rgba(56, 239, 125, 0.06);
  color: #38ef7d;
  font-weight: 700;
}
.comparison-table .check {
  color: #38ef7d;
  font-size: 1.2em;
}
.comparison-table .cross {
  color: #ef4444;
  font-size: 1.2em;
}
.comparison-table tbody tr:hover {
  background: rgba(56, 239, 125, 0.03);
}

/* ── Features Grid ── */
.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.feature-card {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 16px;
  padding: 24px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.feature-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}
.feature-icon {
  font-size: 2rem;
  display: block;
  margin-bottom: 12px;
}
.feature-card h3 {
  font-size: 1.1rem;
  color: #e2e8f0;
  margin-bottom: 8px;
}
.feature-card p {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.6;
}

/* Agents grid */
.agents-grid {
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
}
.agent-card {
  text-align: center;
}
.agent-card .feature-icon {
  font-size: 2.5rem;
  margin-bottom: 8px;
}

/* ── Plans Row ── */
.plans-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 16px;
}
@media (max-width: 640px) {
  .plans-row { grid-template-columns: 1fr; }
}
.plan-box {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 20px;
  padding: 32px 24px;
  position: relative;
}
.plan-box h3 {
  font-size: 1.4rem;
  color: #e2e8f0;
  margin-bottom: 8px;
}
.plan-price-tag {
  font-size: 1.8rem;
  font-weight: 800;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #38ef7d, #11998e);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.plan-free .plan-price-tag {
  background: linear-gradient(135deg, #94a3b8, #64748b);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.plan-box ul {
  list-style: none;
  padding: 0;
  margin: 0 0 24px;
}
.plan-box ul li {
  padding: 6px 0;
  color: #94a3b8;
  font-size: 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.06);
}
.plan-box ul li::before {
  content: "\\2713 ";
  color: #38ef7d;
  margin-right: 8px;
}
.plan-pro {
  border-color: rgba(56, 239, 125, 0.3);
  box-shadow: 0 0 30px rgba(56, 239, 125, 0.05);
}
.plan-badge-pro {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: linear-gradient(135deg, #38ef7d, #11998e);
  color: #0f172a;
  font-size: 0.75em;
  font-weight: 800;
  padding: 4px 16px;
  border-radius: 12px;
  letter-spacing: 1px;
}
.plan-btn {
  display: block;
  text-align: center;
  padding: 14px 24px;
  border-radius: 12px;
  font-weight: 700;
  text-decoration: none;
  transition: all 0.2s;
}
.plan-btn-free {
  background: rgba(255,255,255,0.06);
  color: #94a3b8;
  border: 1px solid rgba(148, 163, 184, 0.2);
}
.plan-btn-pro {
  background: linear-gradient(135deg, #38ef7d, #11998e);
  color: #0f172a;
  box-shadow: 0 4px 20px rgba(56, 239, 125, 0.3);
}
.plan-btn-pro:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(56, 239, 125, 0.4);
}
.guarantee {
  text-align: center;
  margin-top: 20px;
  padding: 16px;
  background: rgba(56, 239, 125, 0.05);
  border: 1px solid rgba(56, 239, 125, 0.15);
  border-radius: 12px;
  color: #94a3b8;
  font-size: 14px;
}

/* ── Founder ── */
.founder-card {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 16px;
  padding: 28px;
  margin-top: 16px;
}
@media (max-width: 640px) {
  .founder-card { flex-direction: column; align-items: center; text-align: center; }
}
.founder-avatar {
  width: 64px;
  height: 64px;
  background: linear-gradient(135deg, #38ef7d, #11998e);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8rem;
  font-weight: 900;
  color: #0f172a;
  flex-shrink: 0;
}
.founder-text p {
  margin-bottom: 10px;
}

/* ── FAQ ── */
.faq-list {
  margin-top: 16px;
}
.faq-item {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
  margin-bottom: 10px;
  overflow: hidden;
}
.faq-q {
  padding: 16px 20px;
  font-weight: 600;
  color: #e2e8f0;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
  font-size: 15px;
}
.faq-q:hover { background: rgba(255,255,255,0.03); }
.faq-a {
  padding: 0 20px 16px;
  color: #94a3b8;
  font-size: 14px;
  line-height: 1.6;
  display: none;
}
.faq-item.open .faq-a { display: block; }
.faq-item.open .faq-arrow { transform: rotate(180deg); }
.faq-arrow { transition: transform 0.2s; font-size: 12px; }

/* ── Telegram Button ── */
.tg-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #229ed9, #2aabee);
  color: white !important;
  border-radius: 999px;
  text-decoration: none;
  font-weight: 600;
  margin-top: 12px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.tg-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(42, 171, 238, 0.4);
}

/* ── Support Section ── */
.support-section {
  background: rgba(124, 58, 237, 0.06);
  padding: 32px;
  border-radius: 20px;
  border: 1px solid rgba(124, 58, 237, 0.15);
}
.support-form { margin-top: 20px; }
.form-row { margin-bottom: 16px; }
.form-row label {
  display: block;
  font-size: 14px;
  margin-bottom: 6px;
  color: #c4b5fd;
  font-weight: 500;
}
.form-row .muted { color: #6b6b7a; font-weight: 400; }
.support-form input,
.support-form select,
.support-form textarea {
  width: 100%;
  background: rgba(20, 20, 36, 0.7);
  border: 1px solid rgba(124, 58, 237, 0.25);
  border-radius: 10px;
  padding: 12px 14px;
  color: #e2e2f0;
  font-size: 15px;
  font-family: inherit;
  resize: vertical;
  box-sizing: border-box;
}
.support-form input:focus,
.support-form select:focus,
.support-form textarea:focus {
  outline: none;
  border-color: #a78bfa;
  box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.15);
}
.char-count { text-align: right; font-size: 12px; color: #6b6b7a; margin-top: 4px; }
.submit-btn {
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  color: white;
  border: none;
  border-radius: 10px;
  padding: 14px 32px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.2s;
}
.submit-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(124, 58, 237, 0.4);
}
.form-result { margin-top: 12px; font-size: 14px; min-height: 20px; }
.form-result.ok { color: #38ef7d; }
.form-result.err { color: #ef4444; }
.form-result.loading { color: #94a3b8; }

.about-version { margin-top: 8px; font-size: 13px; color: #475569; }
"""

out.write_text(css, encoding='utf-8')
print(f"Written CSS to {out}")
