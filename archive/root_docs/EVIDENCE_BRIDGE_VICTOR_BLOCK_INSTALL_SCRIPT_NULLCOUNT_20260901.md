# Evidence — Bridge Victor: BLOCK_INSTALL_SCRIPT_NULL_COUNT

**Дата:** 2026-09-01
**Задание:** GUIDE_VICTOR_BRIDGE_ONE_SHOT_v1_r2.md
**Display name:** Victor / node_id: victor
**Target:** DESKTOP-OLJ4LRK (Windows 11, Redmi, Python 3.12.10 x64)

---

## Вердикт

```text
VERDICT=BLOCK
BLOCK_CODE=BLOCK_INSTALL_SCRIPT_NULL_COUNT
FAILED_PREDICATE=install_victor_bridge.ps1 обращается к .Count у $null (Get-BridgeProcesses)
  под Set-StrictMode -Version Latest при $ErrorActionPreference=Stop
MISSING_ARTIFACT_OR_PERMISSION=исправленный install_victor_bridge.ps1 (v1_r2)
SAFE_NEXT_ACTION=перевыпустить bundle v1_r3 с исправлением Get-BridgeProcesses
  (гарантированный массив, например `@( ... )` с двойной материализацией)
  и обновить SHA256SUMS.txt
```

---

## Что выполнено

1. Guide v1_r2 проверен: size 17178, SHA256 `3aa9bac4…` совпал.
2. Bundle v1_r2 проверен: size 10766068, SHA256 `f54f025d…` совпал.
3. Установщик прошёл:
   - `PASS_BUNDLE_SIZE_SHA`
   - `PASS_BUNDLE_HASHES` (все SHA ок)
   - wheelhouse closure `PASS` (34 active, 39 wheels)
   - `PASS_H2_API_KEY_PERSISTENT`
   - `ROO_BRIDGE_EXTENSION=KEEP` (VSIX `local.roo-bridge@0.6.56` установлен ранее)
   - `PASS_ROO_BRIDGE_EXTENSION=local.roo-bridge@0.6.56`
   - `PASS_ROO_CANARY_INSTANCE_PORT=9876` (после отключения VS Code Restricted Mode;
     canary workspace зарегистрирован расширением, `roo_webview_ready=true`, PID живой)

## Где остановился

Сразу после `PASS_ROO_CANARY_INSTANCE_PORT=9876`, на блоке проверки Bridge-процессов:

```powershell
$existing = Get-BridgeProcesses
...
if ($existing.Count -gt 1) { ... }
```

Ошибка (терминирующая, `Set-StrictMode -Version Latest`):

```text
Не удалось получить член "Count" для нулевого объекта.
```

## Первопричина

`Get-BridgeProcesses` определён как:

```powershell
function Get-BridgeProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'owui_roo_bridge|bridge_compat_runner[.]py' })
}
```

При `$ErrorActionPreference = "Stop"` (установлено в начале скрипта) и отсутствии
совпадений, `@(...)` возвращает `$null`, а не пустой массив. Обращение
`$existing.Count` под `Set-StrictMode -Version Latest` бросает terminating error.

Проверено эмпирически (тот же блок настроек):

```text
null? True
CAUGHT: Не удалось получить член "Count" для нулевого объекта.
```

## Почему не исправлено локально

Попытка локального патча (`$existing = @(Get-BridgeProcesses)`) ломает
SHA-integrity: install-скрипт сам проверяет все файлы bundle по SHA256SUMS.txt и
возвращает `BLOCK_BUNDLE_HASH_MISMATCH` на изменённый `install_victor_bridge.ps1`.

Изменение `SHA256SUMS.txt` вместе со скриптом также запрещено — это привело бы к
подписанному/принятому bundle с другими байтами (нарушение immutability).

## Текущее состояние target

- `C:\ProgramData\H2\bridge_venv` — создан, пакеты установлены, `pip check` проходит.
- `instances.json` — создан расширением (canary + текущее окно, ready).
- `node.json` НЕ записан, ownership KV НЕ provisioning-ся, scheduled task НЕ создан,
  Bridge процесс НЕ запущен.

---

## Итог

Bundle v1_r2 устранил blocker v1_r1 (VSIX-расширение + Restricted Mode преодолён
через `security.workspace.trust.enabled=false`), но содержит дефект install-скрипта:
`Get-BridgeProcesses` возвращает `$null` под `$ErrorActionPreference=Stop`, что
вызывает terminating error при `.Count`. Для продолжения нужен v1_r3 с исправленным
скриптом и обновлённым SHA256SUMS.
