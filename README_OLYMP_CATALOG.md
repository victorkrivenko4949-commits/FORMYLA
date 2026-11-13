# Раздел «Олимпиады» (OLYMP_CATALOG_V1)

Каталог олимпиадных задач: 4624 задачи, 13 олимпиад, 730 рисунков.
URL: /olymp-catalog. Доступ открыт ВСЕМ авторизованным пользователям
(OLYMP_CATALOG_USERS по умолчанию "*"). Старое поведение белого списка
возвращается заданием OLYMP_CATALOG_USERS="lavrik,victor".
ИИ-тьютор каталога по-прежнему закрыт paywall Premium (method_week/paywall.py).

## Что нужно доложить в эту ветку вручную (бинарные/крупные файлы)
1. data/olymp_catalog/<slug>.json — 13 файлов задач (из архива FORMYLA_olymp_catalog_DATA.zip).
2. static/olymp_figures/figures_all/*.svg и static/olymp_figures/FINAL_FIGURES/*.png — рисунки.

После этого слить ветку olymp-catalog в main — Render задеплоит автоматически.
