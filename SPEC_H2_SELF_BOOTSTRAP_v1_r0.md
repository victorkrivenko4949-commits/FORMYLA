# SPEC H2 SELF_BOOTSTRAP

**Рабочее имя продукта:** `H2_SELF_BOOTSTRAP`
**Версия спецификации:** `v1_r0`
**Дата:** 2026-09-01
**Статус документа:** `SPEC_DRAFT`
**Статус исполнения:** `SPEC_ONLY` — реальная установка запрещена до выпуска и приёмки P0-артефактов.
**Родительский документ:** концепт `H2_SELF_BOOTSTRAP` v0_r1 (`CONCEPT_QA_PASS`)
**Целевая платформа:** новый Windows-компьютер
**Исходная точка:** H2-ready Roo из доверенного signed distribution + локально доступный `H2_API_KEY`.

---

## 1. Назначение

Настоящая спецификация фиксирует исполнимый контракт `H2_SELF_BOOTSTRAP`, не
описанный детально в концепте:

- JSON-схемы всех descriptor, receipt и verdict;
- endpoint/capability contract (URL, методы, auth, schema, коды ошибок);
- точный gate-to-command-card mapping;
- compatibility matrix;
- release bundle manifest v2;
- state machine installer runner;
- resume/rollback алгоритм;
- acceptance matrix;
- test plan для disposable Windows VM.

Спецификация не является командой на реальную установку. Она фиксирует, ЧТО
должно быть реализовано и как это будет проверяться. До выпуска перечисленных
ниже P0-артефактов и прохождения acceptance matrix продукт сохраняет статус
`CONCEPT_ONLY`/`SPEC_ONLY`.

---

## 2. Термины и сокращения

| Термин | Значение |
|---|---|
| ACTIVE pointer | Файл с постоянным exact filename, указывающий на актуальный physical guide |
| physical guide | Версионный неизменяемый документ с операторским процессом |
| bootstrap index | Подписанный документ, связывающий guide, policy, descriptor и bundle |
| release bundle | Immutable набор installable bytes + manifest + command cards |
| command card | Машиночитаемое описание одного действия runner |
| coordinator | Unelevated процесс, выполняющий command cards последовательно |
| elevated broker | Минимальный elevated процесс, выполняющий один одобренный command ID |
| ledger | Append-only hash-chained журнал run |
| verdict | Подписанный machine-readable итог gate/run |
| receipt | Подписанный сервером документ о reservation/commit enrollment |
| capability | Короткоживущий подписанный opaque token на одно allow-listed действие |
| TARGET_RUN_ID | Уникальный идентификатор одного bootstrap run |
| gate | Именованная точка контроля с PASS/BLOCK предикатом |

---

## 3. Общие принципы

1. **Fail-closed.** Любая неопределённость — BLOCK, не дефолт вперёд.
2. **No secrets in clear surface.** `H2_API_KEY` не попадает в prompt, аргументы,
   файлы, логи, ledger, evidence, environment child-процессов.
3. **No remote channels.** WinRM/WSMan/PSSession/`wsmprovhost` запрещены статически
   и runtime deny policy.
4. **No implicit identity.** `node_id` берётся только из подписанного enrollment
   descriptor. Hostname, cached profile, DEFAULT_NODE — запрещены.
5. **Immutable artifacts.** Release bundle и physical guide неизменяемы; новая
   версия — новый файл с новым SHA256 и монотонным release sequence.
6. **Exact one.** ACTIVE pointer search должен вернуть ровно один объект.
7. **Separate statuses.** `GUIDE_STATUS`, `ENROLLMENT_STATUS`, `BUNDLE_STATUS`,
   `TARGET_STATUS` не объединяются.
8. **Evidence for every terminal outcome.** PASS, BLOCK, abort, rollback — все
   запечатываются.

---

## 4. JSON-схемы (нормативные)

Все схемы — canonical JSON (RFC 8785 JCS). Любое поле, не описанное в схеме,
отвергается. Все подписываемые документы используют envelope:

```json
{
  "payload": "<canonical-json-without-self-hash>",
  "payload_sha256": "<sha256-of-canonical-payload>",
  "signature": "<detached-signature>",
  "key_id": "<trusted-key-id>"
}
```

### 4.1. ACTIVE pointer

```json
{
  "schema": "h2.guide-pointer.v1",
  "product": "H2_SELF_BOOTSTRAP",
  "physical_filename": "GUIDE_H2_SELF_BOOTSTRAP_v1_r0.md",
  "physical_file_id": "<owui-file-id>",
  "physical_sha256": "<sha256>",
  "physical_size": "<bytes>",
  "release_sequence": 1,
  "issued_at": "<utc-iso8601>",
  "key_id": "<root-signing-key-id>"
}
```

### 4.2. Bootstrap index

```json
{
  "schema": "h2.bootstrap-index.v1",
  "index_id": "<uuid>",
  "policy_id": "<policy-id>",
  "guide": {
    "file_id": "<owui-file-id>",
    "filename": "GUIDE_H2_SELF_BOOTSTRAP_v1_r0.md",
    "sha256": "<sha256>",
    "size": "<bytes>"
  },
  "enrollment_descriptor": {
    "file_id": "<owui-file-id>",
    "sha256": "<sha256>",
    "size": "<bytes>"
  },
  "release_bundle": {
    "bundle_id": "<immutable-bundle-id>",
    "manifest_sha256": "<sha256>",
    "outer_size": "<bytes>"
  },
  "release_sequence": 1,
  "not_before": "<utc-iso8601>",
  "expires_at": "<utc-iso8601>",
  "key_id": "<root-signing-key-id>"
}
```

### 4.3. Enrollment descriptor

```json
{
  "schema": "h2.node-enrollment.v1",
  "enrollment_id": "<uuid>",
  "target_node_id": "<approved-node-id>",
  "machine_binding_challenge": "<server-challenge>",
  "expected_hostname": "<exact-or-approved-pattern>",
  "bundle_id": "<immutable-bundle-id>",
  "policy_id": "<bootstrap-policy-id>",
  "issued_at": "<utc-iso8601>",
  "expires_at": "<utc-iso8601>",
  "reservation_nonce": "<one-time-value>",
  "allowed_paths": {
    "workspace_root": "<target-owned-path>",
    "runtime_root": "<target-owned-path>",
    "staging_root": "<target-owned-path>",
    "backup_root": "<target-owned-path>",
    "evidence_root": "<target-owned-path>"
  },
  "manifest_sha256": "<sha256>",
  "release_sequence": 1
}
```

### 4.4. Reservation receipt

```json
{
  "schema": "h2.enrollment-reservation-receipt.v1",
  "enrollment_id": "<uuid>",
  "target_node_id": "<approved-node-id>",
  "target_run_id": "<run-id>",
  "installation_public_key": "<public-key>",
  "machine_challenge_response": "<response>",
  "reservation_lease_expires_at": "<utc-iso8601>",
  "correlation_id": "<provisional-correlation-id>",
  "workspace_id": "<test-workspace-id>",
  "issued_at": "<utc-iso8601>",
  "key_id": "<control-plane-key-id>"
}
```

### 4.5. Committed enrollment receipt

```json
{
  "schema": "h2.enrollment-committed-receipt.v1",
  "enrollment_id": "<uuid>",
  "target_node_id": "<approved-node-id>",
  "target_run_id": "<run-id>",
  "reservation_receipt_digest": "<sha256>",
  "committed_at": "<utc-iso8601>",
  "installation_public_key": "<public-key>",
  "key_id": "<control-plane-key-id>"
}
```

### 4.6. Release floor

```json
{
  "schema": "h2.release-floor.v1",
  "organization": "<org-id>",
  "policy_id": "<policy-id>",
  "release_sequence": 1,
  "issued_at": "<utc-iso8601>",
  "key_id": "<root-signing-key-id>"
}
```

### 4.7. Signed capability (opaque token)

```json
{
  "schema": "h2.capability.v1",
  "capability": "CAP_BUNDLE_DOWNLOAD",
  "issuer": "<control-plane-id>",
  "audience": "<owui-files-api>",
  "scope": ["files:read"],
  "organization": "<org-id>",
  "policy_id": "<policy-id>",
  "node_id": "<target-node-id>",
  "workspace_id": "<workspace-id>",
  "correlation_id": "<correlation-id>",
  "target_run_id": "<run-id>",
  "parent_run_id": "<parent-run-id-or-null>",
  "receipt_digest": "<sha256-or-null>",
  "issued_at": "<utc-iso8601>",
  "expires_at": "<utc-iso8601>",
  "token_id": "<uuid>",
  "replay_policy": "single-use"
}
```

### 4.8. Command card

```json
{
  "schema": "h2.command-card.v1",
  "command_id": "<id>",
  "executable": "<exact-path-in-bundle>",
  "arguments_template": ["<arg-or-placeholder>"],
  "parameters": {
    "<name>": {
      "source": "descriptor|receipt|manifest|inventory|ledger|none",
      "path": "<json-pointer>"
    }
  },
  "run_as": "user|elevated",
  "working_directory": "<bundle-root-relative>",
  "mutation": true,
  "timeout_seconds": 120,
  "quiescence_probe": "<executable-or-null>",
  "success_exit_codes": [0],
  "result_schema": "h2.command-result.v1",
  "expected_state_transition": "<state>",
  "evidence_outputs": ["<path>"],
  "rollback_command_id": "<id>",
  "rollback_success_predicate": "<predicate>",
  "retry_policy": {
    "max_attempts": 1,
    "require_quiescence": true
  },
  "mutation_extra": {
    "reversibility_class": "REVERSIBLE|COMPENSATABLE|IRREVERSIBLE",
    "ownership": "<owner>",
    "resource_scope": ["<path>"],
    "privilege_scope": ["<scope>"],
    "allowed_child_executables": ["<path>"],
    "network_allowlist": ["<origin-or-cidr>"],
    "filesystem_allowlist": ["<path>"]
  }
}
```

### 4.9. Command result

```json
{
  "schema": "h2.command-result.v1",
  "command_id": "<id>",
  "run_id": "<target-run-id>",
  "action_id": "<durable-action-id>",
  "exit_code": 0,
  "status": "PASS|BLOCK",
  "block_code": "<code-or-null>",
  "started_at": "<utc-iso8601>",
  "completed_at": "<utc-iso8601>",
  "evidence": ["<sha256:path>"]
}
```

### 4.10. Ledger record

```json
{
  "previous_hash": "<sha256>",
  "sequence": 0,
  "timestamp": "<utc-iso8601>",
  "action_id": "<id-or-null>",
  "lease": "<id-or-null>",
  "state_transition": "<from>-><to>",
  "verdict": "PASS|BLOCK",
  "block_code": "<code-or-null>",
  "evidence_refs": ["<sha256:path>"]
}
```

### 4.11. Final verdict

```json
{
  "schema": "h2.final-verdict.v1",
  "target_run_id": "<run-id>",
  "target_node_id": "<node-id>",
  "bundle_id": "<bundle-id>",
  "manifest_sha256": "<sha256>",
  "outcome": "PASS_H2_NODE_READY|BLOCK_*",
  "ledger_head_digest": "<sha256>",
  "evidence_zip_digest": "<sha256>",
  "evidence_zip_size": "<bytes>",
  "committed_receipt_digest": "<sha256-or-null>",
  "child_run_id": "<child-run-id-or-null>",
  "child_verdict_digest": "<sha256-or-null>",
  "key_id": "<installation-or-day0-key-id>"
}
```

---

## 5. Endpoint / capability contract

Базовый origin: `https://chat.h2platform.ru` (pinned, TLS verification обязателен).

| Операция | Метод + путь | Capability | Success | Error |
|---|---|---|---|---|
| Search file by exact name | `GET /api/v1/files/search?filename=<exact>` | `CAP_GUIDE_DOWNLOAD` | `200`, ровно 1 объект | `BLOCK_GUIDE_POINTER` |
| Download file | `GET /api/v1/files/<file_id>/content` | `CAP_GUIDE_DOWNLOAD` / `CAP_BUNDLE_DOWNLOAD` | `200`, байты | `BLOCK_ARTIFACT_HASH`, `BLOCK_OWUI_AUTH` |
| Release floor | `GET /api/v1/bootstrap/release-floor?org=<org>&policy=<policy>` | `CAP_RELEASE_FLOOR_READ` | `200`, signed floor | `BLOCK_RELEASE_ROLLBACK` |
| Reserve enrollment | `POST /api/v1/bootstrap/enrollments/reserve` | `CAP_ENROLLMENT_RESERVE` | `200`, signed reservation receipt | `BLOCK_ENROLLMENT`, `BLOCK_ENROLLMENT_CONFLICT` |
| Commit enrollment | `POST /api/v1/bootstrap/enrollments/commit` | `CAP_ENROLLMENT_COMMIT` | `200`, signed committed receipt | `BLOCK_ENROLLMENT` |
| Abort enrollment | `POST /api/v1/bootstrap/enrollments/abort` | `CAP_ENROLLMENT_COMMIT` | `200`, abort receipt | `BLOCK_ENROLLMENT` |
| Registry verify node | `GET /api/v1/bootstrap/registry/nodes/<node_id>` | `CAP_ENROLLMENT_RESERVE` | `200` | `E_MISSING_NODE`, `E_UNKNOWN_NODE` |
| Provisional E2E submit | `POST /api/v1/bootstrap/e2e/submit` | `CAP_PROVISIONAL_ACCEPTANCE_E2E` | `200`, `status=ACCEPTED` | `BLOCK_CAPABILITY_BINDING` |
| Committed E2E submit | `POST /api/v1/bootstrap/e2e/submit` | `CAP_COMMITTED_ACCEPTANCE_E2E` | `200`, `status=ACCEPTED` | `BLOCK_CAPABILITY_BINDING` |
| Evidence upload | `POST /api/v1/files/` (multipart `file`) | `CAP_EVIDENCE_UPLOAD` | `200`, file_id | `BLOCK_EVIDENCE_INVALID` |

Правила:

- Все запросы — `Authorization: Bearer <opaque-capability>`, никогда `H2_API_KEY`
  напрямую из runner/coordinator.
- Redirects запрещены; смена origin → `BLOCK_OWUI_AUTH`.
- Capability одноразовая, с точным `audience`, `token_id` и replay policy.
- Несовпадение issuer/audience/node/run/workspace/correlation binding →
  `BLOCK_CAPABILITY_BINDING`.

### 5.1. E2E submit request (нормативный)

```json
{
  "schema": "h2.e2e-submit.v1",
  "node": "<target-node-id>",
  "correlation_id": "<correlation-id>",
  "target_run_id": "<run-id>",
  "workspace_id": "<workspace-id>",
  "mode": "new",
  "payload_sha256": "<sha256>"
}
```

Ответ `status=ACCEPTED` обязан содержать: один `request_id`, тот же `node`,
тот же `correlation_id`, `dispatch_count=1`.

---

## 6. Gate-to-command-card mapping

Формат: `GATE ← command card(s) (run_as, mutation)`.

| Gate | Command card | Run-as | Mutation |
|---|---|---|---|
| `PASS_EVIDENCE_LEDGER_READY` | `ledger-init` | user | false (append-only run dir) |
| `PASS_DAY0_PREFLIGHT` | `day0-preflight` | user | false |
| `PASS_RELEASE_FLOOR_VERIFIED` | `floor-verify` | user | false |
| `PASS_GUIDE_VERIFIED` | `guide-fetch`, `guide-verify` | user | false |
| `PASS_BOOTSTRAP_INDEX_VERIFIED` | `index-fetch`, `index-verify` | user | false |
| `PASS_BUNDLE_ACCEPTED` | `bundle-fetch`, `bundle-verify`, `bundle-extract` | user | false |
| `PASS_EXECUTION_ROOT_READY` | `exec-root-publish` | user | false |
| `PASS_TARGET_INVENTORIED` | `inventory-snapshot` | user | false |
| `PASS_ENROLLMENT_DESCRIPTOR_VERIFIED` | `descriptor-fetch`, `descriptor-verify` | user | false |
| `PASS_ENROLLMENT_RESERVED` | `enrollment-reserve` | user | false |
| `PASS_TARGET_BOUND` | `target-bind-check` | user | false |
| `PASS_TARGET_PREFLIGHT` | `target-preflight` | user | false |
| `PASS_CHANGE_PLAN_READY` | `plan-build` | user | false |
| `PASS_MUTATION_APPROVED` | `approval-record` | user | false (подпись одобрения) |
| `PASS_INSTALLER_HANDOFF` | `coordinator-handoff` | user | false |
| `PASS_BACKUP_READY` | `backup-create`, `backup-readback`, `backup-verify` | user/elevated | true |
| `PASS_NODE_IDENTITY_APPLIED` | `node-write`, `node-verify` | user | true |
| `PASS_H2_SHARED_APPLIED` | `h2-shared-install`, `h2-shared-verify` | elevated | true |
| `PASS_ROO_APPLIED` | `vscode-roo-install`, `vscode-roo-verify` | elevated | true |
| `PASS_BRIDGE_APPLIED` | `bridge-install`, `bridge-verify` | elevated | true |
| `PASS_COMPONENT_BLACKBOX` | `component-blackbox` | user | false |
| `PASS_EXACT_NODE_E2E` | `e2e-submit`, `e2e-poll`, `e2e-continue`, `e2e-export`, `e2e-close`, `e2e-idle` | user | false |
| `PASS_ENROLLMENT_COMMITTED` | `enrollment-commit` | user | false (server-side transition) |
| `PASS_IDEMPOTENT_RERUN` | `idempotency-child-run` | user | false |
| `PASS_EVIDENCE_SEALED` | `evidence-collect`, `evidence-seal` | user | false |
| `PASS_H2_NODE_READY` | `final-verdict` | user | false |

Правило: runner не строит команды из prose; он исполняет только command cards из
принятого manifest. `elevated`-карты передаются узкому elevated broker по одной,
только для одобренного `command_id` и подписанного scope.

---

## 7. Compatibility matrix

| Компонент | Минимальная версия | Примечание |
|---|---|---|
| Windows | 10 22H2 / 11 23H2 (x64) | Только x64 |
| PowerShell | 5.1 (встроенный) | НЕ PowerShell Remoting |
| VS Code | 1.95+ | User или Machine install по command card |
| Roo Code | H2-ready signed distribution | Authenticode pinned publisher |
| Python | НЕ Day-0 предпосылка | Всё внутри bootstrap package |
| Git | НЕ Day-0 предпосылка | Всё внутри bootstrap package |
| h2_shared | 0.x (из bundle wheelhouse) | Не требуется для Day-0 client |
| Bridge | installable artifact из bundle | Black box, publisher attestation |
| OWUI origin | `https://chat.h2platform.ru` | Pinned, TLS verify |

Отсутствие в матрице = не поддерживается → `BLOCK_DAY0_PREREQUISITE`.

---

## 8. Release bundle manifest v2

### 8.1. Внешний файловый набор

```text
release/
  release-manifest.v2.json
  release-manifest.v2.sha256
  release-manifest.v2.sig
  compatibility-matrix.json
  acceptance-matrix.json
  policy/
    bootstrap-policy.json
  runner/
    h2-bootstrap-runner.exe
    runner-command-card.json
    elevated-broker.exe
    runtime-deny-policy.json
  node/
    node-writer
    node-validator
    node-schema.json
  h2_shared/
    wheelhouse/
    install-command-card.json
    verify-command-card.json
  vscode_roo/
    install-media/
    install-command-card.json
    verify-command-card.json
  bridge/
    install-media/
    install-command-card.json
    verify-command-card.json
  rollback/
    backup-command-cards/
    restore-command-cards/
    verify-command-cards/
  evidence/
    evidence-schema.json
    collector
    sealer
```

### 8.2. Manifest contract (нормативный)

`release-manifest.v2.json` — массив entries. Для каждого файла:

- `path`, `role`, `size`, `sha256`, `executable`, `installable`, `platform`,
  `component_version`, `provenance`, `required_command_card`.

Плюс:

- canonical signed envelope (см. §4);
- `release_sequence` монотонный + anti-rollback check;
- полный список nested archives;
- каждый archive проверяется до extraction;
- exact extracted file set проверяется после extraction;
- запрещены: absolute/UNC/device paths, `..`, path escape, reserved Windows names,
  trailing dot/space normalization, case-insensitive collisions, ADS, symlink,
  junction, reparse, hardlink, overwrite существующего entry;
- замкнутая ссылочная целостность всех command/verify/backup/restore/compensation ID;
- self-contained runner, signature verifier, credential broker, elevated broker,
  node writer/validator;
- bootstrap-компоненты не зависят от ещё не установленного `h2_shared`.

Покрытие payload — 100%. Лишний/отсутствующий/неописанный файл → BLOCK.

---

## 9. Installer runner state machine

Состояния:

```text
INIT → LEDGER_READY → DAY0_PREFLIGHT → RELEASE_FLOOR_VERIFIED
→ GUIDE_VERIFIED → BOOTSTRAP_INDEX_VERIFIED → BUNDLE_ACCEPTED
→ EXECUTION_ROOT_READY → TARGET_INVENTORIED → DESCRIPTOR_VERIFIED
→ ENROLLMENT_RESERVED → TARGET_BOUND → TARGET_PREFLIGHT
→ CHANGE_PLAN_READY → MUTATION_APPROVED → INSTALLER_HANDOFF
→ BACKUP_READY → NODE_IDENTITY_APPLIED → H2_SHARED_APPLIED
→ ROO_APPLIED → BRIDGE_APPLIED → COMPONENT_BLACKBOX
→ EXACT_NODE_E2E → ENROLLMENT_COMMITTED → IDEMPOTENT_RERUN
→ EVIDENCE_SEALED → H2_NODE_READY
```

Переходы только по PASS. Любой BLOCK → terminal failure evidence.

Runner loop (на каждую command card):

1. Прочитать card, проверить approved `command_id` и scope.
2. `fsync` mutation intent + durable action ID + lease до spawn.
3. Если `run_as=elevated` → передать одному elevated broker.
4. Запустить ровно один command card.
5. Bounded wait terminal result.
6. Проверить quiescence всей transaction и descendant tree.
7. Зафиксировать exit code + result JSON.
8. Пересчитать post-state.
9. Записать `completed_at` и PASS/BLOCK в ledger.

---

## 10. Resume алгоритм

Повторный запуск с тем же `TARGET_RUN_ID`:

1. Прочитать checkpoint ledger.
2. Проверить exclusive target lock, hash chain, fsync-complete head, manifest и
   descriptor signature/SHA.
3. Сверить durable action ID и lease с live transaction и descendant tree.
4. Классифицировать crash point (до spawn / после spawn / после side effect /
   во время verify / во время sealing).
5. Сверить последний checkpoint с live state.
6. Совпадение + quiescent → продолжить со следующего gate.
7. Action выполняется → `BLOCK_OPERATION_IN_FLIGHT`, без takeover.
8. State не совпадает → `BLOCK_RESUME_RECONCILIATION`.
9. Никогда не создавать новый node ID автоматически.

Нормативная crash-recovery таблица — из концепта (§Resume), остаётся в силе.

---

## 11. Rollback алгоритм

1. Остановить выдачу новых mutation actions.
2. Получить terminal/quiescence verdict текущего действия.
3. Read-only reconciliation checkpoint против live state.
4. Определить последний полностью принятый checkpoint.
5. Выбрать exact rollback command cards.
6. Для каждого ресурса — reversibility class + ownership + restore/compensation
   predicate.
7. Восстанавливать компоненты в обратном порядке.
8. Компенсировать registry reservation/commit, services, credentials только
   отдельными одобренными operations.
9. Не восстанавливать donor identity.
10. Проверить post-rollback state + residual-state inventory.
11. Запечатать rollback evidence без secret-bearing backup.

Quiescence не доказана → `BLOCK_OPERATION_IN_FLIGHT`. Restore predicate не
достигнут → `BLOCK_ROLLBACK_FAILED` + residual-state inventory + запрет нового
bootstrap до reconciliation.

---

## 12. Acceptance matrix

Каждый пункт — Given/When/Then из концепта + измеряемый PASS-предикат.

| # | Сценарий | PASS-предикат |
|---|---|---|
| A1 | Happy path | Все gates PASS, `PASS_H2_NODE_READY`, sealed evidence |
| A2 | Existing Roo (KEEP) | `KEEP`, zero mutation, no reinstall |
| A3 | Roo update | Обновление через installer runner, не активная сессия |
| A4 | Trust failure (no launcher) | `PRE_RUN_TRUST_PREREQUISITE_FAILED`, sealed |
| A5 | Trust failure (bad root key/sig/sequence) | Точный BLOCK до запуска исполнимого кода |
| A6 | Missing node | `E_MISSING_NODE`, zero dispatch, zero write |
| A7 | Unknown node | `E_UNKNOWN_NODE`, zero fallback |
| A8 | Reservation conflict | Ровно один receipt, второй `BLOCK_ENROLLMENT_CONFLICT` |
| A9 | Bundle failure | `BLOCK_RELEASE_BUNDLE_NOT_ACCEPTED`/`BLOCK_ARTIFACT_HASH`, target немодифицирован |
| A10 | Interrupted Roo | Тот же `TARGET_RUN_ID`, resume с checkpoint |
| A11 | Elevation | Elevated broker только для одобренного command ID |
| A12 | Timeout | Нет retry/rollback до terminal/quiescence verdict |
| A13 | Rollback | Exact restore/compensation, backup вне evidence |
| A14 | Idempotency | Все `KEEP`, zero drift, `PASS_IDEMPOTENT_RERUN` |
| A15 | Evidence on failure | Ledger + verdict запечатаны при любом terminal outcome |

---

## 13. Открытые решения (с предложенными дефолтами до подтверждения)

| # | Вопрос | Предложенный дефолт (требует подтверждения) |
|---|---|---|
| 1 | Кто выпускает signed enrollment descriptor | H2 control plane; оператор связывает его с новым компьютером вручную до bootstrap |
| 2 | Точные URL/схемы reserve/commit/abort/registry | Закреплены в §5 как `POST /api/v1/bootstrap/enrollments/*`; финальные схемы — после реализации control plane |
| 3 | Scopes `H2_API_KEY` | До подтверждения считать read-only download; enrollment/upload — только отдельные capabilities |
| 4 | Target-owned root без диска `D:` | `C:\H2\` (workspace/staging/backup/evidence под ним) |
| 5 | Формат поставки coordinator/broker/verifier | Self-contained `.exe` внутри release bundle (см. §8.1) |
| 6 | Compatibility matrix v1 | §7 (Win10 22H2 / Win11 23H2, x64, VS Code 1.95+, H2-ready Roo) |
| 7 | Нужна ли установка VS Code | Если Roo уже работает — `KEEP`; иначе `INSTALL` из bundle |
| 8 | Механизм elevation/local IPC broker | Windows Task Scheduler elevation + local named-pipe IPC (подтвердить) |
| 9 | Где runtime-secret после установки | Machine-bound store (DPAPI/TPM) через credential broker; не в `node.json` |
| 10 | E2E endpoint mapping + JSON Schema | §5.1; deadlines: 900 s terminal, 120 s IDLE (закреплены концептом) |
| 11 | Anti-rollback cache после замены диска | Восстановление от server authoritative floor (§5) |
| 12 | Retention/destruction secret-bearing backup | Retention 7 суток, destruction — одобренная command card, вне evidence |

Каждый дефолт помечен `PENDING_CONFIRMATION` и не является нормой до выпуска
соответствующего P0-артефакта.

---

## 14. P0 для реализации (закреплённый перечень)

1. Доверенный self-contained Day-0 bootstrap client (pinned origin + root key).
2. Signed ACTIVE pointer и physical guide.
3. Signed bootstrap index + canonical serialization + schema.
4. Key rotation/revocation + anti-rollback release sequence.
5. Signed enrollment descriptor + server reserve/commit/abort + registry verifier.
6. Локальный credential broker + раздельные opaque capabilities.
7. Immutable signed bundle v2 со 100% SHA coverage.
8. Независимый resumable unelevated coordinator + минимальный elevated broker.
9. Immutable execution root + exclusive lock + durable handoff.
10. Target-parameterized node writer/validator (не зависят от `h2_shared`).
11. Полный installable `h2_shared` wheelhouse.
12. Полные VS Code/Roo installation media + verifier.
13. Installable bridge artifact + publisher attestation + black-box verifier.
14. Command cards для install, verify, backup, restore, compensation.
15. Hash-chained crash-consistent ledger + resume reconciliation.
16. Runtime no-WinRM/no-WSMan deny policy + static scanner.
17. Exact-node E2E acceptance card (фиксированные schema/deadlines/predicates).
18. Idempotency verifier на committed enrollment receipt.
19. Evidence collector, allow-list redactor, signer/attester, sealer.

---

## 15. Test plan (disposable Windows VM)

1. Создать чистую Windows VM (Win11 23H2 x64).
2. Установить H2-ready Roo через утверждённый software channel (Authenticode PASS).
3. Разместить `H2_API_KEY` локально (не в чате).
4. Запустить каноническую bootstrap-задачу.
5. Прогнать acceptance matrix §12 (A1–A15).
6. Для негативных тестов: инъекция bad SHA, bad signature, второй reservation,
   отсутствующий node, unknown node, запрещённый WinRM.
7. Для resume: принудительно прервать на каждом crash point из §10, перезапустить,
   проверить reconciliation.
8. Для rollback: BLOCK после side effect, проверить restore predicate.
9. Запечатать evidence, проверить отсутствие `H2_API_KEY` в любом файле/логе.
10. Записать verdict + evidence ID. Только PASS всех пунктов → `READY_FOR_AUTONOMOUS_BOOTSTRAP`.

---

## 16. История версий

| Версия | Дата | Изменения |
|---|---|---|
| `v1_r0` | 2026-09-01 | Первая спецификация: схемы, endpoint contract, gate mapping, manifest v2, runner state machine, resume/rollback, acceptance matrix, test plan |
