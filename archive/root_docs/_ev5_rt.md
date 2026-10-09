# Evidence — Bridge Victor: BLOCK_OWNERSHIP_LEASE_RENEWAL_COMPAT

**Дата:** 2026-09-01
**Задание:** GUIDE_VICTOR_BRIDGE_ONE_SHOT_v1_r2.md
**Display name:** Victor / node_id: victor
**Target:** DESKTOP-OLJ4LRK (Windows 11, Redmi, Python 3.12.10 x64)

---

## Вердикт

```text
VERDICT=BLOCK
BLOCK_CODE=BLOCK_OWNERSHIP_LEASE_RENEWAL_COMPAT
FAILED_PREDICATE=Bridge 0.5.10 + nats-py 2.15.0: ownership lease renewal использует
  kv.update(last=0), но сервер требует last=<актуальная revision> → wrong last sequence
MISSING_ARTIFACT_OR_PERMISSION=исправленный compatibility launcher (bridge_compat_runner.py),
  патчащий revision handling у kv.create/update, либо bridge wheel совместимый с nats-py 2.15.0
SAFE_NEXT_ACTION=перевыпустить bundle v1_r3 с полным compat для ownership lease
  (revision после kv.create) и повторно пройти live E2E
```

---

## Что выполнено

1. Guide v1_r2: size 17178, SHA256 `3aa9bac4…` — совпал.
2. Bundle v1_r2: size 10766068, SHA256 `f54f025d…` — совпал.
3. Установка успешна до запуска bridge:
   - wheelhouse closure `PASS` (34 active, 39 wheels)
   - `pip install` offline: `owui_roo_bridge==0.5.10`, `h2_shared==0.56.70`,
     `pywin32-ctypes==0.2.3`, `psutil==7.2.2` — установлены, `pip check` OK
   - VSIX `local.roo-bridge@0.6.56` — установлен (KEEP), canary instance ready
   - `node.json` создан BOM-free (node_id=victor)
   - ownership KV bucket `owui_roo_bridge_victor_ownership` создан (history=1, TTL=60)
   - scheduled task `H2_VICTOR_BRIDGE` создан (idempotent)
4. NATS `nats://192.168.99.11:4222` — доступен (server `h2-node-a`, v2.10.2).

## Где остановился

Bridge запускается и доходит до `routing.ready`, но через ~10 секунд
self-terminates:

```text
ownership.claimed owner_id=... rev=0 group=q.node.victor
routing.ready node_id=victor
Subscribed: h2.roo_bridge.node.victor.cmd.> queue=q.node.victor
...
ownership.lost ... reason=lease renewal failed (kv.update last=0): nats: wrong last sequence: 4
routing.terminated (no retry while serving)
```

## Первопричина

Bridge 0.5.10 (`ownership_lease.py`) после `kv.create` сохраняет
`revision = int(getattr(entry, "revision", 0) or 0)`. На nats-py 2.15.0
`entry.revision` возвращает `0` (не фактическую server-side revision), поэтому
первый renew выполняет `kv.update(key, payload, last=0)`, а сервер отвечает
`nats: wrong last sequence: <actual>`. Renewal fatal → routing terminated.

Compat launcher `bridge_compat_runner.py` патчит ТОЛЬКО
`BucketStatus.config.ttl` (для open ownership KV), но НЕ патчит
revision-семантику `kv.create`/`kv.update`. Поэтому lease renewal ломается.

## Почему не обойдено

- Изменять `bridge_compat_runner.py`/`install_victor_bridge.ps1` нельзя:
  bundle SHA-проверка (`SHA256SUMS.txt`) немедленно даёт
  `BLOCK_BUNDLE_HASH_MISMATCH`.
- Пересборка wheel или замена nats-py на другую версию вне bundle запрещена
  (hard rule: не изменять Bridge/h2_shared/Function, closed-world wheelhouse).

## Текущее состояние target

- venv создан, пакеты установлены.
- `node.json`, ownership KV, scheduled task, VSIX, canary instance — готовы.
- Bridge процесс сам останавливается из-за fatal lease renewal (не держит
  routing). Live E2E не достигнут.

---

## Итог

Bundle v1_r2 довёл установку до запуска Bridge, но не проходит live-стадию:
compat launcher не закрывает revision mismatch между Bridge 0.5.10 и
nats-py 2.15.0 в ownership lease renewal. Требуется v1_r3 с полным
ownership-lease compat (корректное чтение `entry.revision` после `kv.create`).
