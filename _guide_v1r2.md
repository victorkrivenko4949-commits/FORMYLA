# Victor: автономная установка и live-проверка OWUI-Roo Bridge

Статус: execution guide v1_r2. Это задание предназначено непосредственно ИИ-кодеру, работающему на Victor. Результатом должна быть установленная и проверенная нода `victor`, а не новый план, спецификация или отчёт. Ревизия v1_r2 заменяет v1_r1 и устраняет `BLOCK_ROO_BRIDGE_EXTENSION_MISSING`.

## Жёсткая директива исполнителю

Выполни задание автономно до `PASS_H2_NODE_READY`. Не спрашивай оператора, где искать файлы, где взять VSIX, как создать `instances.json`, какие команды выполнять и как продолжить после v1_r1. Все поставляемые материалы находятся в одном OWUI bundle. Допустимое участие оператора ограничено подтверждением UAC и безопасным вводом DeepSeek key, только если позже потребуется fallback-разбор свободного текста.

Не изменяй исходный код Bridge, `h2_shared`, Roo Bridge extension или активную OWUI Function. Не добавляй маршрут `victor` повторно: Function 3.16.63 уже содержит этот маршрут. Не используй старые bundle v1_r0 и v1_r1. Не создавай `instances.json` вручную: authoritative writer поставляется как VSIX и обязан сам создать registry.

## Зафиксированные входы

```text
HOSTNAME=DESKTOP-OLJ4LRK
WINDOWS_USER=Redmi
DISPLAY_NAME=Victor
NODE_ID=victor
PYTHON=3.12.10 x64
VSCODE=1.135.0 User
ROO_EXTENSION=rooveterinaryinc.roo-cline-3.54.0
ROO_BRIDGE_EXTENSION=local.roo-bridge-0.6.56
OWUI_ORIGIN=https://chat.h2platform.ru
OWUI_FUNCTION_ID=h2_roo_function
OWUI_FUNCTION_VERSION=3.16.63
NATS_URL=nats://192.168.99.11:4222
OWNERSHIP_KV=owui_roo_bridge_victor_ownership
AUTOSTART_TASK=H2_VICTOR_BRIDGE
```

Полный установочный комплект:

```text
FILE_ID=95184dd6-48bf-40f6-9a5e-93a5af21bdb0
FILENAME=VICTOR_BRIDGE_WHEELHOUSE_v1_r2.zip
SIZE=10766068
SHA256=f54f025db2ec1548629a589bbe9d1dd56f70e48dde0227205e74149f19791419
```

В комплекте 39 wheels для Windows CPython 3.12 x64, включая:

```text
owui_roo_bridge=0.5.10
h2_shared=0.56.70
keyring=25.7.0
pywin32-ctypes=0.2.3
psutil=7.2.2
nats-py=2.15.0
```

`pywin32-ctypes` закрывает подтверждённый блокер v1_r0. `psutil` включён явно, потому что health/lifecycle код Bridge использует его, хотя wheel 0.5.10 не объявляет его в `Requires-Dist`.

В комплект также включён exact VSIX:

```text
extensions/roo-bridge-0.6.56.vsix
EXTENSION_ID=local.roo-bridge
VERSION=0.6.56
SHA256=d48b50f3bd9d59c112a7f6ef55553d9fd21c97b1a5cee362b8ef9d03de32be24
VSCODE_ENGINE=^1.85.0
DEPENDENCY=RooVeterinaryInc.roo-cline
```

Это authoritative writer для `%USERPROFILE%\.roo-bridge\instances.json`. Он активируется на `onStartupFinished`, автоматически запускает loopback Roo API server, атомарно регистрирует окно и обновляет heartbeat. Bundle не содержит и не вызывает самодельный writer.

## Непереопределяемые правила

- Используй только routing ID `victor` в lower-case. Не используй `Victor`, hostname, `laptop` или `heavy02` как node ID.
- Не используй WinRM/WSMan, donor config, donor credential, публичный PyPI или похожий wheel.
- Не выводи значения `H2_API_KEY` и DeepSeek key. Не помещай секреты в `node.json`, task arguments, логи или evidence.
- Не запускай второй Bridge. При обнаружении второго процесса остановись с `BLOCK_MULTIPLE_BRIDGE_PROCESSES`.
- Не закрывай VS Code/Roo принудительно, не применяй `taskkill` или `Stop-Process`.
- Не создавай, не редактируй и не подменяй `%USERPROFILE%\.roo-bridge\instances.json` вручную.
- `node.json` должен быть BOM-free и находиться только в `C:\ProgramData\H2\config`.
- Рабочая директория Bridge должна быть `C:\ProgramData\H2\config`, потому что Bridge 0.5.10 загружает `node.json` из CWD.
- NATS URL задаётся runtime-переменной `NATS_URL`; поле `node.json.nats.url` не является единственным источником.
- PASS разрешён только после live-вызова через `/api/chat/completions`, model `h2_roo_function`, а не после прямого NATS или локального handler-вызова.

## Установка

Открой один elevated Windows PowerShell 5.1 под пользователем `Redmi`. Выполни следующий bootstrap-блок целиком:

```powershell
$ErrorActionPreference = "Stop"
$Root = "C:\H2\victor_bridge_release"
$Zip = "$Root\VICTOR_BRIDGE_WHEELHOUSE_v1_r2.zip"
$Extract = "$Root\payload"
New-Item -ItemType Directory -Path $Root -Force | Out-Null

$Key = [Environment]::GetEnvironmentVariable("H2_API_KEY", "Machine")
if ([string]::IsNullOrWhiteSpace($Key)) {
  $Key = [Environment]::GetEnvironmentVariable("H2_API_KEY", "User")
}
if ([string]::IsNullOrWhiteSpace($Key)) { $Key = $env:H2_API_KEY }
if ([string]::IsNullOrWhiteSpace($Key)) { throw "BLOCK_H2_API_KEY_MISSING" }

$Headers = @{ Authorization = "Bearer $Key" }
Invoke-WebRequest -UseBasicParsing `
  -Uri "https://chat.h2platform.ru/api/v1/files/95184dd6-48bf-40f6-9a5e-93a5af21bdb0/content" `
  -Headers $Headers -OutFile $Zip -TimeoutSec 300

if ((Get-Item -LiteralPath $Zip).Length -ne 10766068) {
  throw "BLOCK_BUNDLE_SIZE_MISMATCH"
}
$Sha = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Sha -ne "f54f025db2ec1548629a589bbe9d1dd56f70e48dde0227205e74149f19791419") {
  throw "BLOCK_BUNDLE_SHA256_MISMATCH"
}

if (Test-Path -LiteralPath $Extract) {
  Remove-Item -LiteralPath $Extract -Recurse -Force
}
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force
$Bundle = "$Extract\VICTOR_BRIDGE_WHEELHOUSE_v1_r2"

Set-ExecutionPolicy -Scope Process Bypass -Force
& "$Bundle\scripts\install_victor_bridge.ps1"
if ($LASTEXITCODE -ne 0) { throw "BLOCK_INSTALL_SCRIPT_FAILED" }
& "$Bundle\scripts\verify_victor_bridge.ps1"
if ($LASTEXITCODE -ne 0) { throw "BLOCK_LOCAL_VERIFY_FAILED" }
```

Установщик автоматически:

- проверяет hostname, пользователя, Python 3.12 и все SHA-256;
- машинно вычисляет Windows dependency closure;
- использует только локальный wheelhouse;
- создаёт или повторно использует `C:\ProgramData\H2\bridge_venv`;
- устанавливает Bridge, `h2_shared`, `pywin32-ctypes` и `psutil`;
- проверяет VS Code 1.135.0 и Roo 3.54.0;
- idempotently устанавливает или сохраняет `local.roo-bridge@0.6.56` из exact VSIX;
- не пишет registry вручную: при отсутствии ready canary instance открывает отдельное окно `C:\H2\victor_bridge_canary`;
- ждёт до 120 секунд ровно одну writer-owned запись с exact workspace, `state=ready`, `roo_webview_ready=true`, живым VS Code PID и heartbeat не старше 30 секунд;
- запускает неизменённый Bridge wheel через внешний compatibility launcher, который
  адаптирует `nats-py 2.15.0 status.ttl` к ожидаемому Bridge 0.5.10
  read-контракту `status.config.ttl`;
- вычисляет фактические Roo paths пользователя `Redmi`;
- создаёт BOM-free `node.json` с `node_id=victor`;
- создаёт или проверяет NATS KV bucket `owui_roo_bridge_victor_ownership`, `history=1`, TTL не менее 60 секунд;
- создаёт один idempotent scheduled task `H2_VICTOR_BRIDGE`;
- запускает Bridge из CWD `C:\ProgramData\H2\config`;
- требует ровно один процесс Bridge.

### Продолжение после блокировки v1_r1

На Victor уже может существовать `C:\ProgramData\H2\bridge_venv` с успешно установленными Python-пакетами. Не удаляй venv и не откатывай выполненные стадии. Просто выполни bootstrap-блок v1_r2 выше. Установщик повторно проверит bundle и dependency closure, сохранит пригодный venv, установит VSIX, дождётся настоящего registry и автоматически продолжит оставшиеся стадии.

Если VSIX уже установлен и существует ровно одна свежая ready-запись для canary workspace, результат extension и окна должен быть `KEEP`. Если VSIX установлен, но записи ещё нет, установщик сам запускает отдельное canary-окно через VS Code CLI. Не проси оператора открыть Roo вручную.

Если DeepSeek key уже есть в `H2_DEEPSEEK_API_KEY` или `DEEPSEEK_API_KEY`, установщик переносит его в Windows Credential Manager target `H2_DEEPSEEK_API_KEY`, username `default`, без вывода значения. При отсутствии ключа установка и strict-JSON live test продолжаются; fallback-разбор свободного текста до установки credential не проверяется.

## Live-проверка через Function и Bridge

Используй helper:

```powershell
$Call = "$Bundle\scripts\invoke_owui_function.ps1"
$Evidence = "C:\ProgramData\H2\evidence"
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
```

### Route и health

```powershell
& $Call -PayloadJson '{"operation":"route_attest","node":"victor"}' `
  -OutFile "$Evidence\01_route_attest.json"
& $Call -PayloadJson '{"operation":"health","node":"victor"}' `
  -OutFile "$Evidence\02_health.json"
& $Call -PayloadJson '{"operation":"list_instances","node":"victor"}' `
  -OutFile "$Evidence\03_list_instances.json"
```

Обязательные predicates:

- нет `E_UNKNOWN_NODE`, `E_MISSING_NODE`, timeout или fallback;
- route относится к `victor`;
- command subject начинается с `h2.roo_bridge.node.victor.cmd`;
- event subject начинается с `h2.roo_bridge.node.victor.evt`;
- queue group равна `q.node.victor`;
- health не `DEGRADED` из-за отсутствия `psutil`;
- присутствует ready Roo instance для `C:/H2/victor_bridge_canary`.

К моменту этой стадии canary workspace уже обязан быть открыт установщиком, а его exact запись должна пройти local readiness gate. Если `list_instances` не видит её, не создавай registry вручную: повторно запусти local verifier и зафиксируй точный `BLOCK_ROO_INSTANCES_NOT_READY`.

### Live new

Сгенерируй UUID один раз и используй его и в `task_id`, и в первой строке prompt:

```powershell
$U1 = [guid]::NewGuid().ToString()
$New = @{
  operation = "dispatch"
  session_mode = "new"
  node = "victor"
  workspace = "C:/H2/victor_bridge_canary"
  task_id = "VICTOR-BRIDGE-NEW-$U1"
  prompt = "TASK_ID: VICTOR-BRIDGE-NEW-$U1`n`nRead input.txt. Create result.txt containing exactly VICTOR_BRIDGE_CANARY_PASS_v1 followed by a newline. Do not modify any other file. Then finish the task."
} | ConvertTo-Json -Compress
& $Call -PayloadJson $New -OutFile "$Evidence\04_dispatch_new.json"
```

Сохрани exact `correlation_id`, `session_uuid`, `roo_task_id` и `request_id` из ответа. Poll `roo_task_state` не чаще одного раза в 10 секунд, deadline 900 секунд. Единственный успешный terminal state: `COMPLETED`.

### Continue

Используй exact `session_uuid` и `roo_task_id` из new. Для continue создай новый UUID:

```powershell
$U2 = [guid]::NewGuid().ToString()
$Continue = @{
  operation = "dispatch"
  session_mode = "continue"
  node = "victor"
  workspace = "C:/H2/victor_bridge_canary"
  session_uuid = "<EXACT_SESSION_UUID_FROM_NEW>"
  roo_task_id = "<EXACT_ROO_TASK_ID_FROM_NEW>"
  task_id = "VICTOR-BRIDGE-CONTINUE-$U2"
  prompt = "TASK_ID: VICTOR-BRIDGE-CONTINUE-$U2`n`nAppend exactly VICTOR_BRIDGE_CONTINUE_PASS_v1 followed by a newline to result.txt. Do not modify any other file. Then finish."
} | ConvertTo-Json -Compress
& $Call -PayloadJson $Continue -OutFile "$Evidence\05_dispatch_continue.json"
```

Poll до `COMPLETED`. Затем файл `result.txt` должен побайтно содержать:

```text
VICTOR_BRIDGE_CANARY_PASS_v1
VICTOR_BRIDGE_CONTINUE_PASS_v1
```

### State, export, close и IDLE

```powershell
$Session = "<EXACT_SESSION_UUID_FROM_NEW>"
$State = @{
  operation = "roo_task_state"
  node = "victor"
  workspace = "C:/H2/victor_bridge_canary"
  session_uuid = $Session
} | ConvertTo-Json -Compress
& $Call -PayloadJson $State -OutFile "$Evidence\06_state.json"

$Export = @{
  operation = "roo_task_export"
  node = "victor"
  workspace = "C:/H2/victor_bridge_canary"
  session_uuid = $Session
  request_id = "VICTOR-EXPORT-$([guid]::NewGuid())"
  scope = "full"
} | ConvertTo-Json -Compress
& $Call -PayloadJson $Export -OutFile "$Evidence\07_export.json"

$Close = @{
  operation = "roo_window_close"
  node = "victor"
  workspace = "C:/H2/victor_bridge_canary"
} | ConvertTo-Json -Compress
& $Call -PayloadJson $Close -OutFile "$Evidence\08_close.json"
```

Poll state до `IDLE`, deadline 120 секунд. Подтверди отсутствие второго dispatch, orphan transaction и второго Bridge process.

## Идемпотентный повтор

Повторно запусти:

```powershell
& "$Bundle\scripts\install_victor_bridge.ps1"
& "$Bundle\scripts\verify_victor_bridge.ps1"
```

Второй запуск обязан сохранить:

- один scheduled task;
- один Bridge process;
- тот же `node.json` digest;
- версии Bridge 0.5.10 и `h2_shared` 0.56.70;
- task result `KEEP`, если definition не изменился;
- отсутствие повторной регистрации маршрута Function.

## Разрешённые BLOCK

Не превращай локально исправимую ошибку в вопрос оператору. Диагностируй и один раз повтори. Terminal BLOCK допустим только с точным predicate и evidence:

```text
BLOCK_H2_API_KEY_MISSING
BLOCK_OWUI_FILES_API_AUTH
BLOCK_BUNDLE_SIZE_MISMATCH
BLOCK_BUNDLE_SHA256_MISMATCH
BLOCK_WHEELHOUSE_DEPENDENCY_INCOMPLETE
BLOCK_NODE_HOSTNAME_MISMATCH
BLOCK_RUNTIME_USER_MISMATCH
BLOCK_ROO_STORAGE_NOT_FOUND
BLOCK_VSCODE_CLI_MISSING
BLOCK_VSCODE_VERSION
BLOCK_VSCODE_EXTENSION_ENUMERATION
BLOCK_ROO_EXTENSION_VERSION
BLOCK_ROO_BRIDGE_VSIX_MISSING
BLOCK_ROO_BRIDGE_VSIX_INSTALL
BLOCK_ROO_BRIDGE_VSIX_VERSION
BLOCK_ROO_CANARY_WINDOW_LAUNCH
BLOCK_ROO_INSTANCES_NOT_READY
BLOCK_OWNERSHIP_KV_NOT_PROVISIONED
BLOCK_MULTIPLE_BRIDGE_PROCESSES
BLOCK_AUTOSTART_DRIFT_RUNNING_PROCESS
BLOCK_BRIDGE_PROCESS_CARDINALITY
BLOCK_OWUI_FUNCTION_HTTP_*
```

## Финальный ответ

Успех:

```text
VERDICT=PASS_H2_NODE_READY
NODE_ID=victor
HOSTNAME=DESKTOP-OLJ4LRK
BRIDGE_VERSION=0.5.10
H2_SHARED_VERSION=0.56.70
ROO_BRIDGE_EXTENSION=local.roo-bridge@0.6.56
ROO_BRIDGE_VSIX_SHA256=d48b50f3bd9d59c112a7f6ef55553d9fd21c97b1a5cee362b8ef9d03de32be24
WHEELHOUSE_FILE_ID=95184dd6-48bf-40f6-9a5e-93a5af21bdb0
WHEELHOUSE_SHA256=f54f025db2ec1548629a589bbe9d1dd56f70e48dde0227205e74149f19791419
NODE_JSON_SHA256=<sha256>
OWNERSHIP_KV=owui_roo_bridge_victor_ownership
BRIDGE_PROCESS_COUNT=1
LIVE_NEW=PASS
LIVE_CONTINUE=PASS
EXPORT_READBACK=PASS
CLOSE_IDLE=PASS
IDEMPOTENCY=PASS
EVIDENCE_PATH=C:\ProgramData\H2\evidence
```

Блокировка:

```text
VERDICT=BLOCK
BLOCK_CODE=<exact code>
FAILED_PREDICATE=<exact check>
AUTOMATIC_DIAGNOSTICS=<what was checked>
LOCAL_RETRY=<result>
SAFE_NEXT_ACTION=<one exact action>
```

Новый concept/spec/roadmap вместо исполнения не является результатом.
