/**
 * FORMYLA — Beautiful Pen Stroke Renderer.
 *
 * Replaces the «лоtaня прямых отрезков» rendering of the default pen tool
 * with a smooth, ink-like stroke:
 *
 *   1. Catmull-Rom -> Bézier smoothing of the polyline (no sharp corners).
 *   2. Variable thickness modulated by pointer SPEED: a slow pen leaves a
 *      thicker line, a fast pen leaves a thinner one — mimics ink/pressure.
 *      If the raw pointer reported `pressure`, that signal is mixed in too.
 *   3. Tapered ends so each stroke starts and ends at near-zero thickness,
 *      like a real felt-tip pen — no blunt rectangles at the stroke caps.
 *
 * The renderer is purely visual: it never mutates the input `points` array.
 * Storage format stays backward-compatible — old strokes (points = [{x,y}])
 * still render fine, they just lack the speed signal.
 *
 * Public API:
 *   FormylaPen.drawSmoothStroke(ctx, points, opts)
 *   FormylaPen.smoothPath(points)              -> array of bezier segments
 *   FormylaPen.MIN_THICKNESS / MAX_THICKNESS_MULT
 *
 * `opts`:
 *   color      : CSS color (default "#e6e8ff")
 *   thickness  : base line width in px (default 2)
 *   smoothing  : 0..1, how aggressive Catmull-Rom is (default 0.55)
 *   speedVar   : 0..1, how much speed affects thickness (default 0.55)
 *   minScale   : lower clamp for thickness multiplier (default 0.45)
 *   maxScale   : upper clamp for thickness multiplier (default 1.65)
 *   taper      : 0..1, how much the head/tail thin out (default 0.55)
 *
 * Each point may carry optional `t` (timestamp ms) and `p` (pressure 0..1).
 * If missing, defaults are used.
 */
(function (root) {
  "use strict";

  // ── Tunables surfaced for tests / future debugging. ──────────────────
  var MIN_THICKNESS = 0.4;          // never disappear completely
  var MAX_THICKNESS_MULT = 2.0;     // hard upper safety bound

  /**
   * Convert a polyline into an array of cubic-bezier segments using a
   * uniform Catmull-Rom spline. Tension `s` ∈ [0,1] tunes how much the
   * curve hugs the original points (1 = Catmull-Rom canonical, 0 = lines).
   *
   * Returns: [{p0,c1,c2,p1, len}] ready for `bezierCurveTo`.
   */
  function smoothPath(points, s) {
    if (s == null) s = 0.55;
    var n = points.length;
    if (n < 2) return [];
    // For 2 points we still emit a single straight cubic so the caller
    // can use a unified rendering pipeline.
    var segs = [];
    for (var i = 0; i < n - 1; i++) {
      var p0 = points[i === 0 ? i : i - 1];
      var p1 = points[i];
      var p2 = points[i + 1];
      var p3 = points[i + 2 < n ? i + 2 : i + 1];

      var c1 = {
        x: p1.x + ((p2.x - p0.x) / 6) * s,
        y: p1.y + ((p2.y - p0.y) / 6) * s,
      };
      var c2 = {
        x: p2.x - ((p3.x - p1.x) / 6) * s,
        y: p2.y - ((p3.y - p1.y) / 6) * s,
      };
      segs.push({
        p0: { x: p1.x, y: p1.y },
        c1: c1,
        c2: c2,
        p1: { x: p2.x, y: p2.y },
        len: Math.hypot(p2.x - p1.x, p2.y - p1.y),
      });
    }
    return segs;
  }

  /**
   * Estimate per-point speed (px / ms). Falls back to a synthetic constant
   * when no timestamps are available so the rest of the pipeline still
   * produces a pleasing variable-thickness look.
   */
  function pointSpeeds(points) {
    var n = points.length;
    var speeds = new Array(n);
    if (n === 0) return speeds;
    // First & last get the speed of their neighbor — avoids "0" at the
    // very edges which would taper to nothing because of bad data.
    var hasTs = points.some(function (p) { return p && typeof p.t === "number"; });
    if (!hasTs) {
      // No timestamps -> use *distance* between consecutive points as
      // a proxy for "slowness": short steps == slow == thick.
      for (var i = 0; i < n; i++) {
        var prev = points[Math.max(0, i - 1)];
        var next = points[Math.min(n - 1, i + 1)];
        var d = Math.hypot(next.x - prev.x, next.y - prev.y);
        // Map: small step (~1-2 px)  slow; big step (~10+)  fast.
        // Speed unit is arbitrary, only the *order* matters for the
        // downstream normalisation step below.
        speeds[i] = d;
      }
      return speeds;
    }
    for (var j = 0; j < n; j++) {
      var pPrev = points[Math.max(0, j - 1)];
      var pNext = points[Math.min(n - 1, j + 1)];
      var dt = Math.max(1, (pNext.t || 0) - (pPrev.t || 0));
      var dist = Math.hypot(pNext.x - pPrev.x, pNext.y - pPrev.y);
      speeds[j] = dist / dt; // px / ms
    }
    return speeds;
  }

  /** Robust percentile-based normalisation -> [0..1]. */
  function normalize01(arr) {
    if (!arr.length) return arr.slice();
    var sorted = arr.slice().sort(function (a, b) { return a - b; });
    var lo = sorted[Math.floor(sorted.length * 0.1)];
    var hi = sorted[Math.floor(sorted.length * 0.9)];
    if (hi <= lo) { hi = lo + 1e-6; }
    return arr.map(function (v) {
      return Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    });
  }

  /**
   * Compute per-point thickness multiplier.
   *   thick ≈ base * lerp(maxScale, minScale, speed_norm) * taperEdges
   * with optional `pressure` blended in.
   */
  function thicknessProfile(points, opts) {
    var n = points.length;
    if (!n) return [];
    var speedVar = opts.speedVar != null ? opts.speedVar : 0.55;
    var minScale = opts.minScale != null ? opts.minScale : 0.45;
    var maxScale = opts.maxScale != null ? opts.maxScale : 1.65;
    var taper    = opts.taper    != null ? opts.taper    : 0.55;

    var speeds = normalize01(pointSpeeds(points));

    // Edge taper window: first ~6% and last ~6% of the stroke smoothly
    // ramp to (1 - taper) thickness so the stroke head/tail look ink-like.
    var window = Math.max(2, Math.floor(n * 0.06));

    var result = new Array(n);
    for (var i = 0; i < n; i++) {
      // Speed effect: fast = thin, slow = thick.
      var sNorm = speeds[i] || 0;                  // 0..1, 1 = fastest
      var speedMult = maxScale - (maxScale - minScale) * sNorm;
      // Blend speed with original pressure (if any) so HW pens still work.
      var p = points[i];
      if (p && typeof p.p === "number" && p.p > 0) {
        // Press 0..1 -> 0.6..1.4 multiplicative bias.
        var pressMult = 0.6 + 0.8 * Math.max(0, Math.min(1, p.p));
        speedMult = speedMult * (1 - speedVar) + pressMult * speedVar;
      }
      // Linear taper at the head/tail.
      var taperMult = 1;
      if (i < window) {
        taperMult = (1 - taper) + (taper * (i / window));
      } else if (i > n - 1 - window) {
        var k = (n - 1 - i) / window;
        taperMult = (1 - taper) + (taper * k);
      }
      var mult = speedMult * taperMult;
      // Safety clamp.
      mult = Math.max(0.05, Math.min(MAX_THICKNESS_MULT, mult));
      result[i] = mult;
    }
    return result;
  }

  /**
   * Render a stroke as a series of small filled quad ribbons whose width
   * follows the per-point thickness profile. This is the *correct* way to
   * get variable-width strokes — `ctx.lineWidth` cannot vary along a path.
   */
  function drawSmoothStroke(ctx, points, opts) {
    opts = opts || {};
    if (!points || points.length < 1) return;
    var color = opts.color || "#e6e8ff";
    var base = Math.max(0.5, Number(opts.thickness) || 2);

    ctx.save();
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    if (points.length === 1) {
      // Single click: just paint a dot at the base radius.
      ctx.beginPath();
      ctx.arc(points[0].x, points[0].y, base * 0.55, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      return;
    }

    // ── Build a densified smoothed polyline ───────────────────────────
    // We sample each Catmull-Rom segment at a step proportional to its
    // length: ~1 sample every 2-3 px. This gives us a *dense* polyline
    // along which we can vary thickness smoothly.
    var segs = smoothPath(points, opts.smoothing);
    var dense = [];
    var thickIn = thicknessProfile(points, opts); // per ORIGINAL point
    // Anchor: we associate each segment index with the two original-point
    // thicknesses (start = thickIn[i], end = thickIn[i+1]).
    for (var si = 0; si < segs.length; si++) {
      var seg = segs[si];
      var steps = Math.max(2, Math.ceil(seg.len / 2.5));
      var t0 = thickIn[si];
      var t1 = thickIn[si + 1] != null ? thickIn[si + 1] : t0;
      for (var k = 0; k < steps; k++) {
        var t = k / steps;
        // Cubic Bézier eval (de Casteljau).
        var u = 1 - t;
        var x = u*u*u*seg.p0.x + 3*u*u*t*seg.c1.x + 3*u*t*t*seg.c2.x + t*t*t*seg.p1.x;
        var y = u*u*u*seg.p0.y + 3*u*u*t*seg.c1.y + 3*u*t*t*seg.c2.y + t*t*t*seg.p1.y;
        var w = base * (t0 * (1 - t) + t1 * t);
        dense.push({ x: x, y: y, w: Math.max(MIN_THICKNESS, w) });
      }
    }
    // Always include the very last anchor so the tail doesn't get cut.
    var lastSeg = segs[segs.length - 1];
    dense.push({
      x: lastSeg.p1.x, y: lastSeg.p1.y,
      w: Math.max(MIN_THICKNESS, base * thickIn[thickIn.length - 1]),
    });

    // ── Draw the ribbon as a filled polygon by walking left & right offsets.
    // For each pair of consecutive samples, compute their perpendicular
    // offsets ± w/2 and stitch them into a quad. Building one big filled
    // path is much faster than thousands of stroke() calls.
    ctx.beginPath();
    var leftPts = [];
    var rightPts = [];
    for (var i = 0; i < dense.length; i++) {
      var a = dense[i];
      var b = dense[Math.min(i + 1, dense.length - 1)];
      var dx = b.x - a.x;
      var dy = b.y - a.y;
      var len = Math.hypot(dx, dy) || 1;
      var nx = -dy / len;
      var ny =  dx / len;
      var half = a.w / 2;
      leftPts.push ({ x: a.x + nx * half, y: a.y + ny * half });
      rightPts.push({ x: a.x - nx * half, y: a.y - ny * half });
    }
    // Forward along the LEFT edge, then back along the RIGHT (reverse).
    ctx.moveTo(leftPts[0].x, leftPts[0].y);
    for (var L = 1; L < leftPts.length; L++) ctx.lineTo(leftPts[L].x, leftPts[L].y);
    for (var R = rightPts.length - 1; R >= 0; R--) ctx.lineTo(rightPts[R].x, rightPts[R].y);
    ctx.closePath();
    ctx.fill();

    // Optional: a thin, soft stroke along the ribbon centerline gives the
    // antialiased edges an extra crispness. Cheap, big visual win.
    ctx.beginPath();
    ctx.moveTo(dense[0].x, dense[0].y);
    for (var d = 1; d < dense.length; d++) ctx.lineTo(dense[d].x, dense[d].y);
    ctx.lineWidth = Math.max(0.25, base * 0.18);
    ctx.globalAlpha = 0.55;
    ctx.stroke();

    ctx.restore();
  }

  root.FormylaPen = {
    drawSmoothStroke: drawSmoothStroke,
    smoothPath: smoothPath,
    thicknessProfile: thicknessProfile,
    pointSpeeds: pointSpeeds,
    normalize01: normalize01,
    MIN_THICKNESS: MIN_THICKNESS,
    MAX_THICKNESS_MULT: MAX_THICKNESS_MULT,
  };
})(typeof window !== "undefined" ? window : globalThis);
