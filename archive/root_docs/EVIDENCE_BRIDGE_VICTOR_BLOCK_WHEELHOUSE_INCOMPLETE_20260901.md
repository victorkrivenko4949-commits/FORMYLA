# Evidence — Bridge Victor: BLOCK_WHEELHOUSE_DEPENDENCY_INCOMPLETE

**Дата:** 2026-09-01
**Задание:** INSTALL AND LIVE-VERIFY OWUI–ROO BRIDGE ON VICTOR
**Display name:** Victor
**Canonical node_id:** victor
**Target:** DESKTOP-OLJ4LRK (Windows 11, пользователь Redmi, Python 3.12.10)

---

## Вердикт

```text
VERDICT=BLOCK
BLOCK_CODE=BLOCK_WHEELHOUSE_DEPENDENCY_INCOMPLETE
FAILED_PREDICATE=approved closed-world wheelhouse lacks a required transitive dependency
MISSING_ARTIFACT_OR_PERMISSION=pywin32-ctypes>=0.2.0 (sys_platform==win32; required by keyring-25.7.0)
SAFE_NEXT_ACTION=пересобрать VICTOR_BRIDGE_WHEELHOUSE v1_r1 с полным closed-world набором
(включить pywin32-ctypes>=0.2.0 и повторно прогнать offline pip install + pip check)
```

---

## Что выполнено (preflight и начальные шаги установки)

1. NATS `nats://192.168.99.11:4222` — TCP connect OK (approved источник: `h2_roo_function_full.py`).
2. Bridge wheel `owui_roo_bridge-0.5.10-py3-none-any.whl` (OWUI file `2b3fdbca-5809-4d34-8e08-0460e0e5c52e`) — size 386434, SHA256 `f836efcc…` совпал.
3. Найден approved closed-world bundle `VICTOR_BRIDGE_WHEELHOUSE_v1_r0.zip`
   (OWUI file `e9fba74b-500a-4e28-a5c8-416b5df9fcaa`, size 10232354).
4. Целостность bundle проверена: все 37 wheels совпали с SHA256SUMS.txt — `ALL_OK`.
   Состав: `h2_shared-0.56.70`, `owui_roo_bridge-0.5.10`, `nats-py-2.15.0`,
   `aiohttp-3.14.3`, `httpx-0.28.1`, `keyring-25.7.0`, `pydantic-2.13.5`,
   `websockets-17.1`, `cryptography`, `mariadb`, прочие transitive deps.
5. Создан production venv: `C:\ProgramData\H2\bridge_venv` (Python 3.12.10).

## Что заблокировало установку

Offline-установка (`pip install --no-index --find-links …/wheels owui_roo_bridge==0.5.10`)
завершилась ошибкой:

```text
ERROR: Could not find a version that satisfies the requirement
pywin32-ctypes>=0.2.0; sys_platform == "win32" (from keyring) (from versions: none)
ERROR: No matching distribution found for pywin32-ctypes>=0.2.0; sys_platform == "win32"
```

Анализ:

- `keyring-25.7.0` (в bundle) на Windows требует `pywin32-ctypes>=0.2.0` для
  Credential Manager backend.
- В bundle присутствуют Linux-зависимости `jeepney` и `secretstorage`, но
  Windows-зависимость `pywin32-ctypes` отсутствует.
- Это нарушает требование closed-world install («все transitive dependencies»),
  зафиксированное в письме архитектора и в Definition of Done.

Проверка в OWUI (exact filename search, все вернули 404):

```text
pywin32-ctypes-0.2.3-py3-none-any.whl  -> No files found
pywin32-ctypes                         -> No files found
pywin32                                -> No files found
pywin32-310-cp312-cp312-win_amd64.whl  -> No files found
```

## Почему не обойдено

Hard rules 8/9 и письмо архитектора запрещают:

- скачивать зависимости из публичного PyPI во время target install;
- придумывать file ID / artifact;
- использовать donor-конфигурацию.

Поэтому `pywin32-ctypes` не извлекался из публичного PyPI и не подменялся.

## Текущее состояние target

- Создан пустой production venv `C:\ProgramData\H2\bridge_venv` (локальная
  bootstrap-запись, не target-component mutation).
- Пакеты не установлены (pip install не дошёл до завершения).
- `node.json` не создавался, служба не регистрировалась, NATS ownership KV не
  provisioning-ся, bridge не запускался.

---

## Итог

Бандл `VICTOR_BRIDGE_WHEELHOUSE_v1_r0` подтверждён как approved по SHA, но
неполон как closed-world набор для Windows. Требуется пересборка wheelhouse
с добавлением `pywin32-ctypes>=0.2.0` (и, при обнаружении, любых других
отсутствующих transitive deps), после чего — повторный offline install и
`pip check`.
