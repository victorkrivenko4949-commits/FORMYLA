// FORMYLA.net Whiteboard - LiveKit collaborative sync.
// Bridges static/js/whiteboard.js (window.WB) with static/js/wb_meet.js
// (LiveKit room) via the room data-channel.  Listens for the custom
// events "wb-meet-room", "wb-meet-leave" and "wb-meet-summon" that
// wb_meet.js dispatches.
//
// Wire format (UTF-8 JSON):
//   { v:2, c:<clientId>, n:<name>, t:"hello" }
//   { v:2, c, n, t:"snapshot", state:{objects,nextId} }   // merge, never wipes
//   { v:2, c, n, t:"op", op:<diff from whiteboard.js>, all?:true }
//   { v:2, c, n, t:"view", view:{x,y,scale,w,h} }          // «позвать всех к себе»
//
// COLLAB_SAFE_V2 — почему раньше «удалялось то, что писал»:
//   1. id объектов — обычный счётчик 1,2,3… у КАЖДОГО участника.  Чужой
//      объект с таким же id перезаписывал мой (upsert по id).  Теперь чужие
//      id получают префикс "<clientId>:", коллизий нет.
//   2. Снимок состояния (snapshot) целиком ЗАМЕНЯЛ доску получателя.
//      Теперь любой snapshot только дополняет (merge).
//   3. "clear" рассылался не только по кнопке «Очистить», но и когда
//      участник стирал/отменял свой последний штрих (0 объектов) — у всех
//      пропадало всё.  Теперь такой clear удаляет только объекты отправителя;
//      полная очистка — только по явному нажатию кнопки #wbClear.
(function () {
  "use strict";

  var room = null;
  var lk = null;
  var myIdentity = null;
  var myName = "";
  var dataHandler = null;
  var prevBroadcast = null;
  var helloTimer = 0;
  var explicitClearUntil = 0;

  function log()  { try { console.log.apply(console, ["[wb_collab]"].concat([].slice.call(arguments))); } catch (e) {} }
  function warn() { try { console.warn.apply(console, ["[wb_collab]"].concat([].slice.call(arguments))); } catch (e) {} }

  // ── Стабильный id клиента (переживает переподключения и перезагрузку) ──
  var myCid = (function () {
    try {
      var v = localStorage.getItem("wb_client_id");
      if (!v || !/^[a-z0-9]{6,12}$/.test(v)) {
        v = Math.random().toString(36).slice(2, 10);
        localStorage.setItem("wb_client_id", v);
      }
      return v;
    } catch (e) { return Math.random().toString(36).slice(2, 10); }
  })();

  function encode(obj) { return new TextEncoder().encode(JSON.stringify(obj)); }
  function decode(bytes) { return JSON.parse(new TextDecoder().decode(bytes)); }

  function packet(t, extra) {
    var p = { v: 2, c: myCid, n: myName || "", t: t };
    if (extra) for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) p[k] = extra[k];
    return p;
  }

  function publishAll(p) {
    if (!room || !room.localParticipant) return;
    try {
      room.localParticipant.publishData(encode(p), { reliable: true });
    } catch (e) {
      try {
        if (lk && lk.DataPacket_Kind) room.localParticipant.publishData(encode(p), lk.DataPacket_Kind.RELIABLE);
      } catch (e2) { warn("publishAll failed:", e, e2); }
    }
  }

  function publishTo(p, identities) {
    if (!room || !room.localParticipant) return;
    if (!Array.isArray(identities) || !identities.length) return;
    try {
      room.localParticipant.publishData(encode(p), { reliable: true, destinationIdentities: identities });
    } catch (e) {
      try {
        if (lk && lk.DataPacket_Kind) room.localParticipant.publishData(encode(p), lk.DataPacket_Kind.RELIABLE, identities);
      } catch (e2) { warn("publishTo failed:", e, e2); }
    }
  }

  // ── Пространство имён id ───────────────────────────────────────────
  function inId(id, cid) {
    if (typeof id === "number") return cid + ":" + id;
    if (typeof id === "string") {
      var pref = myCid + ":";
      if (id.indexOf(pref) === 0) {
        var n = Number(id.slice(pref.length));
        if (!isNaN(n)) return n;
      }
      return id;
    }
    return id;
  }
  function cleanObj(o) {
    var c = {};
    for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k) && k !== "_img") c[k] = o[k];
    return c;
  }
  function inObj(o, cid) {
    var c = cleanObj(o);
    c.id = inId(o.id, cid);
    return c;
  }
  function isOwnedBy(id, cid) {
    return typeof id === "string" && id.indexOf(cid + ":") === 0;
  }
  function localObjects() {
    try {
      if (window.WB && typeof window.WB.getSnapshot === "function") {
        var s = window.WB.getSnapshot();
        return (s && Array.isArray(s.objects)) ? s.objects : [];
      }
    } catch (e) {}
    return [];
  }
  function localNextId() {
    try { var s = window.WB.getSnapshot(); return s && s.nextId || 1; } catch (e) { return 1; }
  }
  function applyOps(adds, updates, removes) {
    if (!window.WB || typeof window.WB.applyRemoteOp !== "function") return;
    if (!adds.length && !updates.length && !removes.length) return;
    window.WB.applyRemoteOp({ op: "ops", adds: adds, updates: updates, removes: removes, nextId: localNextId() });
  }

  // Слить чужой снимок с нашей доской.  dropMissingOfSender=true —
  // дополнительно убрать объекты отправителя, которых в снимке уже нет
  // (он их стёр).  Чужие и свои объекты не трогаем никогда.
  function mergeSnapshot(state, cid, dropMissingOfSender) {
    if (!state || !Array.isArray(state.objects)) return;
    var adds = state.objects.map(function (o) { return inObj(o, cid); });
    var removes = [];
    if (dropMissingOfSender) {
      var present = new Set(adds.map(function (o) { return o.id; }));
      localObjects().forEach(function (o) {
        if (isOwnedBy(o.id, cid) && !present.has(o.id)) removes.push(o.id);
      });
    }
    applyOps(adds, [], removes);
  }

  function sendMySnapshot(toIdentities) {
    var objs = localObjects();
    if (!objs.length) return;
    var p = packet("snapshot", { state: { objects: objs.map(cleanObj), nextId: localNextId() } });
    if (toIdentities) publishTo(p, toIdentities); else publishAll(p);
  }

  // ── Приём ──────────────────────────────────────────────────────────
  function onDataReceived(payload, participant) {
    var fromId = (participant && participant.identity) ? participant.identity : "?";
    var msg;
    try { msg = decode(payload); } catch (e) { warn("bad packet from", fromId, e); return; }
    if (!msg || typeof msg !== "object") return;
    var cid = (typeof msg.c === "string" && msg.c) ? msg.c : ("p_" + fromId);
    if (cid === myCid) return;

    if (msg.t === "hello") {
      sendMySnapshot([fromId]);
      return;
    }

    if (msg.t === "snapshot") {
      try { mergeSnapshot(msg.state, cid, false); log("merged snapshot from", msg.n || fromId); }
      catch (e) { warn("apply snapshot failed:", e); }
      return;
    }

    if (msg.t === "view") {
      if (msg.view) goToView(msg.view, msg.n || "Участник");
      return;
    }

    if (msg.t === "op") {
      var op = msg.op;
      if (!op || typeof op !== "object") return;
      if (!window.WB || typeof window.WB.applyRemoteOp !== "function") return;
      try {
        if (op.op === "snapshot") {
          mergeSnapshot(op.state, cid, true);
        } else if (op.op === "clear") {
          if (msg.all) {
            window.WB.applyRemoteOp({ op: "clear", nextId: localNextId() });
          } else {
            var rm = localObjects().filter(function (o) { return isOwnedBy(o.id, cid); }).map(function (o) { return o.id; });
            applyOps([], [], rm);
          }
        } else if (op.op === "ops") {
          var adds = (Array.isArray(op.adds) ? op.adds : []).map(function (o) { return inObj(o, cid); });
          var upds = (Array.isArray(op.updates) ? op.updates : []).map(function (o) { return inObj(o, cid); });
          var rems = (Array.isArray(op.removes) ? op.removes : []).map(function (id) { return inId(id, cid); });
          applyOps(adds, upds, rems);
        } else {
          window.WB.applyRemoteOp(op);
        }
      } catch (e) { warn("apply remote op failed:", e); }
      return;
    }
  }

  // ── Отправка локальных изменений ───────────────────────────────────
  function localBroadcaster(op) {
    if (!room || !op) return;
    try {
      if (op.op === "clear") {
        publishAll(packet("op", { op: { op: "clear", nextId: op.nextId }, all: Date.now() < explicitClearUntil }));
        return;
      }
      if (op.op === "snapshot" && op.state && Array.isArray(op.state.objects)) {
        publishAll(packet("op", { op: { op: "snapshot", state: { objects: op.state.objects.map(cleanObj), nextId: op.state.nextId } } }));
        return;
      }
      if (op.op === "ops") {
        publishAll(packet("op", { op: {
          op: "ops",
          adds: (op.adds || []).map(cleanObj),
          updates: (op.updates || []).map(cleanObj),
          removes: op.removes || [],
          nextId: op.nextId
        } }));
        return;
      }
      publishAll(packet("op", { op: op }));
    } catch (e) { warn("broadcast failed:", e); }
  }

  // Явная очистка — только кнопка «Очистить доску».
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#wbClear")) explicitClearUntil = Date.now() + 3000;
  }, true);

  // ── «Позвать всех к себе»: чтение/установка вида доски ─────────────
  // whiteboard.js не экспортирует view, поэтому читаем его из матрицы
  // setTransform, а двигаем доску штатными событиями (ctrl+wheel и
  // панорамирование средней кнопкой) — ровно так, как это делает рука.
  var canvasEl = document.getElementById("wbCanvas");
  var lastView = { x: 0, y: 0, scale: 1 };
  var prevWasIdentity = false;
  function hookView() {
    if (!canvasEl) return;
    var ctx;
    try { ctx = canvasEl.getContext("2d"); } catch (e) { return; }
    if (!ctx || ctx.__wbViewHooked) return;
    var orig = ctx.setTransform;
    ctx.setTransform = function (a, b, c, d, e, f) {
      if (arguments.length === 6 && typeof a === "number") {
        var dpr = window.devicePixelRatio || 1;
        var s = a / dpr, x = e / dpr, y = f / dpr;
        var identity = Math.abs(s - 1) < 1e-9 && Math.abs(x) < 1e-9 && Math.abs(y) < 1e-9;
        if (!identity) lastView = { x: x, y: y, scale: s };
        else if (prevWasIdentity) lastView = { x: 0, y: 0, scale: 1 };
        prevWasIdentity = identity;
      }
      return orig.apply(this, arguments);
    };
    ctx.__wbViewHooked = true;
  }
  hookView();

  function frame() { return new Promise(function (res) { requestAnimationFrame(function () { res(); }); }); }
  function clientRect() { return canvasEl.getBoundingClientRect(); }

  function wheelAt(cx, cy, deltaY) {
    var r = clientRect();
    canvasEl.dispatchEvent(new WheelEvent("wheel", {
      deltaY: deltaY, deltaMode: 0, ctrlKey: true,
      clientX: r.left + cx, clientY: r.top + cy, bubbles: true, cancelable: true
    }));
  }
  function fakePan(cx, cy, dx, dy) {
    var r = clientRect();
    var base = { bubbles: true, cancelable: true, pointerId: 7777, pointerType: "mouse", isPrimary: true };
    function ev(type, extra) {
      var init = {};
      for (var k in base) init[k] = base[k];
      for (var j in extra) init[j] = extra[j];
      return new PointerEvent(type, init);
    }
    canvasEl.dispatchEvent(ev("pointerdown", { button: 1, buttons: 4, clientX: r.left + cx, clientY: r.top + cy }));
    canvasEl.dispatchEvent(ev("pointermove", { button: -1, buttons: 4, clientX: r.left + cx + dx, clientY: r.top + cy + dy }));
    canvasEl.dispatchEvent(ev("pointerup",   { button: 1, buttons: 0, clientX: r.left + cx + dx, clientY: r.top + cy + dy }));
  }

  var goingTo = false;
  async function goToView(v, who) {
    if (!canvasEl || goingTo) return;
    if (!v || !(v.scale > 0) || !(v.w > 0) || !(v.h > 0)) return;
    goingTo = true;
    try {
      hookView();
      var r = clientRect();
      if (!r.width || !r.height) return;
      var cx = r.width / 2, cy = r.height / 2;
      // Центр видимой области ведущего в мировых координатах.
      var wcx = (v.w / 2 - v.x) / v.scale;
      var wcy = (v.h / 2 - v.y) / v.scale;
      // Вписываем область ведущего в наш холст.
      var target = v.scale * Math.min(r.width / v.w, r.height / v.h);
      target = Math.min(8, Math.max(0.1, target));

      for (var i = 0; i < 80; i++) {
        var cur = lastView.scale;
        var err = Math.log(target / cur);
        if (Math.abs(err) < 0.02) break;
        wheelAt(cx, cy, err > 0 ? -100 : 100);
        await frame();
        var after = lastView.scale;
        if (Math.abs(after - cur) < 1e-6) break;        // колёсико не сработало
        var err2 = Math.log(target / after);
        if (err * err2 < 0) {                           // перелетели
          if (Math.abs(err2) > Math.abs(err)) { wheelAt(cx, cy, err2 > 0 ? -100 : 100); await frame(); }
          break;
        }
      }

      var s = lastView.scale;
      var tx = cx - wcx * s, ty = cy - wcy * s;
      var dx = tx - lastView.x, dy = ty - lastView.y;
      if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
        fakePan(cx, cy, dx, dy);
        await frame();
      }
      try { if (window.WB_MEET && window.WB_MEET.status) window.WB_MEET.status((who || "Участник") + " позвал всех к себе", "ok"); } catch (e) {}
      log("moved to view of", who, lastView);
    } catch (e) {
      warn("goToView failed:", e);
    } finally { goingTo = false; }
  }

  function summon() {
    if (!room || !canvasEl) return;
    hookView();
    var r = clientRect();
    publishAll(packet("view", { view: { x: lastView.x, y: lastView.y, scale: lastView.scale, w: r.width, h: r.height } }));
    log("summon sent", lastView);
  }

  // ── Подключение к комнате ──────────────────────────────────────────
  function attach(detail) {
    detach();
    room = detail.room;
    lk = detail.lk;
    myIdentity = detail.identity;
    myName = detail.name || "";
    if (!room || !lk) { warn("attach: missing room/lk"); return; }

    dataHandler = onDataReceived;
    try { room.on(lk.RoomEvent.DataReceived, dataHandler); }
    catch (e) { warn("room.on(DataReceived) failed:", e); }

    prevBroadcast = window.__wbBroadcast || null;
    window.__wbBroadcast = localBroadcaster;
    hookView();

    clearTimeout(helloTimer);
    helloTimer = setTimeout(function () {
      publishAll(packet("hello"));      // попросить у всех их состояние
      sendMySnapshot(null);             // и показать всем своё (merge у них)
      log("sent hello + own snapshot");
    }, 400);

    log("attached identity=" + myIdentity + " cid=" + myCid + (detail.rejoin ? " (rejoin)" : ""));
  }

  function detach() {
    clearTimeout(helloTimer);
    helloTimer = 0;
    if (room && lk && dataHandler) {
      try { room.off(lk.RoomEvent.DataReceived, dataHandler); } catch (e) {}
    }
    dataHandler = null;
    if (window.__wbBroadcast === localBroadcaster) window.__wbBroadcast = prevBroadcast || null;
    prevBroadcast = null;
    room = null;
    lk = null;
    myIdentity = null;
  }

  window.addEventListener("wb-meet-room",   function (e) { try { attach(e.detail || {}); } catch (err) { warn("attach err:", err); } });
  window.addEventListener("wb-meet-leave",  function ()  { try { detach(); } catch (err) { warn("detach err:", err); } });
  window.addEventListener("wb-meet-summon", function ()  { try { summon(); } catch (err) { warn("summon err:", err); } });

  window.WB_COLLAB = {
    attach: attach, detach: detach, summon: summon, goToView: goToView,
    isAttached: function () { return !!room; },
    clientId: myCid, getView: function () { return lastView; }
  };
})();
