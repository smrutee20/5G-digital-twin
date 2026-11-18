/* SetuCity: network effects.
   Each effect is a named group of glowing shapes (radio waves, beams, fibre, packets, coverage) that a
   lesson step or an Explore layer switches on. Effects are built the first time they are shown. */
(function () {
  "use strict";
  const T = THREE, SC = window.SC, W = SC.W, V = W.V, lerp = W.lerp;
  const defs = {}, live = {};
  const def = (W.defineFx = (name, build) => (defs[name] = build));
  W.setFx = function (names) {
    names = names || [];
    for (const n in defs) {
      const on = names.indexOf(n) >= 0;
      if (on && !live[n]) { const g = new T.Group(); W.scene.add(g); live[n] = { g, upd: defs[n](g) || null }; }
      if (live[n]) live[n].g.visible = on;
    }
  };
  W.fxNames = () => Object.keys(defs);

  const C = { cyan: "#37d5ff", amber: "#ffb224", green: "#3ddc97", violet: "#a78bfa", pink: "#ff6b9a", red: "#ff5a5f", cream: "#fff1b8", white: "#ffffff", lime: "#b6f04a" };
  const bm = (color, op) => new T.MeshBasicMaterial({ color, transparent: true, opacity: op === undefined ? 1 : op, depthWrite: false, toneMapped: false, side: T.DoubleSide });
  const P = (name) => W.places[name].clone();
  const snap = (v) => Math.max(-150, Math.min(150, Math.round((v + 150) / 60) * 60 - 150));

  /* ---------- drawing helpers */
  function seg(g, a, b, color, th, op) {
    const m = new T.Mesh(new T.BoxGeometry(th, th, Math.max(0.01, a.distanceTo(b))), bm(color, op === undefined ? 0.95 : op));
    m.position.copy(a).lerp(b, 0.5); m.lookAt(b); g.add(m);
    return m;
  }
  function poly(g, pts, color, th, op) { for (let i = 0; i < pts.length - 1; i++) seg(g, pts[i], pts[i + 1], color, th, op); return pts; }
  function arc(a, b, lift, n) {
    const mid = a.clone().lerp(b, 0.5); mid.y = Math.max(a.y, b.y) + lift;
    return new T.QuadraticBezierCurve3(a, mid, b).getPoints(n || 28);
  }
  function tube(g, pts, color, r, op) {
    const m = new T.Mesh(new T.TubeGeometry(new T.CatmullRomCurve3(pts), pts.length * 2, r, 6), bm(color, op === undefined ? 0.5 : op));
    g.add(m); return m;
  }
  function resample(pts, S) {
    const cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
    const total = cum[cum.length - 1], out = [];
    let j = 0;
    for (let s = 0; s <= S; s++) {
      const d = (s / S) * total;
      while (j < pts.length - 2 && cum[j + 1] < d) j++;
      const span = cum[j + 1] - cum[j] || 1;
      out.push(pts[j].clone().lerp(pts[j + 1], (d - cum[j]) / span));
    }
    out.total = total;
    return out;
  }
  const dot = new T.SphereGeometry(1, 8, 6), tmp = new T.Object3D();
  /* n packets travelling along pts at `speed` metres a second (negative = the other way) */
  function flow(g, pts, color, n, speed, size) {
    const S = 140, Q = resample(pts, S), im = new T.InstancedMesh(dot, bm(color, 1), n);
    im.frustumCulled = false; g.add(im);
    return (t) => {
      for (let i = 0; i < n; i++) {
        let k = ((t * speed) / Q.total + i / n) % 1; if (k < 0) k += 1;
        const f = k * S, a = Math.floor(f);
        tmp.position.lerpVectors(Q[a], Q[Math.min(S, a + 1)], f - a);
        tmp.scale.setScalar(size * (0.75 + 0.25 * Math.sin(k * Math.PI)));
        tmp.updateMatrix(); im.setMatrixAt(i, tmp.matrix);
      }
      im.instanceMatrix.needsUpdate = true;
    };
  }
  const ringGeo = new T.RingGeometry(0.94, 1, 56);
  function rings(g, pos, color, maxR, n, period) {
    const ms = [];
    for (let i = 0; i < n; i++) { const m = new T.Mesh(ringGeo, bm(color, 0.8)); m.rotation.x = -Math.PI / 2; m.position.copy(pos); g.add(m); ms.push(m); }
    return (t) => ms.forEach((m, i) => { const k = (t / period + i / n) % 1; m.scale.setScalar(0.01 + k * maxR); m.material.opacity = (1 - k) * 0.85; });
  }
  function disc(g, x, y, z, r, color, op, start, len) {
    const m = new T.Mesh(new T.CircleGeometry(r, 48, start || 0, len === undefined ? Math.PI * 2 : len), bm(color, op));
    m.rotation.x = -Math.PI / 2; m.position.set(x, y, z); g.add(m); return m;
  }
  function dome(g, pos, r, color, op) {
    const m = new T.Mesh(new T.SphereGeometry(r, 28, 12, 0, Math.PI * 2, 0, Math.PI / 2), bm(color, op === undefined ? 0.16 : op));
    m.position.set(pos.x, 0.3, pos.z); g.add(m);
    const e = new T.Mesh(new T.RingGeometry(r * 0.985, r, 64), bm(color, 0.7)); e.rotation.x = -Math.PI / 2; e.position.set(pos.x, 0.9, pos.z); g.add(e);
    return m;
  }
  const beamGeo = new T.CylinderGeometry(1, 0.03, 1, 16, 1, true).translate(0, 0.5, 0).rotateX(Math.PI / 2);
  function beam(g, color, op) {
    const m = new T.Mesh(beamGeo, bm(color, op === undefined ? 0.3 : op)); g.add(m);
    m.set = (a, b, w) => { m.position.copy(a); m.lookAt(b); m.scale.set(w, w, a.distanceTo(b)); };
    return m;
  }
  /* a straight link whose ends can move every frame */
  function dyn(g, color, th, op) {
    const m = new T.Mesh(new T.BoxGeometry(th, th, 1), bm(color, op === undefined ? 0.9 : op)); g.add(m);
    m.set = (a, b) => { m.position.copy(a).lerp(b, 0.5); m.lookAt(b); m.scale.z = Math.max(0.01, a.distanceTo(b)); };
    return m;
  }
  function tag(g, text, color, pos, scale) { const s = W.label(text, color, scale || 1, g); s.position.copy(pos); return s; }
  function route(a, b, y) {
    y = y === undefined ? 0.7 : y;
    const rx = snap(a.x), rz = snap(b.z), raw = [V(a.x, y, a.z), V(rx, y, a.z), V(rx, y, rz), V(b.x, y, rz), V(b.x, y, b.z)];
    return raw.filter((p, i) => i === 0 || p.distanceTo(raw[i - 1]) > 0.5);
  }
  const wp = new T.Vector3();
  const world = (o, dy) => { o.getWorldPosition(wp); return V(wp.x, wp.y + (dy || 0), wp.z); };
  const all = (fns) => (t, dt) => { for (const f of fns) f(t, dt); };
  const siteToCore = (t, y) => [t.pos.clone(), V(t.base.x, y === undefined ? 0.7 : y, t.base.z)].concat(route(t.base, W.places.coreGate, y).slice(1));

  W.initFx = function () {
    W.place("internet", -70, 46, 318);
    W.place("cloudfar", -268, 70, -30);
    W.objs = { avCar: W.avCar, hoCar: W.hoCar, drone: W.drone, sat: W.sat, harvester: W.harvester, agv: W.agv, ship: W.ship };
    W.updaters.push((t, dt) => { for (const n in live) if (live[n].g.visible && live[n].upd) live[n].upd(t, dt); });
  };

  /* ================================================================= radio */
  def("waves", (g) => all(W.towers.map((t) => rings(g, t.pos, C.cyan, t.r * 0.42, 3, 3.2))));

  def("cells", (g) => {
    const pal = [["#37d5ff", "#5ee0ff", "#1fb6e6"], ["#ffb224", "#ffc95c", "#f59e0b"], ["#3ddc97", "#6ee7b0", "#22c583"], ["#a78bfa", "#c4b0ff", "#8b6cf0"], ["#ff6b9a", "#ff93b5", "#f04f84"]];
    W.towers.forEach((t, i) => {
      const r = t.r * 0.62;
      for (let k = 0; k < 3; k++) disc(g, t.pos.x, 0.9 + i * 0.05, t.pos.z, r, pal[i % 5][k], 0.2, (k * 2 * Math.PI) / 3 + 0.5, (2 * Math.PI) / 3 - 0.05);
      const e = new T.Mesh(new T.RingGeometry(r * 0.99, r, 72), bm(pal[i % 5][0], 0.85)); e.rotation.x = -Math.PI / 2; e.position.set(t.pos.x, 1.3, t.pos.z); g.add(e);
      tag(g, "Cell site " + (i + 1), pal[i % 5][0], V(t.pos.x, t.pos.y + 9, t.pos.z), 1.5);
    });
  });

  def("spectrum", (g) => {
    const c = P("rooftop");
    [[235, C.pink, 0.1, "Low band · 700 MHz · reaches furthest"], [125, C.amber, 0.15, "Mid band · 3.5 GHz · the 5G workhorse"], [42, C.cyan, 0.3, "High band · 26 GHz mmWave · huge capacity, short reach"]].forEach((b, i) => {
      disc(g, c.x, 1 + i * 0.25, c.z, b[0], b[1], b[2]);
      const e = new T.Mesh(new T.RingGeometry(b[0] * 0.992, b[0], 96), bm(b[1], 0.9)); e.rotation.x = -Math.PI / 2; e.position.set(c.x, 1.6 + i * 0.25, c.z); g.add(e);
      tag(g, b[3], b[1], V(c.x + b[0] * 0.3, 14 + i * 16, c.z + b[0] * 0.82), 1.7 - i * 0.25);
    });
    return rings(g, c, C.white, 60, 3, 2.6);
  });

  def("uplink", (g) => {
    const u = P("parkUser"), s = P("rooftop"), b = beam(g, C.cyan, 0.2);
    b.set(s, u, 5);
    const up = arc(u, s, 10), down = arc(s.clone().add(V(0.8, 0, 0.8)), u.clone().add(V(0.8, 0, 0.8)), 4);
    return all([flow(g, up, C.amber, 7, 26, 0.55), flow(g, down, C.cyan, 9, 30, 0.55), rings(g, V(u.x, 0.9, u.z), C.amber, 6, 2, 1.8)]);
  });

  def("beams", (g) => {
    const s = P("rooftop"), cols = [C.cyan, C.amber, C.green, C.violet, C.pink, C.lime];
    const bs = (W.ringC || []).map((c, i) => ({ b: beam(g, cols[i % 6], 0.3), c }));
    const st = beam(g, C.white, 0.25); st.set(s, P("parkUser"), 2.4);
    return () => bs.forEach((o) => o.b.set(s, V(o.c.position.x, 1.5, o.c.position.z), 2.6));
  });

  def("smallcells", (g) => {
    const fns = [];
    W.smallCells.forEach((p, i) => {
      disc(g, p.x, 0.95, p.z, 21, C.green, 0.3);
      const e = new T.Mesh(new T.RingGeometry(20.6, 21, 64), bm(C.green, 0.9)); e.rotation.x = -Math.PI / 2; e.position.set(p.x, 1, p.z); g.add(e);
      fns.push(rings(g, p, C.green, 12, 2, 2.2));
    });
    return all(fns);
  });

  def("handover", (g) => {
    const car = W.hoCar, link = dyn(g, C.amber, 0.5), nb = dyn(g, C.white, 0.22, 0.4), top = V(0, 0, 0);
    const pal = [C.cyan, C.amber, C.green, C.violet, C.pink];
    W.towers.forEach((t, i) => { tag(g, "Cell " + (i + 1), pal[i % 5], V(t.pos.x, t.pos.y + 9, t.pos.z), 1.5); disc(g, t.pos.x, 0.9 + i * 0.05, t.pos.z, t.r * 0.62, pal[i % 5], 0.1); });
    let serving = -1;
    const r = rings(g, V(0, 0, 0), C.white, 9, 2, 1.2), holder = g.children.slice(-2);
    return (t) => {
      top.set(car.position.x, 3.4, car.position.z);
      const d = W.towers.map((tw) => tw.pos.distanceTo(top) / tw.r);
      let best = 0; d.forEach((v, i) => { if (v < d[best]) best = i; });
      /* hysteresis: only switch when the new cell is clearly better, exactly like a real A3 handover trigger */
      if (serving < 0 || d[best] < d[serving] * 0.9) serving = best;
      let second = serving === 0 ? 1 : 0; d.forEach((v, i) => { if (i !== serving && v < d[second]) second = i; });
      link.material.color.set(pal[serving % 5]); link.set(top, W.towers[serving].pos); nb.set(top, W.towers[second].pos);
      holder.forEach((m) => m.position.set(top.x, 1, top.z)); r(t);
    };
  });

  /* signal-strength heat map: every hexagon is a location, coloured by the best signal it can hear */
  def("heat", (g) => {
    const sites = W.towers.map((t) => ({ p: t.pos, pw: t.name === "hilltower" ? 6 : 0 })).concat(W.smallCells.map((p) => ({ p, pw: -22 })));
    const R = 4.3, dx = 1.5 * R, dz = Math.sqrt(3) * R, items = [], F = W.footprints;
    const blocked = (s, x, z) => {
      for (const f of F) {
        const x0 = f.x - f.w / 2, x1 = f.x + f.w / 2, z0 = f.z - f.d / 2, z1 = f.z + f.d / 2, ddx = x - s.x, ddz = z - s.z;
        let t0 = 0, t1 = 1;
        if (Math.abs(ddx) < 1e-6) { if (s.x < x0 || s.x > x1) continue; } else { let a = (x0 - s.x) / ddx, b = (x1 - s.x) / ddx; if (a > b) { const q = a; a = b; b = q; } t0 = Math.max(t0, a); t1 = Math.min(t1, b); }
        if (Math.abs(ddz) < 1e-6) { if (s.z < z0 || s.z > z1) continue; } else { let a = (z0 - s.z) / ddz, b = (z1 - s.z) / ddz; if (a > b) { const q = a; a = b; b = q; } t0 = Math.max(t0, a); t1 = Math.min(t1, b); }
        if (t0 < t1 && lerp(s.y, 1.5, (t0 + t1) / 2) < f.h) return true;
      }
      return false;
    };
    let col = 0;
    for (let x = -158; x <= 158; x += dx, col++) for (let z = -158 + (col % 2 ? dz / 2 : 0); z <= 158; z += dz) {
      if (F.some((f) => Math.abs(x - f.x) < f.w / 2 + 1.5 && Math.abs(z - f.z) < f.d / 2 + 1.5)) continue;
      let best = -200;
      for (const s of sites) { const d = Math.hypot(x - s.p.x, z - s.p.z, s.p.y); const v = s.pw - 32 * Math.log10(d) - (blocked(s.p, x, z) ? 22 : 0); if (v > best) best = v; }
      const q = best > -60 ? 0 : best > -66 ? 1 : best > -72 ? 2 : best > -79 ? 3 : 4;
      items.push([x, z, q]);
    }
    const im = new T.InstancedMesh(new T.CylinderGeometry(R * 0.93, R * 0.93, 0.3, 6), bm("#ffffff", 0.82), items.length), c = new T.Color();
    const pal = ["#22c55e", "#a3e635", "#facc15", "#fb923c", "#ef4444"];
    items.forEach((it, i) => { tmp.position.set(it[0], 1, it[1]); tmp.scale.setScalar(1 - it[2] * 0.07); tmp.rotation.set(0, Math.PI / 6, 0); tmp.updateMatrix(); im.setMatrixAt(i, tmp.matrix); im.setColorAt(i, c.set(pal[it[2]])); });
    tmp.rotation.set(0, 0, 0);
    g.add(im);
    return all(W.smallCells.map((p) => rings(g, p, C.white, 9, 2, 2)));
  });

  /* ================================================================= transport */
  def("backhaul", (g) => {
    const fns = [];
    W.towers.forEach((t) => {
      const pts = poly(g, siteToCore(t), C.cream, 0.55);
      fns.push(flow(g, pts, C.amber, Math.ceil(resample(pts, 4).total / 26), 34, 0.8), flow(g, pts, C.cyan, Math.ceil(resample(pts, 4).total / 34), -40, 0.7));
    });
    W.smallCells.forEach((p) => poly(g, [p.clone(), V(p.x, 0.7, p.z)].concat(route(p, W.places.coreGate).slice(1)), C.cream, 0.22, 0.6));
    return all(fns);
  });

  /* the whole duct network, meant to be seen with the city ghosted (X-ray view) */
  def("fibre", (g) => {
    for (let i = 0; i < 6; i++) { const p = -150 + 60 * i; seg(g, V(p, 0.6, -156), V(p, 0.6, 156), C.cream, 0.3, 0.8); seg(g, V(-156, 0.6, p), V(156, 0.6, p), C.cream, 0.3, 0.8); for (let j = 0; j < 6; j++) disc(g, p, 0.75, -150 + 60 * j, 1.5, C.white, 0.9); }
    for (const f of W.footprints) {
      if (f.h < 18) continue;
      const x = f.x + f.w / 2, z = f.z + f.d / 2, rx = snap(x);
      poly(g, [V(rx, 0.6, z), V(x, 0.6, z), V(x, f.h + 0.6, z), V(f.x, f.h + 0.6, f.z)], C.cream, 0.22, 0.75);
    }
    const fns = [];
    W.towers.forEach((t) => { const pts = poly(g, siteToCore(t, 0.6), C.amber, 0.5); fns.push(flow(g, pts, C.white, Math.ceil(resample(pts, 4).total / 30), 38, 0.8)); });
    const sea = poly(g, [P("manhole"), V(-130, 0.6, 126), V(-130, 0.6, 196), V(-130, -1, 340)], C.cyan, 0.6);
    fns.push(flow(g, sea, C.white, 8, 40, 0.9));
    return all(fns);
  });

  def("internet", (g) => {
    const gate = P("coreGate"), mh = P("manhole"), net = P("internet");
    const land = poly(g, route(gate, V(-130, 0, 126)).concat([V(-130, 0.7, 196)]), C.cream, 0.6);
    const sea = arc(V(-130, 0.7, 196), net, 14, 40); tube(g, sea, C.cyan, 0.5, 0.7);
    const globe = new T.Mesh(new T.IcosahedronGeometry(22, 2), new T.MeshBasicMaterial({ color: C.cyan, wireframe: true, transparent: true, opacity: 0.55, toneMapped: false })); globe.position.copy(net); g.add(globe);
    const inner = new T.Mesh(new T.IcosahedronGeometry(15, 1), bm("#1b3a6b", 0.6)); inner.position.copy(net); g.add(inner);
    tag(g, "THE INTERNET", C.cyan, V(net.x, net.y + 30, net.z), 2.6);
    tag(g, "Submarine cable", C.cyan, V(-124, 14, 226), 1.4); tag(g, "Cable landing station", C.cream, V(mh.x, 16, mh.z), 1.4);
    const srv = [0, 1, 2, 3, 4].map((i) => { const m = new T.Mesh(new T.BoxGeometry(3, 5, 3), bm([C.amber, C.green, C.pink, C.violet, C.white][i], 0.9)); g.add(m); return m; });
    const path = land.concat(sea.slice(1));
    const f1 = flow(g, path, C.amber, 16, 46, 0.95), f2 = flow(g, path, C.white, 12, -52, 0.8);
    return (t) => { globe.rotation.y = t * 0.15; srv.forEach((m, i) => { const a = t * 0.3 + i * 1.256; m.position.set(net.x + Math.cos(a) * 30, net.y + Math.sin(a * 2 + i) * 6, net.z + Math.sin(a) * 30); }); f1(t); f2(t); };
  });

  /* ================================================================= core network, drawn as a hologram over the data centre */
  def("core", (g) => {
    const o = P("core"), z = o.z + 2;
    const N = {
      NSSF: [-24, 44, "cp"], AUSF: [-12, 44, "cp"], UDM: [0, 44, "cp"], PCF: [12, 44, "cp"], NRF: [24, 44, "cp"],
      AMF: [-14, 26, "cp"], SMF: [6, 26, "cp"], UPF: [6, 13, "up"], gNB: [-36, 13, "ran"], DN: [30, 13, "dn"],
    };
    const name = { gNB: "gNB · radio site", DN: "Internet", UPF: "UPF · user plane", AMF: "AMF · mobility", SMF: "SMF · sessions", UDM: "UDM · subscribers", AUSF: "AUSF · auth", PCF: "PCF · policy", NRF: "NRF · registry", NSSF: "NSSF · slices" };
    const col = { cp: C.cyan, up: C.amber, ran: C.green, dn: C.violet }, at = (k, dy) => V(o.x + N[k][0], N[k][1] + (dy || 0), z);
    const cubes = [];
    for (const k in N) {
      const m = new T.Mesh(new T.BoxGeometry(5.4, 5.4, 5.4), bm(col[N[k][2]], 0.82)); m.position.copy(at(k)); g.add(m); cubes.push(m);
      const e = new T.LineSegments(new T.EdgesGeometry(m.geometry), new T.LineBasicMaterial({ color: "#ffffff", toneMapped: false })); m.add(e);
      tag(g, name[k], col[N[k][2]], at(k, 4.6), 0.42);
    }
    seg(g, V(o.x - 30, 35, z), V(o.x + 30, 35, z), C.cyan, 0.5);
    tag(g, "Service-based interface", C.cyan, V(o.x + 41, 35, z), 0.5);
    for (const k of ["NSSF", "AUSF", "UDM", "PCF", "NRF"]) seg(g, at(k, -2.7), V(o.x + N[k][0], 35, z), C.cyan, 0.3);
    for (const k of ["AMF", "SMF"]) seg(g, at(k, 2.7), V(o.x + N[k][0], 35, z), C.cyan, 0.3);
    const n2 = [at("gNB"), V(o.x - 36, 26, z), at("AMF")], n3 = [at("gNB"), at("UPF"), at("DN")];
    poly(g, n2, C.green, 0.35); poly(g, n3, C.amber, 0.5); seg(g, at("SMF", -2.7), at("UPF", 2.7), C.white, 0.3);
    tag(g, "N2", C.green, V(o.x - 27, 28.4, z), 0.4); tag(g, "N3", C.amber, V(o.x - 15, 15.4, z), 0.4); tag(g, "N4", C.white, V(o.x + 9.6, 19.6, z), 0.4); tag(g, "N6", C.amber, V(o.x + 18, 15.4, z), 0.4);
    const f = [flow(g, n3, C.amber, 9, 16, 0.75), flow(g, n3, C.white, 6, -19, 0.6), flow(g, n2, C.green, 4, 12, 0.6)];
    return (t) => { cubes.forEach((m, i) => (m.rotation.y = Math.sin(t * 0.6 + i) * 0.25)); f.forEach((x) => x(t)); };
  });

  def("coreFlow", (g) => {
    const o = P("core"), y = SC.W.places["core.trays"].y - 0.9, fns = [];
    for (let r = 0; r < 7; r++) { const x = o.x - 14.4 + r * 4.8; const pts = poly(g, [V(x, y, o.z + 12), V(x, y, o.z - 12.6), V(o.x + 18, y, o.z - 12.6)], C.cream, 0.28); fns.push(flow(g, pts, r % 2 ? C.cyan : C.amber, 5, r % 2 ? 9 : -9, 0.38)); }
    tag(g, "Control plane · AMF, SMF, UDM", C.cyan, V(o.x - 9, 11, o.z - 6), 0.3); tag(g, "User plane · UPF", C.amber, V(o.x + 9.6, 11, o.z + 2), 0.3); tag(g, "Operations room", C.white, P("core.control").add(V(0, 4, 0)), 0.26);
    return all(fns);
  });

  def("slices", (g) => {
    const t = W.towers.find((x) => x.name === "rooftop"), fns = [];
    [[C.violet, "Slice 1 · eMBB · fast broadband", 12, 30, 0.95], [C.amber, "Slice 2 · URLLC · instant control", 5, 70, 0.6], [C.green, "Slice 3 · mMTC · millions of sensors", 26, 18, 0.38]].forEach((s, i) => {
      const y = 1 + i * 2.4, pts = siteToCore(t, y).map((p, k) => (k === 0 ? p.clone().add(V(i - 1, 0, 0)) : p));
      poly(g, pts, s[0], 0.75, 0.75);
      fns.push(flow(g, pts, C.white, s[2], s[3], s[4]));
      tag(g, s[1], s[0], V(-30, 12 + i * 8, -90 - i * 0.01), 1.25);
    });
    return all(fns);
  });

  /* ================================================================= services */
  def("call", (g) => {
    const a = P("parkUser"), b = P("homeUser"), s1 = W.towers.find((x) => x.name === "rooftop"), s2 = W.towers.find((x) => x.name === "southtower"), core = P("core").add(V(0, 20, 0));
    const up = arc(a, s1.pos, 8), down = arc(s2.pos, b, 6);
    const l1 = siteToCore(s1), l2 = siteToCore(s2), gate = P("coreGate");
    const path = up.concat(l1.slice(1), [core], l2.slice().reverse().slice(0, -1), down);
    tube(g, up, C.pink, 0.35, 0.7); tube(g, down, C.pink, 0.35, 0.7); poly(g, l1, C.pink, 0.5, 0.8); poly(g, l2, C.pink, 0.5, 0.8); seg(g, gate, core, C.pink, 0.5, 0.8);
    const cube = new T.Mesh(new T.BoxGeometry(7, 7, 7), bm(C.pink, 0.8)); cube.position.copy(core); g.add(cube);
    tag(g, "IMS · sets up the call", C.pink, core.clone().add(V(0, 8, 0)), 1.5);
    tag(g, "Caller", C.amber, a.clone().add(V(0, 6, 0)), 1); tag(g, "Called", C.amber, b.clone().add(V(0, 9, 0)), 1);
    const f1 = flow(g, path, C.white, 22, 60, 0.75), f2 = flow(g, path, C.amber, 18, -60, 0.65);
    const r1 = rings(g, V(a.x, 1, a.z), C.pink, 7, 2, 1.4), r2 = rings(g, V(b.x, 9.5, b.z), C.pink, 9, 2, 1.4);
    return (t) => { cube.rotation.y = t * 0.5; f1(t); f2(t); r1(t); r2(t); };
  });

  def("v2x", (g) => {
    const cars = W.ringB || [], pool = [], rs = W.smallCells;
    for (let i = 0; i < 26; i++) pool.push(dyn(g, i < 14 ? C.cyan : C.lime, 0.28, 0.9));
    const a = V(0, 0, 0), b = V(0, 0, 0), holder = [], r = rings(g, V(0, 0, 0), C.cyan, 16, 3, 1.6);
    g.children.slice(-3).forEach((m) => holder.push(m));
    return (t) => {
      let n = 0;
      const use = (p, q) => { if (n < pool.length) { pool[n].visible = true; pool[n].set(p, q); n++; } };
      for (let i = 0; i < cars.length; i++) {
        a.set(cars[i].position.x, 2.8, cars[i].position.z);
        for (let j = i + 1; j < cars.length; j++) { b.set(cars[j].position.x, 2.8, cars[j].position.z); if (a.distanceTo(b) < 78) use(a.clone(), b.clone()); }
        let near = null, nd = 70; for (const s of rs) { const d = s.distanceTo(a); if (d < nd) { nd = d; near = s; } }
        if (near) use(a.clone(), near);
      }
      for (let k = n; k < pool.length; k++) pool[k].visible = false;
      const av = W.avCar.position; holder.forEach((m) => m.position.set(av.x, 1, av.z)); r(t);
    };
  });

  def("iot", (g) => {
    const src = W.sensors.concat(W.smallCells);
    for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) if (j >= 3 || i === 0) src.push(V(-120 + 60 * i + 22.6, 7.3, -120 + 60 * j - 22.6));
    for (let k = 0; k < 14; k++) src.push(V(168 + (k % 3) * 12, 3, 86 + Math.floor(k / 3) * 14));
    const links = src.map((s) => { let best = W.towers[0]; for (const t of W.towers) if (t.pos.distanceTo(s) < best.pos.distanceTo(s)) best = t; return [s, best.pos]; });
    const im = new T.InstancedMesh(dot, bm(C.green, 1), links.length); im.frustumCulled = false; g.add(im);
    const fns = src.slice(0, 14).map((s) => rings(g, V(s.x, s.y, s.z), C.green, 4, 1, 2.4));
    return (t) => {
      links.forEach((l, i) => { const k = (t * 0.22 + i * 0.137) % 1; tmp.position.lerpVectors(l[0], l[1], k); tmp.position.y += Math.sin(k * Math.PI) * 14; tmp.scale.setScalar(k < 0.9 ? 0.75 : 0.01); tmp.updateMatrix(); im.setMatrixAt(i, tmp.matrix); });
      im.instanceMatrix.needsUpdate = true; fns.forEach((f) => f(t));
    };
  });

  def("private", (g) => {
    const m = W.portMast, c = V(-180, 0, 80);
    dome(g, c, 82, C.violet, 0.13);
    tag(g, "Private 5G · this site only", C.violet, V(c.x, 60, c.z), 1.1);
    seg(g, m, V(m.x, 0.8, m.z), C.cream, 0.3); seg(g, V(m.x, 0.8, m.z), P("port.core").setY(0.8), C.cream, 0.3);
    const ls = W.cranes.map(() => dyn(g, C.violet, 0.3, 0.9)), sh = dyn(g, C.cyan, 0.3, 0.8), r = rings(g, m, C.violet, 46, 3, 2.6);
    return (t) => { W.cranes.forEach((cr, i) => ls[i].set(m, world(cr))); sh.set(m, world(W.ship, 17)); r(t); };
  });

  def("factoryNet", (g) => {
    const r0 = P("factory.radio"), f = P("factory"), fns = [rings(g, r0, C.cyan, 16, 3, 1.8)];
    for (let i = 0; i < 5; i++) seg(g, r0, V(f.x - 13 + i * 6.5, 4.6, f.z - 0.8), C.cyan, 0.12, 0.85);
    const agv = dyn(g, C.amber, 0.14);
    fns.push(() => agv.set(r0, world(W.agv, 1.4)));
    return all(fns);
  });

  def("edge", (g) => {
    const f = P("factory").setY(11), e = P("edge"), far = P("cloudfar");
    const near = arc(f, e, 12), long = arc(f, far, 40, 40);
    tube(g, near, C.green, 0.4, 0.75); tube(g, long, C.red, 0.4, 0.55);
    tag(g, "Edge node · about 5 ms away", C.green, e.clone().add(V(0, 7, 0)), 1.3); tag(g, "Distant cloud region · 40 ms or more", C.red, far.clone().add(V(0, 16, 0)), 2.2);
    const cl = new T.Mesh(new T.IcosahedronGeometry(12, 1), bm("#ffffff", 0.85)); cl.position.copy(far); cl.scale.y = 0.6; g.add(cl);
    dome(g, e, 9, C.green, 0.2);
    return all([flow(g, near, C.white, 6, 60, 0.6), flow(g, near, C.green, 6, -60, 0.6), flow(g, long, C.white, 6, 34, 0.9), flow(g, long, C.red, 6, -34, 0.9)]);
  });

  def("stadium", (g) => {
    const c = P("stadium"), cols = [C.cyan, C.amber, C.pink, C.lime];
    dome(g, c, 31, C.cyan, 0.1);
    W.stadiumMasts.forEach((m, i) => { for (let k = 0; k < 5; k++) { const a = (i * Math.PI) / 2 + k * 0.5 + 0.6, r = 12 + k * 1.4; beam(g, cols[i], 0.3).set(m, V(c.x + Math.cos(a) * r * 1.28, 0.4 + 1.8 + k, c.z + Math.sin(a) * r), 1.8); } });
    tag(g, "60,000 phones, one small space", C.cyan, V(c.x, 30, c.z), 1.4);
    return all(W.stadiumMasts.map((m) => rings(g, m, C.white, 10, 2, 1.6)));
  });

  def("drone", (g) => {
    const s = P("rooftop"), l = dyn(g, C.green, 0.3), cone = beam(g, C.green, 0.22), r = rings(g, V(0, 0, 0), C.green, 14, 2, 1.8), hold = g.children.slice(-2);
    return (t) => { const p = W.drone.position; l.set(s, p); cone.set(p, V(p.x, 0.5, p.z), 13); hold.forEach((m) => m.position.set(p.x, 1, p.z)); r(t); };
  });

  def("satellite", (g) => {
    const gs = W.groundStation, farm = V(180, 1, -70), b1 = beam(g, C.violet, 0.2), b2 = beam(g, C.cyan, 0.18), feeder = dyn(g, C.amber, 0.5);
    disc(g, farm.x, 1.2, farm.z, 34, C.violet, 0.2); tag(g, "Satellite spot beam", C.violet, V(farm.x, 20, farm.z), 1.5); tag(g, "Gateway · feeder link", C.amber, gs.clone().add(V(0, 14, 0)), 1.5);
    return (t) => { const s = W.sat.position; b1.set(s, farm, 34); b2.set(s, world(W.ship, 14), 26); feeder.set(gs, s); };
  });

  def("fwa", (g) => {
    const t = W.towers.find((x) => x.name === "southtower").pos, cpe = P("home.cpe"), rt = P("home.router");
    beam(g, C.cyan, 0.22).set(t, cpe, 1.6);
    const a = arc(t, cpe, 3); poly(g, [cpe, V(cpe.x, rt.y, cpe.z), rt], C.cream, 0.14);
    return all([flow(g, a, C.white, 12, 40, 0.3), rings(g, rt, C.green, 7, 3, 1.6)]);
  });

  def("ward", (g) => {
    const cell = P("ward.cell"), th = P("ward.theatre"), con = P("ward.console"), beds = P("ward.beds"), far = P("rooftop");
    seg(g, cell, th, C.cyan, 0.12); seg(g, cell, con, C.cyan, 0.12);
    for (let i = 0; i < 4; i++) seg(g, cell, V(beds.x - 5 + i * 4.2, beds.y - 0.2, beds.z + 1.4), C.green, 0.08, 0.8);
    const out = arc(cell.clone().add(V(0, 0.8, 0)), far, 12);
    tube(g, out, C.amber, 0.25, 0.7);
    tag(g, "Remote surgeon's link · under 10 ms", C.amber, cell.clone().add(V(-10, 9, -5)), 0.4);
    return all([flow(g, out, C.white, 10, 50, 0.4), flow(g, out, C.amber, 8, -50, 0.4), rings(g, cell, C.cyan, 9, 3, 1.6)]);
  });

  def("office", (g) => {
    const cell = P("office.cell"), o = P("office");
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) if (!(r === 1 && c === 1)) seg(g, cell, V(o.x - 7.5 + c * 7, o.y + 0.5, o.z - 6 + r * 6), C.cyan, 0.07, 0.75);
    const up = [cell.clone(), V(o.x + 11.5, cell.y, o.z - 10.5), V(o.x + 11.5, 0.8, o.z - 10.5)]; poly(g, up, C.cream, 0.16);
    return all([rings(g, cell, C.cyan, 13, 3, 1.8), flow(g, up, C.amber, 6, 14, 0.3)]);
  });

  def("farm", (g) => {
    const t = W.towers.find((x) => x.name === "easttower").pos, l = dyn(g, C.amber, 0.3), fns = [];
    W.sensors.forEach((s) => { seg(g, s, t, C.green, 0.08, 0.45); fns.push(rings(g, s, C.green, 5, 1, 2.2)); });
    fns.push(() => l.set(t, world(W.harvester, 6)));
    return all(fns);
  });
})();
