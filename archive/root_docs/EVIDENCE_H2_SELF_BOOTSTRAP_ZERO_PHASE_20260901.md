# Evidence — H2 SELF_BOOTSTRAP нулевая фаза (hard BLOCK)

**Дата:** 2026-09-01
**Executor run:** Roo (code mode) на целевом Windows-компьютере
**Задание:** PMA_H2_SELF_BOOTSTRAP_IMPLEMENT_INSTALL_LIVE_v1_r0.md (node=`Victor`)
**PMA OWUI file ID:** `d2ad8700-32e9-4390-a60d-7d6049868dbc`
**PMA SHA256:** `0be4c1e40ee4b2da5589cf8b11a560864e62d7a660a763f7220ae0d5682bc238`
**PMA размер:** 39134 байта
**Концепт:** `77c22ebd-23f6-4042-bae0-d878654a3f96` (68747 байт, SHA `ae4e6fe1…`)
**SPEC:** `6d71898a-3b9a-4b05-b8b9-6ec4da9205b1` (29762 байта, SHA `e154907e…`)

---

## Вердикт

```text
VERDICT=PRE_RUN_TRUST_PREREQUISITE_FAILED
TARGET_RUN_ID=null
LOCAL_SEALED_EVIDENCE_NOT_AVAILABLE=true
```

Дополнительный точный hard BLOCK для первого достижимого gate:

```text
VERDICT=BLOCK_CONTROL_PLANE_NOT_IMPLEMENTED
LAST_PASS_GATE=null (нет Day-0 launcher → нет run ledger)
```

---

## 1. Причина PRE_RUN_TRUST_PREREQUISITE_FAILED

Концепт и SPEC требуют `H2-ready Roo` из подписанного H2 Roo distribution с
закреплённым публичным корневым ключом и Day-0 bootstrap client. На данном
компьютере:

- нет H2 Roo launcher;
- нет Day-0 bootstrap client;
- нет root signing public key / `key_id`;
- нет локального credential broker;
- нет machine-bound Day-0 attestation key.

Текущая Roo-сессия — generic Roo Code, запущенная из произвольной рабочей
директории. Поэтому обычный run ещё не существует, `TARGET_RUN_ID` не создан,
локально sealed evidence не обещается (по нормативной оговорке §"Преrequisite"
PMA).

**Доказательство:** локальная файловая инвентаризация целевой директории не
обнаружила ни `node.json`, ни `h2_shared`, ни H2 bootstrap-компонентов, ни
signing/trust-артефактов.

---

## 2. Control-plane endpoint probe

Запросы выполнялись с pinned origin `https://chat.h2platform.ru`, TLS verify
включён, redirects запрещены.

| Endpoint | HTTP | Content-Type | Размер | Вывод |
|---|---|---|---|---|
| `GET /api/v1/bootstrap/release-floor` | 200 | `text/html` | 11098 | SPA fallback, НЕ API |
| `GET /api/v1/bootstrap/registry/nodes/X` | 200 | `text/html` | 11098 | SPA fallback, НЕ API |
| `GET /api/v1/bootstrap/enrollments/reserve` | 200 | `text/html` | 11098 | SPA fallback, НЕ API |

Все перечисленные в SPEC `h2.*` endpoints отсутствуют. Оригин обслуживает только
OWUI Files API и SPA-оболочку Open WebUI.

**Вывод:** control plane не deployed → `BLOCK_CONTROL_PLANE_NOT_IMPLEMENTED`.

---

## 3. Scope H2_API_KEY (что реально доступно)

Пробы (значение ключа не выводилось и не записывалось):

- `GET /api/v1/files/` → 200, JSON `{items, total}` (read list) — РАБОТАЕТ
- `GET /api/v1/files/{id}/content` → 200 (read) — РАБОТАЕТ
- `GET /api/v1/files/search?filename=…` → 200/404 (search) — РАБОТАЕТ
- `POST /api/v1/files/` multipart → 200 (upload) — РАБОТАЕТ
- `DELETE /api/v1/files/{id}` → не проверялся (не требовался)

Ключ НЕ выдаёт enrollment, capability exchange, release floor, registry verify,
E2E submit/commit. Это только OWUI Files API key, а не контрольная плоскость H2.

---

## 4. Инвентаризация обязательных объектов PMA

| Объект (по PMA §access inventory) | Статус | Evidence |
|---|---|---|
| Day-0/Roo distribution repository | ABSENT | нет в проекте, нет в git remotes |
| Control-plane repository | ABSENT | origin = FORMYLA (не H2) |
| Bootstrap/bundle repository | ABSENT | origin = FORMYLA (не H2) |
| Bridge repository (source) | ABSENT | в OWUI только wheel 0.5.10 для heavy02 |
| `h2_shared` source/release | ABSENT (только как dependency bridge) | METADATA требует `h2_shared>=0.41.0`, самого пакета нет |
| Signing service | ABSENT | нет signer, ключей, policy |
| Publisher certificate / Authenticode pipeline | ABSENT | нет pinned publisher identity |
| OWUI destination | ПРИСУТСТВУЕТ (Files API) | upload/download/list/search работают |
| Disposable Windows VM | ABSENT | нет VM ID/snapshot/contour |
| Target | ПРИСУТСТВУЕТ (этот компьютер) | — |
| Enrollment authority | ABSENT | нет endpoint, нет descriptor |

Соответствующие hard BLOCK:

```text
BLOCK_DEPENDENCY_REPOSITORY
BLOCK_DEPENDENCY_WRITE_ACCESS
BLOCK_DEPENDENCY_SIGNING
BLOCK_DEPENDENCY_DEPLOYMENT
BLOCK_DEPENDENCY_VM
BLOCK_DEPENDENCY_ENROLLMENT
```

---

## 5. Что НЕ выполнено и почему это нельзя обойти

1. Нельзя реализовать P0 локально и тем же run принять их как доверенные:
   root trust / signing authority нельзя создавать на недоверенном target.
2. Единственный git remote — `https://github.com/victorkrivenko4949-commits/FORMYLA.git`
   (математический tutor), не содержит H2 bootstrap/control-plane/bridge source.
3. Bridge wheel `owui_roo_bridge-0.5.10` — это NATS-релей для существующего
   heavy02-контура, требующий `h2_shared>=0.41.0` и NATS; он НЕ является
   self-contained bootstrap installer для нового компьютера и не подписан
   approved release authority.
4. Нет disposable Windows VM, нет enrollment descriptor, нет signed ACTIVE
   pointer/physical guide/bootstrap index в OWUI (search по
   `GUIDE_H2_SELF_BOOTSTRAP_ACTIVE.md` и `GUIDE_H2_SELF_BOOTSTRAP_v1_r0.md` → 404).

---

## 6. Рекомендуемый safe next action

```text
OWNER_REQUIRED=H2 software-distribution owner / control-plane owner
SAFE_NEXT_ACTION=Предоставить доступ к authoritative H2 repositories,
signing pipeline, control-plane contour и disposable Windows VM;
затем перезапустить PMA с доверенным H2-ready Roo launcher.
```

До этого дальнейшая установка запрещена. Обходной shim, donor config или
продолжение мутаций не выполняются.
