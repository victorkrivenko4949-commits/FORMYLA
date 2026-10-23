# Evidence — Bridge Victor: BLOCK_MISSING_H2_SHARED_ARTIFACT

**Дата:** 2026-09-01
**Задание:** INSTALL AND LIVE-VERIFY OWUI–ROO BRIDGE ON VICTOR
**Display name:** Victor
**Canonical node_id:** victor
**Target:** DESKTOP-OLJ4LRK (этот Windows-компьютер)

---

## Вердикт

```text
VERDICT=BLOCK
BLOCK_CODE=BLOCK_MISSING_H2_SHARED_ARTIFACT
FAILED_PREDICATE=approved h2_shared>=0.41.0 artifact не найден ни локально, ни в OWUI
MISSING_ARTIFACT_OR_PERMISSION=h2_shared>=0.41.0 wheel (approved)
SAFE_NEXT_ACTION=предоставить approved h2_shared>=0.41.0 artifact (OWUI file ID или wheelhouse),
затем перезапустить установку с шага C.1
```

---

## A. Preflight (выполнено)

| Пункт | Значение |
|---|---|
| Hostname | `DESKTOP-OLJ4LRK` |
| OS | Windows 11, release 11 (build 10.0.26200) |
| Пользователь | `Redmi` |
| Python | 3.12.10 (`C:\Users\Redmi\AppData\Local\Programs\Python\Python312\python.exe`) |
| VS Code | 1.135.0 (User install) |
| Roo | `rooveterinaryinc.roo-cline-3.54.0` |
| H2_API_KEY | present = true (User environment), значение не читалось и не выводилось |
| Files API | `GET https://chat.h2platform.ru/api/v1/files/` → 200 application/json |

## A.4–5. Bridge wheel

- File ID: `2b3fdbca-5809-4d34-8e08-0460e0e5c52e`
- Filename: `owui_roo_bridge-0.5.10-py3-none-any.whl`
- Ожидаемый размер: 386434 → фактический: 386434 ✅
- Ожидаемый SHA256: `f836efcc97c5d4ec71119ee9b191df7b58d3bf7afd9e9cf3280835583c0d05f6` → фактический совпал ✅

## A.6–7. h2_shared>=0.41.0 — НЕ НАЙДЕН

Проверка локально:

- `importlib.util.find_spec('h2_shared')` → `False`
- `importlib.util.find_spec('nats')` → `False`
- `pip list` → нет `h2_shared`, нет `nats`
- `C:\ProgramData\H2` → ABSENT
- `C:\H2` → ABSENT
- рекурсивный обход рабочей директории → файлов с `h2_shared` нет

Проверка в OWUI (search по exact filename, каждый вернул 404 «No files found»):

- `h2_shared`
- `h2_shared-0.41.0`
- `h2_shared-0.41.0-py3-none-any.whl`
- `h2_shared-0.41.0-cp312-none-any.whl`
- `h2_shared-0.41.1-py3-none-any.whl`
- `h2_shared-0.42.0-py3-none-any.whl`
- `h2_shared-0.43.0-py3-none-any.whl`
- `h2_shared.whl`
- `h2shared`

Bridge wheel METADATA подтверждает жёсткую зависимость: `Requires-Dist: h2_shared>=0.41.0`.

## Подтверждение существования других H2-артефактов (не h2_shared)

В OWUI найдены (read-only, не влияют на данный BLOCK):

- `h2_roo_function_full.py` (OWUI file ID `03096f34-3a39-4366-875d-d10605c3e4bc`) — содержит approved `NATS_URL = "nats://192.168.99.11:4222"` (v3.16.16).
- `owui_roo_bridge-0.5.10-py3-none-any.whl` (проверен выше).

NATS_URL для последующей установки зафиксирован как `nats://192.168.99.11:4222`
(только из существующей approved конфигурации, не придуман).

## Почему не продолжено

Задание требует (A.6–A.7): при отсутствии approved h2_shared artifact остановиться
с `BLOCK_MISSING_H2_SHARED_ARTIFACT`, не скачивать случайный пакет из публичного
PyPI и не придумывать file ID. Установка bridge без h2_shared невозможна
(жёсткая `Requires-Dist`). Изготовление собственного h2_shared на target без
provenance запрещено (hard rule 8/9).

---

## Evidence-запись

Этот файл является evidence-записью остановки. Мутации target не производились:
node.json не создавался, venv не создавался, пакеты не устанавливались, служба
не регистрировалась, NATS не конфигурировался.
