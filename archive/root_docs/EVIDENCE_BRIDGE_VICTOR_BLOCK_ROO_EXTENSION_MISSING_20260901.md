# Evidence — Bridge Victor: BLOCK_ROO_BRIDGE_EXTENSION_MISSING

**Дата:** 2026-09-01
**Задание:** GUIDE_VICTOR_BRIDGE_ONE_SHOT_v1_r1.md
**Display name:** Victor
**Canonical node_id:** victor
**Target:** DESKTOP-OLJ4LRK (Windows 11, пользователь Redmi, Python 3.12.10 x64)

---

## Вердикт

```text
VERDICT=BLOCK
BLOCK_CODE=BLOCK_ROO_BRIDGE_EXTENSION_MISSING
FAILED_PREDICATE=instances.json writer (VS Code Roo Bridge extension / equivalent) отсутствует в bundle v1_r1 и в OWUI
MISSING_ARTIFACT_OR_PERMISSION=VS Code extension, создающий %USERPROFILE%\.roo-bridge\instances.json
SAFE_NEXT_ACTION=включить в bundle VSIX Roo Bridge extension (или approved target-side writer instances.json),
затем перезапустить install_victor_bridge.ps1
```

---

## Что выполнено фактически

1. Guide `GUIDE_VICTOR_BRIDGE_ONE_SHOT_v1_r1.md` (OWUI `58f69468-98ae-4d44-a6b1-741f704e3605`) — size 13911, SHA256 `0a293cf3…` совпал.
2. Bundle `VICTOR_BRIDGE_WHEELHOUSE_v1_r1.zip` (OWUI `099e8c10-bed8-4c55-9e12-84f5e4744d2e`) — size 10408546, SHA256 `bf5019c2…` совпал.
3. Elevated bootstrap:
   - `PASS_BUNDLE_SIZE_SHA`
   - `PASS_BUNDLE_HASHES` (все вложенные SHA-256 совпали)
   - Windows wheelhouse closure: `WINDOWS_WHEELHOUSE_CLOSURE=PASS`, `ACTIVE_PROJECTS=34`, `TOTAL_WHEELS=39`
   - `PASS_H2_API_KEY_PERSISTENT`
   - offline `pip install` — успешно установлены `owui_roo_bridge==0.5.10`, `h2_shared==0.56.70`, `pywin32-ctypes==0.2.3`, `psutil==7.2.2` и все transitive deps.

## Где установка остановилась

`install_victor_bridge.ps1` (строка 120–121) выполнил:

```text
BLOCK_ROO_INSTANCES_NOT_FOUND
Open Roo once in VS Code and ensure C:\Users\Redmi\.roo-bridge\instances.json exists.
```

## Анализ первопричины

- Bridge 0.5.10 читает `instances.json` исключительно из
  `%USERPROFILE%\.roo-bridge\instances.json` (canonical, без fallback).
- Этот файл пишет **VS Code Roo Bridge extension** (формат
  `{"<port>": {"current_workspace": "...", "state": "ready", ...}}`).
- В bundle v1_r1 НЕТ этого расширения (VSIX) и нет никакого target-side
  writer `instances.json`:
  - `run_victor_bridge.ps1` — только читает node.json и запускает runner;
  - `bridge_compat_runner.py` — compat-адаптер nats-py, не создаёт instances.json;
  - `provision_ownership_kv.py` — только provisioning KV bucket.
- Среди установленных VS Code расширений (`roo-cline-3.54.0`, `claude-dev`,
  python/powershell) нет ни одного, ссылающегося на `.roo-bridge`/`instances.json`.
- Поиск в OWUI (exact filename) по `roo-bridge`, `roo_bridge`, `roo-bridge-vsix`,
  `roo-bridge-extension`, `instances.json` — все `404 No files found`.

## Почему не обойдено

Вручную создавать `instances.json` запрещено: это registry, который должен вести
VS Code-расширение (bridge опирается на него как на AUTHORITATIVE runtime identity;
поддельный/пустой registry даст псевдоуспех list_instances и сломанный live E2E).
Не использовать donor config и не придумывать артефакт (hard rules).

## Текущее состояние target

- Production venv `C:\ProgramData\H2\bridge_venv` создан, пакеты установлены и
  `pip check` проходит.
- `node.json` НЕ создан (install-скрипт останавливается до его записи).
- Ownership KV НЕ provisioning-ся, scheduled task НЕ регистрируется, bridge НЕ запускается.

---

## Итог

Bundle v1_r1 исправил wheelhouse-зависимости (pywin32-ctypes + psutil), но остался
неполным: отсутствует компонент, создающий `instances.json`. Для продолжения требуется
VSIX Roo Bridge extension (или утверждённый target-side writer), после чего установка
должна дойти до `PASS_BRIDGE_PROCESS_CARDINALITY` и live E2E.
