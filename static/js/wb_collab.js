// FORMYLA Whiteboard - LiveKit collaborative sync.
// Bridges static/js/whiteboard.js (window.WB) with static/js/wb_meet.js
// (LiveKit room) via the room data-channel.  Listens for the custom
// events "wb-meet-room" and "wb-meet-leave" that wb_meet.js dispatches.
//
// Wire format (UTF-8 JSON, fields:):
//   v=1, t="hello", from=identity
//   v=1, t="snapshot", state= objects+nextId
//   v=1, t="op", op= a diff produced by whiteboard.js
//
// "op" mirrors what whiteboard.js emits via window.__wbBroadcast.
(function () {
  "use strict";

  var room = null;
  var lk = null;
  var myIdentity = null;
  var dataHandler = null;
  var prevBroadcast = null;
  var helloTimer = 0;
  var receivedSnapshot = false;

  function log()  { try { console.log.apply(console, ["[wb_collab]"].concat([].slice.call(arguments))); } catch (e) {} }
  function warn() { try { console.warn.apply(console, ["[wb_collab]"].concat([].slice.call(arguments))); } catch (e) {} }

  function encode(obj) { return new TextEncoder().encode(JSON.stringify(obj)); }
  function decode(bytes) { return JSON.parse(new TextDecoder().decode(bytes)); }

  function publishAll(packet) {
    if (!room || !room.localParticipant) return;
    try {
      room.localParticipant.publishData(encode(packet), { reliable: true });
    } catch (e) {
      try {
        if (lk && lk.DataPacket_Kind) {
          room.localParticipant.publishData(encode(packet), lk.DataPacket_Kind.RELIABLE);
        }
      } catch (e2) { warn("publishAll failed:", e, e2); }
    }
  }

  function publishTo(packet, identities) {
    if (!room || !room.localParticipant) return;
    if (!Array.isArray(identities) || !identities.length) return;
    try {
      room.localParticipant.publishData(encode(packet), {
        reliable: true,
        destinationIdentities: identities
      });
    } catch (e) {
      try {
        if (lk && lk.DataPacket_Kind) {
          room.localParticipant.publishData(encode(packet), lk.DataPacket_Kind.RELIABLE, identities);
        }
      } catch (e2) { warn("publishTo failed:", e, e2); }
    }
  }

  function onDataReceived(payload, participant) {
    var fromId = (participant && participant.identity) ? participant.identity : "?";
    var msg;
    try { msg = decode(payload); } catch (e) { warn("bad packet from", fromId, e); return; }
    if (!msg || typeof msg !== "object") return;

    if (msg.t === "hello") {
      if (!window.WB || typeof window.WB.getSnapshot !== "function") return;
      try {
        var snap = window.WB.getSnapshot();
        publishTo({ v: 1, t: "snapshot", state: snap }, [fromId]);
      } catch (e) { warn("snapshot reply failed:", e); }
      return;
    }

    if (msg.t === "snapshot") {
      if (receivedSnapshot) return;
      if (!msg.state || !Array.isArray(msg.state.objects)) return;
      if (!window.WB || typeof window.WB.applyRemoteOp !== "function") return;
      try {
        window.WB.applyRemoteOp({ op: "snapshot", state: msg.state });
        receivedSnapshot = true;
        log("got snapshot from", fromId, "objects:", msg.state.objects.length);
      } catch (e) { warn("apply snapshot failed:", e); }
      return;
    }

    if (msg.t === "op") {
      if (!msg.op || typeof msg.op !== "object") return;
      if (!window.WB || typeof window.WB.applyRemoteOp !== "function") return;
      try { window.WB.applyRemoteOp(msg.op); }
      catch (e) { warn("apply remote op failed:", e); }
      return;
    }
  }

  function localBroadcaster(op) {
    if (!room) return;
    publishAll({ v: 1, t: "op", op: op });
  }

  function attach(detail) {
    detach();
    room = detail.room;
    lk = detail.lk;
    myIdentity = detail.identity;
    if (!room || !lk) { warn("attach: missing room/lk"); return; }

    dataHandler = onDataReceived;
    try { room.on(lk.RoomEvent.DataReceived, dataHandler); }
    catch (e) { warn("room.on(DataReceived) failed:", e); }

    prevBroadcast = window.__wbBroadcast || null;
    window.__wbBroadcast = localBroadcaster;

    receivedSnapshot = false;
    clearTimeout(helloTimer);
    helloTimer = setTimeout(function () {
      publishAll({ v: 1, t: "hello", from: myIdentity });
      log("sent hello, waiting for snapshot...");
    }, 400);

    log("attached identity=" + myIdentity);
  }

  function detach() {
    clearTimeout(helloTimer);
    helloTimer = 0;
    if (room && lk && dataHandler) {
      try { room.off(lk.RoomEvent.DataReceived, dataHandler); } catch (e) {}
    }
    dataHandler = null;
    if (window.__wbBroadcast === localBroadcaster) {
      window.__wbBroadcast = prevBroadcast || null;
    }
    prevBroadcast = null;
    room = null;
    lk = null;
    myIdentity = null;
    receivedSnapshot = false;
  }

  window.addEventListener("wb-meet-room",  function (e) { try { attach(e.detail || {}); } catch (err) { warn("attach err:", err); } });
  window.addEventListener("wb-meet-leave", function ()  { try { detach(); } catch (err) { warn("detach err:", err); } });

  window.WB_COLLAB = { attach: attach, detach: detach, isAttached: function () { return !!room; } };
})();
