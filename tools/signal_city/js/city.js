/* SetuCity: the city itself.
   Everything is generated here from simple shapes: island, roads, districts, landmark buildings with
   interiors you can open (cutaways), cell sites, traffic, people, a drone, a satellite.
   Layout: 5 x 5 blocks, 48 m each, separated by 12 m roads. Block (i, j) is centred on (-120 + 60 i, -120 + 60 j);
   i runs west to east, j runs north to south. */
(function () {
  "use strict";
  const T = THREE, SC = window.SC, W = SC.W;
  const { M, box, cyl, ball, mesh, group, place, rnd, rr, pick, V, lerp } = W;
  const SLAB = 0.4, LANE = 2.8;
  const PAL = {
    towers: ["#e8edf2", "#cfd8e3", "#f2e9dc", "#d9c7b8", "#b9c7d6", "#f4f1ea", "#c9b6a6", "#e2d3c0"],
    brick: ["#c9785c", "#b9694f", "#d18a6a", "#a85f4a"],
    houses: ["#f6efe4", "#fbe3c4", "#e6eef5", "#f3d9d0", "#e3f0df", "#fff4d6"],
    roofs: ["#8c4a3c", "#5d6470", "#a85b3f", "#46505c", "#7a3f35"],
    cars: ["#e5484d", "#3b82f6", "#f5f5f5", "#1f2937", "#22c55e", "#f59e0b", "#8b5cf6", "#06b6d4", "#d1d5db"],
    shirts: ["#e5484d", "#3b82f6", "#f59e0b", "#22c55e", "#8b5cf6", "#f5f5f5", "#ec4899", "#14b8a6"],
    skin: ["#f1c9a5", "#d9a47a", "#a8744f", "#7a4f35"],
    crates: ["#e5484d", "#2f7fd1", "#22a06b", "#f59e0b", "#e9edf1", "#0e9fb5", "#8b5cf6"],
  };
  W.footprints = []; W.towers = []; W.smallCells = []; W.sensors = []; W.cuts = {}; W.cars = [];
  const bx = (i) => -120 + 60 * i;

  /* ---------- instancing: thousands of small repeated shapes drawn in a few calls */
  const G = {
    box: new T.BoxGeometry(1, 1, 1).translate(0, 0.5, 0),
    trunk: new T.CylinderGeometry(0.3, 0.45, 3, 5).translate(0, 1.5, 0),
    pine: new T.ConeGeometry(2.3, 6, 6).translate(0, 5.6, 0),
    round: new T.IcosahedronGeometry(2.7, 0).translate(0, 5, 0),
    pole: new T.CylinderGeometry(0.14, 0.2, 7, 5).translate(0, 3.5, 0),
    body: new T.CylinderGeometry(0.4, 0.5, 1.5, 6).translate(0, 0.75, 0),
    head: new T.IcosahedronGeometry(0.42, 1).translate(0, 1.95, 0),
  };
  const inst = {};
  function add(kind, geo, mat, x, y, z, sx, sy, sz, rot, color) {
    (inst[kind] || (inst[kind] = { geo, mat, items: [] })).items.push([x, y, z, sx, sy, sz, rot || 0, color || "#ffffff"]);
  }
  const WHITE = () => M("#ffffff");
  const ibox = (W.ibox = (x, y, z, w, h, d, color, rot) => add("box", G.box, WHITE(), x, y, z, w, h, d, rot, color));
  const iglow = (x, y, z, w, h, d, color, rot) => add("glow" + color, G.box, W.glow(color, 1.3), x, y, z, w, h, d, rot);
  function tree(x, z, s, type, y) {
    s = s || rr(0.8, 1.25); y = y === undefined ? SLAB : y;
    add("trunk", G.trunk, WHITE(), x, y, z, s, s, s, 0, "#7a5a3c");
    if (type === "pine") add("pine", G.pine, WHITE(), x, y, z, s, s, s, rnd() * 6, pick(["#2f8f5b", "#3aa86a", "#267a4d"]));
    else add("round", G.round, WHITE(), x, y, z, s, s * rr(0.85, 1.1), s, rnd() * 6, pick(["#4fb86b", "#63c77a", "#3fa35c", "#7dd08a"]));
  }
  function lamp(x, z, y) {
    y = y === undefined ? SLAB : y;
    add("pole", G.pole, WHITE(), x, y, z, 1, 1, 1, 0, "#59626e");
    iglow(x, y + 6.9, z, 1.1, 0.25, 0.5, "#ffe7a3");
  }
  function person(x, y, z, color) {
    const s = 1.25;
    add("body", G.body, WHITE(), x, y, z, s, s, s, 0, color || pick(PAL.shirts));
    add("head", G.head, WHITE(), x, y, z, s, s, s, 0, pick(PAL.skin));
  }
  function flush() {
    const d = new T.Object3D(), c = new T.Color();
    for (const k in inst) {
      const I = inst[k], im = new T.InstancedMesh(I.geo, I.mat, I.items.length);
      I.items.forEach((it, i) => {
        d.position.set(it[0], it[1], it[2]); d.scale.set(it[3], it[4], it[5]); d.rotation.set(0, it[6], 0); d.updateMatrix();
        im.setMatrixAt(i, d.matrix); im.setColorAt(i, c.set(it[7]));
      });
      im.castShadow = true; im.receiveShadow = true;
      W.city.add(im);
      delete inst[k];
    }
  }

  /* ---------- window textures: 8 x 8 windows, tiled across a facade */
  const winCache = {};
  function winMat(color, style) {
    const key = color + style;
    if (winCache[key]) return winCache[key];
    const c = document.createElement("canvas"), e = document.createElement("canvas");
    c.width = c.height = e.width = e.height = 256;
    const g = c.getContext("2d"), ge = e.getContext("2d");
    g.fillStyle = style === "glass" ? "#9fc4dd" : "#ffffff"; g.fillRect(0, 0, 256, 256);
    ge.fillStyle = "#000"; ge.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) {
      const x = i * 32, y = j * 32;
      let r;
      if (style === "office") r = [x + 2, y + 8, 28, 18];
      else if (style === "glass") r = [x + 1.5, y + 1.5, 29, 29];
      else if (style === "band") r = [x, y + 9, 32, 15];
      else r = [x + 8, y + 7, 16, 19];
      g.fillStyle = style === "glass" ? pick(["#5f9cc4", "#6aa8cf", "#5490b8", "#77b3d6"]) : pick(["#3f5b78", "#4a6887", "#38536e"]);
      g.fillRect(r[0], r[1], r[2], r[3]);
      g.fillStyle = "rgba(255,255,255,.2)"; g.fillRect(r[0], r[1], r[2], r[3] * 0.32);
      if (rnd() < 0.4) { ge.fillStyle = pick(["#ffd98a", "#ffe9b8", "#cfe8ff", "#ffc76a"]); ge.fillRect(r[0], r[1], r[2], r[3]); }
    }
    const tex = new T.CanvasTexture(c), etex = new T.CanvasTexture(e);
    for (const t of [tex, etex]) { t.wrapS = t.wrapT = T.RepeatWrapping; t.anisotropy = 4; }
    tex.encoding = etex.encoding = T.sRGBEncoding;
    const m = new T.MeshStandardMaterial({ color, map: tex, emissive: 0xffffff, emissiveMap: etex, emissiveIntensity: 0.02, roughness: style === "glass" ? 0.35 : 0.75, metalness: style === "glass" ? 0.25 : 0.02 });
    W.winMats.push(m);
    return (winCache[key] = m);
  }
  /* A building volume with windows on its four sides. y is the base. */
  function tower(x, z, w, d, h, color, style, parent, y, roofColor) {
    y = y === undefined ? SLAB : y;
    const geo = new T.BoxGeometry(w, h, d), uv = geo.attributes.uv;
    const fl = Math.max(1, Math.round(h / 3.4)), bw = Math.max(1, Math.round(w / 3.2)), bd = Math.max(1, Math.round(d / 3.2));
    const ou = Math.floor(rnd() * 8) / 8, ov = Math.floor(rnd() * 8) / 8;
    for (let i = 0; i < uv.count; i++) {
      const face = Math.floor(i / 4);
      if (face === 2 || face === 3) continue;
      uv.setXY(i, ou + (uv.getX(i) * (face < 2 ? bd : bw)) / 8, ov + (uv.getY(i) * fl) / 8);
    }
    const side = winMat(color, style || "resi"), roof = M(roofColor || "#59616d");
    const m = mesh(geo, [side, side, roof, roof, side, side], x, y + h / 2, z, parent);
    if (!parent) W.footprints.push({ x, z, w, d, h: y + h });
    return m;
  }
  function roofKit(x, z, w, d, top, parent) {
    const p = parent || W.city, n = 1 + Math.floor(rnd() * 3);
    box(w + 0.6, 0.5, d + 0.6, "#6b7480", x, top, z, p);
    for (let i = 0; i < n; i++) box(rr(2, 4), rr(1, 2), rr(2, 3.5), pick(["#c9d1d9", "#aeb7c2", "#8d97a3"]), x + rr(-w / 3, w / 3), top + 0.5, z + rr(-d / 3, d / 3), p);
    if (rnd() < 0.4) cyl(1.3, 1.3, 2.2, "#b08968", x + rr(-w / 4, w / 4), top + 0.5, z + rr(-d / 4, d / 4), p, 8);
  }
  function walls(parent, x, z, w, d, h, color, y, th) {
    th = th || 0.6; y = y || 0;
    return [
      box(w, h, th, color, x, y, z - d / 2 + th / 2, parent),
      box(w, h, th, color, x, y, z + d / 2 - th / 2, parent),
      box(th, h, d, color, x - w / 2 + th / 2, y, z, parent),
      box(th, h, d, color, x + w / 2 - th / 2, y, z, parent),
    ];
  }
  function gable(w, d, rh, color, x, y, z, parent, rot) {
    const s = new T.Shape();
    s.moveTo(-w / 2 - 0.6, 0); s.lineTo(w / 2 + 0.6, 0); s.lineTo(0, rh); s.closePath();
    const geo = new T.ExtrudeGeometry(s, { depth: d + 1.2, bevelEnabled: false });
    geo.translate(0, 0, -(d + 1.2) / 2);
    const m = mesh(geo, color, x, y, z, parent);
    if (rot) m.rotation.y = rot;
    return m;
  }
  const cut = (name, objs) => (W.cuts[name] = (W.cuts[name] || []).concat(objs));
  W.setCuts = function (list) {
    list = list || [];
    for (const k in W.cuts) for (const o of W.cuts[k]) o.visible = list.indexOf(k) < 0;
  };

  /* ================================================================= land, sea, roads */
  function rounded(x0, x1, z0, z1, r) {
    const s = new T.Shape();
    s.moveTo(x0 + r, -z0); s.lineTo(x1 - r, -z0); s.quadraticCurveTo(x1, -z0, x1, -z0 - r);
    s.lineTo(x1, -z1 + r); s.quadraticCurveTo(x1, -z1, x1 - r, -z1);
    s.lineTo(x0 + r, -z1); s.quadraticCurveTo(x0, -z1, x0, -z1 + r);
    s.lineTo(x0, -z0 - r); s.quadraticCurveTo(x0, -z0, x0 + r, -z0);
    return s;
  }
  function land() {
    const slab = (grow, depth, color, y, opt) => {
      const geo = new T.ExtrudeGeometry(rounded(-206 - grow, 206 + grow, -248 - grow, 198 + grow, 46 + grow), { depth, bevelEnabled: false, curveSegments: 10 });
      geo.rotateX(-Math.PI / 2);
      const m = mesh(geo, M(color, opt), 0, y - depth, 0);
      m.castShadow = false;
      return m;
    };
    slab(0, 7, "#86c873", 0);
    slab(7, 5, "#f0dfb0", -0.5);
    slab(22, 3, "#63d2d6", -1.15, { roughness: 0.3 });
    const sea = mesh(new T.PlaneGeometry(6000, 6000), M("#2596c9", { roughness: 0.28, metalness: 0.12, flatShading: false }), 0, -1.6, 0);
    sea.rotation.x = -Math.PI / 2; sea.castShadow = false;

    /* roads */
    const road = M("#3d4552");
    for (let i = 0; i < 6; i++) {
      const p = -150 + 60 * i;
      box(12, 0.08, 312, road, p, 0, 0).castShadow = false;
      box(312, 0.08, 12, road, 0, 0, p).castShadow = false;
      for (let s = -153; s <= 153; s += 6) {
        if (Math.abs(((s + 150) % 60 + 60) % 60 - 0) < 9 || Math.abs(((s + 150) % 60 + 60) % 60 - 60) < 9) continue;
        ibox(p, 0.09, s, 0.3, 0.02, 2.4, "#e9edf1");
        ibox(s, 0.09, p, 2.4, 0.02, 0.3, "#e9edf1");
      }
      for (let j = 0; j < 6; j++) {
        const q = -150 + 60 * j;
        for (let k = -2; k <= 2; k++) {
          ibox(p + k * 2.1, 0.09, q - 7.6, 1.1, 0.02, 2.2, "#dfe4ea"); ibox(p + k * 2.1, 0.09, q + 7.6, 1.1, 0.02, 2.2, "#dfe4ea");
          ibox(p - 7.6, 0.09, q + k * 2.1, 2.2, 0.02, 1.1, "#dfe4ea"); ibox(p + 7.6, 0.09, q + k * 2.1, 2.2, 0.02, 1.1, "#dfe4ea");
        }
      }
    }
    /* pavements under every block, with street lamps on the corners */
    for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) {
      const park = i === 2 && j === 2, resi = j >= 3 && i >= 1;
      box(48, SLAB, 48, "#cdd2d8", bx(i), 0, bx(j)).castShadow = false;
      if (park || resi) box(43, 0.06, 43, park ? "#79c46a" : "#8fd07c", bx(i), SLAB, bx(j)).castShadow = false;
      for (const a of [-1, 1]) for (const b of [-1, 1]) lamp(bx(i) + a * 22.6, bx(j) + b * 22.6);
    }
    place("city", 0, 6, -10);
  }

  /* ================================================================= districts */
  function towersBlock(cx, cz, lo, hi) {
    for (const a of [-1, 1]) for (const b of [-1, 1]) {
      const w = rr(14, 19), d = rr(14, 19), h = rr(lo, hi), x = cx + a * 11.5, z = cz + b * 11.5;
      const style = pick(["office", "glass", "band", "resi"]);
      tower(x, z, w, d, h, style === "resi" ? pick(PAL.brick) : pick(PAL.towers), style);
      roofKit(x, z, w, d, SLAB + h);
      if (h > 34 && rnd() < 0.5) { tower(x, z, w * 0.6, d * 0.6, rr(6, 12), pick(PAL.towers), "office", null, SLAB + h + 0.5); }
    }
    tree(cx, cz, 1); tree(cx + rr(-2, 2), cz + 22, 0.8); tree(cx + 22, cz + rr(-2, 2), 0.8);
  }
  function house(x, z, rot, hero) {
    const g = group(x, SLAB, z); g.rotation.y = rot;
    const col = pick(PAL.houses);
    box(9, 5, 7, col, 0, 0, 0, g);
    gable(9, 7, 3.2, pick(PAL.roofs), 0, 5, 0, g);
    box(1.3, 2.4, 0.2, "#6b4a35", -1.8, 0, 3.55, g);
    for (const wx of [1.6, -3.4]) box(1.5, 1.4, 0.15, "#3f5b78", wx, 2.4, 3.55, g);
    box(1, 2.2, 1, "#9a5a47", 2.6, 6, -1, g);
    W.footprints.push({ x, z, w: 9, d: 8, h: 8 });
  }
  function housesBlock(cx, cz, skip) {
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
      if (a === 0 && b === 0) { if (!skip) { tree(cx, cz, 1.3); tree(cx + 4, cz - 3, 0.9, "pine"); } continue; }
      if (skip && skip(a, b)) continue;
      const x = cx + a * 14.5, z = cz + b * 14.5;
      house(x, z, pick([0, Math.PI / 2, Math.PI, -Math.PI / 2]));
      tree(x + rr(5.5, 7), z + rr(-6, 6), rr(0.6, 0.9), rnd() < 0.3 ? "pine" : "round");
      if (rnd() < 0.5) ibox(x - 6, SLAB, z + rr(-3, 3), 4.6, 1.5, 2.1, pick(PAL.cars), 0);
    }
  }

  /* ---------- data centre: the mobile core lives here. Roof lifts off to show the racks. */
  function dataCentre(cx, cz) {
    const g = group(cx, SLAB, cz), zc = -4;
    walls(g, 0, zc, 38, 28, 8.5, "#eef1f4");
    box(37, 0.12, 27, "#aab3bd", 0, 0, zc, g);
    for (let r = 0; r < 7; r++) {
      const x = -14.4 + r * 4.8;
      for (const seg of [[-12.5, 10], [1.5, 10]]) {
        ibox(cx + x, SLAB + 0.12, cz + zc + seg[0] + seg[1] / 2 - 2.5, 1.5, 4.4, seg[1], "#22262d");
        for (let k = 0; k < 6; k++) iglow(cx + x + 0.78, SLAB + 0.8 + (k % 3) * 1.2, cz + zc + seg[0] - 1.6 + k * 1.6, 0.06, 0.18, 0.9, k % 2 ? "#37d5ff" : "#3ddc97");
      }
      box(0.5, 0.12, 25, "#e9dfb4", x, 5.4, zc, g);
    }
    box(36, 0.12, 0.6, "#e9dfb4", 0, 5.4, zc - 12.6, g);
    /* control room in the corner */
    box(0.3, 4, 9, "#cfd6dd", 10, 0, zc + 9.2, g); box(8, 1.1, 1.6, "#59626e", 14.5, 0, zc + 11.5, g);
    iglow(cx + 14.5, SLAB + 1.3, cz + zc + 11.3, 3.2, 1.1, 0.12, "#37d5ff");
    person(cx + 14.5, SLAB + 0.1, cz + zc + 9.6, "#0e9fb5"); person(cx - 2.4, SLAB + 0.1, cz + zc - 1.2, "#0e9fb5"); person(cx + 6.8, SLAB + 0.1, cz + zc + 6, "#f59e0b");
    /* the shell that hides in cutaway view */
    const roof = group(0, 8.5, zc, g);
    box(38.6, 0.7, 28.6, "#dfe4ea", 0, 0, 0, roof);
    for (let i = 0; i < 5; i++) { box(4.4, 1.6, 4.4, "#b9c2cc", -15 + i * 7.5, 0.7, -6, roof); cyl(1.6, 1.6, 0.3, "#59626e", -15 + i * 7.5, 2.3, -6, roof, 10); }
    for (let i = 0; i < 4; i++) box(5, 0.25, 8, "#27456e", -12 + i * 8, 0.7, 6, roof).rotation.x = 0.18;
    cut("core", [roof]);
    /* outside: glass office front, generators, fuel tank, dishes */
    tower(cx - 9, cz + 16.5, 18, 7, 6.5, "#cfe1ee", "glass");
    for (let i = 0; i < 3; i++) box(4.5, 2.4, 2.4, "#7f8a96", 6 + i * 5.6, 0, 16, g);
    cyl(1.5, 1.5, 4.6, "#e9edf1", 21.5, 0, 12, g, 10);
    iglow(cx - 19.3, SLAB + 5.2, cz + zc, 0.12, 1.2, 16, "#37d5ff");
    iglow(cx + 19.3, SLAB + 5.2, cz + zc, 0.12, 1.2, 16, "#37d5ff");
    W.footprints.push({ x: cx, z: cz + zc, w: 38, d: 28, h: 9.5 });
    tree(cx - 21, cz + 21, 0.9); tree(cx + 21.5, cz + 21, 0.9, "pine"); tree(cx + 21.5, cz - 21, 0.8, "pine");
    place("core", cx, 5, cz + zc); place("core.racks", cx - 5, 6, cz + zc - 8); place("core.upf", cx + 9.5, 6, cz + zc - 2);
    place("core.control", cx + 14.5, 4, cz + zc + 10.5); place("core.trays", cx - 12, 7, cz + zc + 6);
    place("coreGate", cx, 0.6, cz + 24);
  }

  /* ---------- museum of telecoms */
  function museum(cx, cz) {
    const g = group(cx - 4, SLAB, cz - 4);
    for (let i = 0; i < 3; i++) box(30 - i * 2, 0.5, 21 - i * 2, "#e6dfd0", 0, i * 0.5, 0, g);
    box(24, 9, 15, "#f3ecdd", 0, 1.5, -1, g);
    for (let i = 0; i < 6; i++) cyl(0.8, 0.9, 8.4, "#fbf7ee", -10 + i * 4, 1.5, 7.6, g, 10);
    box(26, 1, 18, "#e6dfd0", 0, 10.4, 0, g);
    gable(25, 17, 3.6, "#c9b99a", 0, 11.4, 0, g);
    iglow(cx - 4, SLAB + 8.2, cz + 3.7, 12, 1.4, 0.15, "#ffb224");
    /* five generations of handset on plinths along the front */
    const hs = [[1.1, 3.2, 0.9, "#d9d2c0"], [0.9, 2.4, 0.6, "#4b5563"], [0.9, 2.1, 0.4, "#3b82f6"], [1.2, 2.3, 0.22, "#111827"], [1.3, 2.5, 0.2, "#a78bfa"]];
    hs.forEach((h, i) => {
      const x = -17 + i * 5.2 + 4;
      cyl(1.3, 1.5, 1.4, "#cfc7b6", x, 0, 18.5, g, 8);
      box(h[0], h[1], h[2], h[3], x, 1.4, 18.5, g);
      if (i === 0) box(0.15, 1.4, 0.15, "#1f2937", x + 0.35, 4.6, 18.5, g);
    });
    /* an old lattice radio mast, for the story of how it started */
    const mx = 19, mz = -14;
    for (let i = 0; i < 5; i++) cyl(lerp(1.3, 0.3, (i + 1) / 5), lerp(1.3, 0.3, i / 5), 5, i % 2 ? "#e5484d" : "#f1f3f5", mx, i * 5, mz, g, 4);
    W.footprints.push({ x: cx - 4, z: cz - 5, w: 26, d: 18, h: 15 });
    tree(cx + 19, cz + 8, 1.1); tree(cx + 19, cz + 18, 0.9); tree(cx - 21, cz - 20, 0.9, "pine");
    place("museum", cx - 4, 6, cz); place("museum.phones", cx - 3, 3.5, cz + 14.5); place("museum.mast", cx + 15, 16, cz - 18);
  }

  /* ---------- hospital: the top floor opens to show a connected ward and a remote-surgery theatre */
  function hospital(cx, cz) {
    const tx = cx - 7, tz = cz - 7, h = 21, y = SLAB + h, w = 28, d = 20;
    tower(tx, tz, w, d, h, "#f7f9fb", "band");
    const g = group(tx, y, tz);
    box(w, 0.25, d, "#d9dee4", 0, 0, 0, g);
    walls(g, 0, 0, w, d, 3.6, "#f1f4f7", 0.25, 0.5);
    box(0.3, 3.2, d - 1, "#e2e7ec", 3.5, 0.25, 0, g);
    box(8, 3.2, 0.3, "#e2e7ec", -9.5, 0.25, -1, g);
    for (let i = 0; i < 4; i++) for (const s of [-1, 1]) {
      const bxx = -11 + i * 4.2, bz = s * 6.3;
      if (s < 0 && i < 2) continue;
      ibox(tx + bxx, y + 0.25, tz + bz, 1.6, 0.8, 3.4, "#fafafa"); ibox(tx + bxx, y + 1.05, tz + bz + 0.4 * s, 1.5, 0.2, 2.2, "#7fb2d9");
      ibox(tx + bxx + 1.5, y + 0.25, tz + bz, 0.12, 2.6, 3.6, "#5e8fa6");
      iglow(tx + bxx - 0.9, y + 1.8, tz + bz + s * 1.5, 0.7, 0.5, 0.1, "#3ddc97");
    }
    person(tx - 4, y + 0.25, tz + 2, "#f5f5f5"); person(tx - 9, y + 0.25, tz + 3.4, "#7fd3c4"); person(tx + 1, y + 0.25, tz - 2.5, "#f5f5f5");
    /* theatre: operating table and a robotic arm driven from another hospital */
    ibox(tx + 9, y + 0.25, tz - 3, 1.8, 1, 4, "#e9edf1"); ibox(tx + 9, y + 1.25, tz - 3, 1.5, 0.25, 3, "#7fb2d9");
    const arm = group(9, 0.25, -6.6, g);
    cyl(0.5, 0.7, 1.6, "#f1f3f5", 0, 0, 0, arm, 8);
    const a1 = group(0, 1.6, 0, arm); box(0.35, 2.6, 0.35, "#37d5ff", 0, 0, 0, a1); a1.rotation.x = 0.7;
    const a2 = group(0, 2.6, 0, a1); box(0.28, 2.2, 0.28, "#f1f3f5", 0, 0, 0, a2); a2.rotation.x = 1.1;
    W.updaters.push((t) => { a1.rotation.x = 0.7 + Math.sin(t * 1.3) * 0.12; a2.rotation.x = 1.1 + Math.sin(t * 2.1) * 0.2; arm.rotation.y = Math.sin(t * 0.7) * 0.25; });
    iglow(tx + 13.3, y + 1.6, tz + 4, 0.1, 1.8, 3.2, "#37d5ff");
    person(tx + 11.2, y + 0.25, tz + 4.6, "#7fd3c4");
    iglow(tx + 3.5, y + 3.3, tz + 0, 0.5, 0.25, 0.5, "#ffb224");
    const roof = group(0, 3.85, 0, g);
    box(w + 0.8, 0.6, d + 0.8, "#dfe4ea", 0, 0, 0, roof);
    box(5, 2, 4, "#c9d1d9", -8, 0.6, -4, roof); box(3, 1.4, 3, "#aeb7c2", 6, 0.6, 4, roof);
    cut("hospital", [roof]);
    /* lower wing with a helipad, and the sign */
    const wx = cx + 13, wz = cz + 11;
    tower(wx, wz, 18, 20, 9, "#eef2f6", "band");
    cyl(7, 7, 0.25, "#59626e", wx, SLAB + 9, wz, null, 20);
    cyl(5.6, 5.6, 0.06, "#e5484d", wx, SLAB + 9.25, wz, null, 20);
    ibox(wx - 1.6, SLAB + 9.32, wz, 0.8, 0.04, 5, "#ffffff"); ibox(wx + 1.6, SLAB + 9.32, wz, 0.8, 0.04, 5, "#ffffff"); ibox(wx, SLAB + 9.32, wz, 3.2, 0.04, 0.8, "#ffffff");
    iglow(tx, SLAB + 15, tz + d / 2 + 0.1, 4.6, 1.5, 0.12, "#3b9dff"); iglow(tx, SLAB + 13.4, tz + d / 2 + 0.1, 1.5, 4.6, 0.12, "#3b9dff");
    tower(cx - 12, cz + 14, 16, 12, 6, "#e3e9ef", "office");
    tree(cx + 2, cz + 20, 0.9); tree(cx - 22, cz + 21.5, 0.8); tree(cx + 21, cz - 20, 1, "pine");
    place("hospital", tx, 14, tz); place("ward", tx, y + 1, tz); place("ward.theatre", tx + 9, y + 2.4, tz - 4.5);
    place("ward.beds", tx - 6, y + 1.8, tz + 6); place("ward.console", tx + 12.6, y + 2.4, tz + 4); place("ward.cell", tx + 3.5, y + 3.4, tz);
    place("helipad", wx, SLAB + 10, wz);
  }

  function campus(cx, cz) {
    tower(cx - 10, cz - 12, 24, 14, 12, "#c9785c", "resi", null, undefined, "#7a3f35");
    tower(cx + 12, cz + 4, 14, 26, 10, "#d18a6a", "resi", null, undefined, "#7a3f35");
    tower(cx - 13, cz + 12, 16, 14, 8, "#f2e9dc", "office");
    box(5, 22, 5, "#b9694f", cx + 12, SLAB, cz - 15); W.footprints.push({ x: cx + 12, z: cz - 15, w: 5, d: 5, h: 26 });
    const cone = mesh(new T.ConeGeometry(4.2, 5, 4), "#46505c", cx + 12, SLAB + 24.5, cz - 15); cone.rotation.y = Math.PI / 4;
    iglow(cx + 12, SLAB + 17, cz - 12.4, 2.4, 2.4, 0.12, "#fff4d6");
    for (let i = 0; i < 6; i++) tree(cx + rr(-6, 4), cz + rr(-2, 6), rr(0.8, 1.2));
    for (let i = 0; i < 5; i++) person(cx + rr(-6, 4), SLAB, cz + rr(-3, 20));
    place("campus", cx, 8, cz);
  }

  /* ---------- smart factory: roof lifts off, robot line, AGVs, private 5G radio */
  function factory(cx, cz) {
    const g = group(cx, SLAB, cz), zc = -3;
    walls(g, 0, zc, 40, 30, 9, "#e8e2d5");
    box(39, 0.12, 29, "#b7bec6", 0, 0, zc, g);
    for (let i = 0; i < 9; i++) { ibox(cx - 16 + i * 4, SLAB + 0.13, cz + zc + 6.4, 2.2, 0.02, 0.25, "#f5c64a"); ibox(cx - 16 + i * 4, SLAB + 0.13, cz + zc - 5, 2.2, 0.02, 0.25, "#f5c64a"); }
    box(34, 0.9, 2.4, "#3a4350", 0, 0.12, zc + 2.5, g);
    box(34, 0.12, 2, "#1f2630", 0, 1.02, zc + 2.5, g);
    const parts = [];
    for (let i = 0; i < 8; i++) parts.push(box(1.5, 1.2, 1.5, i % 3 ? "#f1f3f5" : "#cfd8e3", 0, 1.14, zc + 2.5, g));
    const arms = [];
    for (let i = 0; i < 5; i++) {
      const a = group(-13 + i * 6.5, 0.12, zc - 0.8, g);
      box(1.8, 1.2, 1.8, "#f1f3f5", 0, 0, 0, a);
      const s = group(0, 1.2, 0, a); cyl(0.55, 0.6, 0.6, "#f26b21", 0, 0, 0, s, 8);
      const u = group(0, 0.6, 0, s); box(0.5, 3, 0.5, "#f26b21", 0, 0, 0, u);
      const f = group(0, 3, 0, u); box(0.4, 2.4, 0.4, "#f1f3f5", 0, 0, 0, f); box(0.9, 0.3, 0.3, "#3a4350", 0, 2.4, 0, f);
      arms.push({ s, u, f, ph: i * 1.3 });
    }
    const agvs = [0, 1].map((k) => { const a = group(0, 0.12, 0, g); box(2.4, 0.6, 1.6, "#ffb224", 0, 0, 0, a); box(1.6, 1, 1.2, "#8b5cf6", 0, 0.6, 0, a); return a; });
    W.updaters.push((t) => {
      parts.forEach((p, i) => { p.position.x = ((t * 2.2 + i * 4.25) % 34) - 17; });
      for (const a of arms) { a.s.rotation.y = Math.sin(t * 0.9 + a.ph) * 0.5; a.u.rotation.x = 0.55 + Math.sin(t * 1.4 + a.ph) * 0.25; a.f.rotation.x = 1.25 + Math.sin(t * 1.8 + a.ph) * 0.35; }
      agvs.forEach((a, k) => { const u = ((t * 0.06 + k * 0.5) % 1) * 2, x = u < 1 ? lerp(-16, 16, u) : lerp(16, -16, u - 1); a.position.set(x, 0.12, zc + (u < 1 ? 8.5 : 11)); });
    });
    W.agv = agvs[0];
    for (let i = 0; i < 5; i++) { ibox(cx - 15 + i * 7.5, SLAB + 0.12, cz + zc - 12.2, 5, 4.5, 1.6, "#59626e"); for (let k = 0; k < 3; k++) ibox(cx - 16.6 + i * 7.5 + k * 1.6, SLAB + 1.2 + (k % 2) * 1.6, cz + zc - 11.8, 1.3, 1.2, 1.6, pick(PAL.crates)); }
    person(cx - 6, SLAB + 0.12, cz + zc + 6.5, "#d4f04a"); person(cx + 9, SLAB + 0.12, cz + zc + 5.4, "#d4f04a"); person(cx + 15, SLAB + 0.12, cz + zc - 6, "#d4f04a");
    for (let i = 0; i < 4; i++) box(40, 0.3, 0.4, "#8d97a3", 0, 8.2, zc - 11 + i * 7.4, g);
    box(1.2, 0.5, 1.2, "#fafafa", 0, 7.7, zc + 3.8, g); iglow(cx, SLAB + 7.55, cz + zc + 3.8, 0.5, 0.15, 0.5, "#37d5ff");
    const roof = group(0, 9, zc, g);
    box(40.8, 0.5, 30.8, "#cfd6dd", 0, 0, 0, roof);
    for (let i = 0; i < 4; i++) { const r = gable(7.4, 39, 2.4, "#aeb7c2", 0, 0.5, -11.1 + i * 7.4, roof, Math.PI / 2); r.scale.x = 1; }
    cut("factory", [roof]);
    cyl(1.2, 1.5, 17, "#d9c7b8", 21.5, 0, zc - 13, g, 10); cyl(2.6, 2.6, 6, "#e9edf1", -21.5, 0, 16, g, 12);
    box(8, 3.6, 5, "#dfe3e8", 14, 0, 17.5, g); iglow(cx + 14, SLAB + 2.4, cz + 20.1, 5, 0.8, 0.1, "#ffb224");
    W.footprints.push({ x: cx, z: cz + zc, w: 40, d: 30, h: 10 });
    place("factory", cx, 3, cz + zc); place("factory.arm", cx, 5.2, cz + zc - 0.8); place("factory.agv", cx + 6, 2.6, cz + zc + 9.6);
    place("factory.radio", cx, 8.4, cz + zc + 3.8); place("factory.line", cx - 9, 3, cz + zc + 2.5);
  }

  /* ---------- business tower: the top floor is a working office you can look into */
  function bizBlock(cx, cz) {
    const tx = cx - 6, tz = cz - 6, w = 24, d = 22, h = 54, y = SLAB + h;
    tower(tx, tz, w, d, h, "#e8edf2", "band");
    const g = group(tx, y, tz);
    box(w, 0.25, d, "#8b95a1", 0, 0, 0, g);
    const ws = walls(g, 0, 0, w, d, 3.8, "#f4f6f8", 0.25, 0.5);
    ws[1].scale.y = 0.3; ws[1].position.y = 0.25 + 0.57; ws[3].scale.y = 0.3; ws[3].position.y = 0.25 + 0.57;
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
      if (r === 1 && c === 1) continue;
      const x = tx - 7.5 + c * 7, z = tz - 6 + r * 6;
      ibox(x, y + 0.25, z, 3.6, 1, 1.6, "#eef1f4"); iglow(x - 0.5, y + 1.3, z - 0.3, 1, 0.7, 0.1, "#9fd8ff"); ibox(x + 0.9, y + 1.25, z - 0.3, 0.9, 0.65, 0.1, "#1f2937");
      person(x + rr(-0.8, 0.8), y + 0.25, z + 1.2);
    }
    ibox(tx - 0.5, y + 0.25, tz, 4.5, 1, 2.6, "#d9dee4"); ibox(tx + 8.8, y + 0.25, tz - 9.4, 5, 1.3, 1.2, "#b08968"); person(tx + 8.8, y + 0.25, tz - 8, "#e5484d");
    for (const p of [[-10.5, -9.5], [10.5, 9.5], [-1, 3]]) { ibox(tx + p[0], y + 0.25, tz + p[1], 0.7, 0.7, 0.7, "#59626e"); add("round", G.round, WHITE(), tx + p[0], y - 0.6, tz + p[1], 0.32, 0.32, 0.32, 0, "#3fa35c"); }
    box(0.9, 0.3, 0.9, "#fafafa", 0, 3.6, 0, g); iglow(tx, y + 3.5, tz, 0.4, 0.12, 0.4, "#37d5ff");
    const roof = group(0, 4.05, 0, g);
    box(w + 0.8, 0.6, d + 0.8, "#6b7480", 0, 0, 0, roof);
    box(6, 2.2, 5, "#c9d1d9", -5, 0.6, -3, roof); box(3, 1.5, 3, "#aeb7c2", 6, 0.6, 5, roof); cyl(0.12, 0.12, 5, "#59626e", 9, 0.6, -8, roof, 5);
    const front = [box(w, 2.66, 0.3, M("#9fd0ea", { transparent: true, opacity: 0.45, roughness: 0.2 }), 0, 1.39, d / 2 - 0.25, g), box(0.3, 2.66, d, M("#9fd0ea", { transparent: true, opacity: 0.45, roughness: 0.2 }), w / 2 - 0.25, 1.39, 0, g)];
    front.forEach((m) => (m.castShadow = false));
    cut("office", [roof].concat(front));
    tower(cx + 15, cz - 13, 13, 16, 30, "#d9c7b8", "office"); roofKit(cx + 15, cz - 13, 13, 16, SLAB + 30);
    tower(cx + 14, cz + 12, 15, 17, 22, pick(PAL.brick), "resi"); roofKit(cx + 14, cz + 12, 15, 17, SLAB + 22);
    tower(cx - 9, cz + 16, 22, 10, 14, "#cfe1ee", "glass");
    place("office", tx, y + 1, tz); place("office.cell", tx, y + 3.7, tz); place("office.desks", tx - 7.5, y + 2, tz + 6); place("office.meet", tx - 0.5, y + 1.8, tz); place("biz", tx, 28, tz);
  }

  function hqBlock(cx, cz) {
    const h = 88;
    tower(cx, cz, 21, 21, h, "#d7e6f1", "glass");
    tower(cx, cz, 15, 15, 7, "#c5d9e8", "glass", null, SLAB + h);
    const top = SLAB + h + 7;
    box(16, 0.5, 16, "#59626e", cx, top, cz);
    for (let k = 0; k < 3; k++) {
      const a = (k * 2 * Math.PI) / 3 + 0.5, px = cx + Math.sin(a) * 6, pz = cz + Math.cos(a) * 6;
      cyl(0.15, 0.15, 5, "#8b95a1", px, top + 0.5, pz, null, 6);
      const p = box(1, 2.8, 0.4, "#fafafa", px + Math.sin(a) * 0.4, top + 2.6, pz + Math.cos(a) * 0.4); p.rotation.y = a;
    }
    ball(0.4, W.glow("#ff3b3b", 2), cx, top + 6, cz); cyl(0.1, 0.1, 5.4, "#8b95a1", cx, top + 0.5, cz, null, 5);
    W.towers.push({ name: "rooftop", pos: V(cx, top + 3.5, cz), base: V(cx + 12, 0.5, cz + 12), r: 120 });
    place("rooftop", cx, top + 3.5, cz); place("hq", cx, 40, cz);
    for (const p of [[-16, -16, 13, 12, 26], [16, -16, 12, 12, 38], [-16, 16, 13, 13, 32], [16, 16, 12, 13, 20]]) {
      tower(cx + p[0], cz + p[1], p[2], p[3], p[4], pick(PAL.towers), pick(["office", "band"])); roofKit(cx + p[0], cz + p[1], p[2], p[3], SLAB + p[4]);
    }
  }

  function stadium(cx, cz) {
    const g = group(cx, SLAB, cz);
    const pts = [new T.Vector2(11, 0.3), new T.Vector2(11.4, 1.6), new T.Vector2(17, 7.6), new T.Vector2(17.6, 8), new T.Vector2(17.6, 0)];
    const bowl = mesh(new T.LatheGeometry(pts, 28), M("#e2e8ef", { side: T.DoubleSide }), 0, 0, 0, g);
    bowl.scale.set(1.28, 1, 1);
    box(22, 0.12, 14, "#4fb86b", 0, 0, 0, g);
    for (const x of [-10.8, 0, 10.8]) ibox(cx + x, SLAB + 0.13, cz, 0.2, 0.02, 14, "#ffffff");
    ibox(cx, SLAB + 0.13, cz - 6.9, 22, 0.02, 0.2, "#ffffff"); ibox(cx, SLAB + 0.13, cz + 6.9, 22, 0.02, 0.2, "#ffffff");
    for (let i = 0; i < 520; i++) {
      const a = rnd() * Math.PI * 2, k = rnd(), r = lerp(11.8, 16.6, k);
      ibox(cx + Math.cos(a) * r * 1.28, SLAB + lerp(1.7, 7.4, k), cz + Math.sin(a) * r, 0.55, 0.6, 0.55, pick(PAL.shirts));
    }
    W.stadiumMasts = [];
    for (const a of [-1, 1]) for (const b of [-1, 1]) {
      cyl(0.3, 0.45, 15, "#8b95a1", a * 21.5, 0, b * 21, g, 6);
      const l = box(4, 2.2, 0.5, W.glow("#fff4d6", 1.6), a * 21.5, 15, b * 21, g); l.rotation.y = Math.atan2(a, b);
      W.stadiumMasts.push(V(cx + a * 21.5, SLAB + 14, cz + b * 21));
    }
    for (let i = 0; i < 10; i++) person(cx + rr(-9, 9), SLAB + 0.12, cz + rr(-5, 5), i < 5 ? "#e5484d" : "#3b82f6");
    place("stadium", cx, 5, cz);
  }

  function park(cx, cz) {
    cyl(9, 9, 0.12, M("#4cc3d9", { roughness: 0.25 }), cx - 9, SLAB + 0.02, cz - 8, null, 20).castShadow = false;
    cyl(9.8, 9.8, 0.08, "#e7d9ae", cx - 9, SLAB, cz - 8, null, 20).castShadow = false;
    ibox(cx, SLAB + 0.06, cz + 4, 43, 0.03, 2.2, "#e7d9ae"); ibox(cx + 6, SLAB + 0.06, cz, 2.2, 0.03, 43, "#e7d9ae");
    cyl(2.4, 2.6, 0.8, "#cfd6dd", cx + 6, SLAB, cz + 4, null, 12); cyl(0.4, 0.6, 2.2, "#e9edf1", cx + 6, SLAB, cz + 4, null, 8);
    for (let i = 0; i < 26; i++) {
      const x = cx + rr(-20, 20), z = cz + rr(-20, 20);
      if (Math.hypot(x - cx + 9, z - cz + 8) < 11 || Math.abs(z - cz - 4) < 2.5 || Math.abs(x - cx - 6) < 2.5) continue;
      tree(x, z, rr(0.9, 1.5), rnd() < 0.25 ? "pine" : "round");
    }
    for (const p of [[-4, 6.4], [12, 6.4], [8.4, -10], [8.4, 14]]) ibox(cx + p[0], SLAB, cz + p[1], 2.4, 0.6, 0.7, "#b08968");
    for (let i = 0; i < 12; i++) person(cx + rr(-18, 18), SLAB, cz + pick([4, 4.6, 3.4]) + rr(-0.3, 0.3));
    for (let i = 0; i < 6; i++) person(cx + 6 + rr(-0.5, 0.5), SLAB, cz + rr(-18, 18));
    /* the learner's guide through the lessons: someone on a bench with a phone */
    person(cx + 12, SLAB, cz + 7.6, "#ffb224"); iglow(cx + 12.5, SLAB + 1.9, cz + 8, 0.35, 0.6, 0.08, "#9fd8ff");
    place("park", cx, 3, cz); place("parkUser", cx + 12, SLAB + 2.4, cz + 7.6);
    for (const a of [-1, 1]) for (const b of [-1, 1]) smallCell(cx + a * 22.6, cz + b * 22.6);
  }
  function smallCell(x, z) {
    box(0.7, 1.3, 0.5, "#fafafa", x, SLAB + 5.2, z); ball(0.22, W.glow("#37d5ff", 2), x, SLAB + 6.8, z + 0.3);
    W.smallCells.push(V(x, SLAB + 5.8, z));
  }

  function mall(cx, cz) {
    const g = group(cx, SLAB, cz);
    tower(cx - 5, cz - 5, 32, 26, 9, "#f4f1ea", "band");
    const dome = mesh(new T.SphereGeometry(7, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2), M("#9fd0ea", { transparent: true, opacity: 0.55, roughness: 0.15, metalness: 0.2 }), -5, 9, -7, g); dome.castShadow = false;
    iglow(cx - 5, SLAB + 6.4, cz + 8.1, 14, 1.6, 0.14, "#ff6b9a");
    cyl(3.4, 3.4, 0.2, "#59626e", 5.5, 9, 1, g, 16); cyl(2.6, 2.6, 0.06, "#ffb224", 5.5, 9.2, 1, g, 16);
    for (let i = 0; i < 9; i++) { ibox(cx - 19 + i * 4.6, SLAB, cz + 15, 2.1, 1.5, 4.6, pick(PAL.cars)); if (i < 7) ibox(cx - 19 + i * 4.6, SLAB, cz + 21.4, 2.1, 1.5, 4.6, pick(PAL.cars)); }
    for (let i = 0; i < 4; i++) ibox(cx + 18.5, SLAB, cz - 16 + i * 6, 4.6, 1.5, 2.1, pick(PAL.cars));
    tree(cx + 20, cz + 12, 0.9); tree(cx + 14, cz + 21.5, 0.8);
    for (let i = 0; i < 6; i++) person(cx + rr(-16, 6), SLAB, cz + 10.5 + rr(-0.6, 0.6));
    place("mall", cx - 5, 7, cz - 4); place("dronepad", cx + 5.5, SLAB + 10, cz + 1);
  }

  function logistics(cx, cz) {
    tower(cx - 3, cz - 6, 36, 26, 10, "#e3e8ee", "band", null, undefined, "#8b95a1");
    iglow(cx - 3, SLAB + 8, cz + 7.1, 20, 1.2, 0.12, "#3b9dff");
    for (let i = 0; i < 5; i++) { ibox(cx - 17 + i * 6.6, SLAB, cz + 7.2, 4.2, 4, 0.3, "#59626e"); if (i % 2 === 0) { ibox(cx - 17 + i * 6.6, SLAB + 0.5, cz + 12.5, 2.6, 3, 7, "#f1f3f5"); ibox(cx - 17 + i * 6.6, SLAB + 0.5, cz + 17.4, 2.5, 2.4, 2.4, pick(PAL.cars)); } }
    /* edge computing node: a containerised micro data centre at the kerb */
    const ex = cx + 18, ez = cz + 17;
    box(4, 3.2, 8, "#1f2a3a", ex, SLAB, ez); iglow(ex - 2.05, SLAB + 2.2, ez, 0.08, 0.3, 7, "#37d5ff"); iglow(ex + 2.05, SLAB + 2.2, ez, 0.08, 0.3, 7, "#37d5ff");
    box(2, 1, 2, "#8b95a1", ex, SLAB + 3.2, ez - 2); cyl(0.1, 0.1, 4, "#8b95a1", ex, SLAB + 3.2, ez + 3, null, 5);
    place("logistics", cx - 3, 6, cz - 4); place("edge", ex, SLAB + 3.4, ez);
  }

  function port() {
    box(42, 0.5, 150, "#b9c0c8", -179, 0, 76).castShadow = false;
    for (let s = 0; s < 3; s++) for (let r = 0; r < 9; r++) for (let l = 0; l < 4; l++) {
      if (rnd() < 0.25 + l * 0.18) break;
      ibox(-136 + s * 14 + rr(-0.1, 0.1), SLAB + l * 2.6, 40 + r * 5.2, 12, 2.5, 2.5, pick(PAL.crates));
    }
    for (let r = 0; r < 20; r++) for (let l = 0; l < 3; l++) { if (rnd() < 0.3 + l * 0.2) break; ibox(-170 + (r % 2) * 3.2, 0.5 + l * 2.6, 22 + r * 6.2, 2.5, 2.5, 6, pick(PAL.crates), 0); }
    W.cranes = [];
    for (let i = 0; i < 3; i++) {
      const g = group(-192, 0.5, 34 + i * 40);
      for (const a of [-1, 1]) for (const b of [-1, 1]) box(0.9, 26, 0.9, "#e5484d", a * 5, 0, b * 5, g);
      box(11, 1, 11, "#e5484d", 0, 26, 0, g);
      box(46, 1.4, 2, "#e5484d", -10, 27, 0, g); box(1, 9, 1, "#e5484d", 0, 27, 0, g);
      const trolley = group(-14, 26, 0, g); box(3, 1.2, 3, "#f5c64a", 0, -0.2, 0, trolley); box(0.15, 9, 0.15, "#1f2937", 0, -9.2, 0, trolley); box(6, 2.4, 2.4, pick(PAL.crates), 0, -11.6, 0, trolley);
      W.cranes.push(trolley);
    }
    W.updaters.push((t) => W.cranes.forEach((c, i) => { c.position.x = -16 + Math.sin(t * 0.25 + i * 2) * 13; }));
    /* container ship alongside */
    const ship = (W.ship = group(-226, -1.2, 78));
    box(16, 6, 96, "#22344d", 0, 0, 0, ship); box(15, 0.4, 94, "#b84a3a", 0, 0, 0, ship);
    box(12, 9, 9, "#f1f3f5", 0, 6, 39, ship); box(13, 1.4, 4, "#22344d", 0, 15, 39, ship); cyl(1.2, 1.4, 4, "#e5484d", 0, 16.4, 41, ship, 8);
    for (let r = 0; r < 11; r++) for (let c = 0; c < 4; c++) for (let l = 0; l < 3; l++) { if (rnd() < 0.2 + l * 0.2) break; box(2.7, 2.5, 6, pick(PAL.crates), -5 + c * 3.3, 6 + l * 2.6, -42 + r * 6.6, ship); }
    W.updaters.push((t) => { ship.position.y = -1.2 + Math.sin(t * 0.6) * 0.18; });
    /* private-network mast and its on-site core cabinet */
    const mx = -164, mz = 100;
    cyl(0.25, 0.45, 20, "#e9edf1", mx, 0.5, mz, null, 6);
    for (let k = 0; k < 3; k++) { const a = (k * 2 * Math.PI) / 3; const p = box(0.8, 2.6, 0.35, "#fafafa", mx + Math.sin(a) * 0.8, 17.6, mz + Math.cos(a) * 0.8); p.rotation.y = a; }
    ball(0.3, W.glow("#a78bfa", 2), mx, 21, mz);
    box(3.4, 2.6, 2.2, "#2f3b52", mx + 4, 0.5, mz + 2); iglow(mx + 4, 2.4, mz + 3.15, 2.4, 0.3, 0.06, "#a78bfa");
    W.portMast = V(mx, 19, mz);
    for (let i = 0; i < 6; i++) person(-176 + rr(-3, 3), 0.5, 30 + i * 22, "#d4f04a");
    place("port", -182, 6, 78); place("portmast", mx, 19, mz); place("port.crane", -192, 28, 74); place("port.core", mx + 4, 3, mz + 2); place("port.ship", -226, 12, 78); place("yard", -122, 6, 60);
  }

  function landing(cx, cz) {
    tower(cx - 10, cz - 8, 18, 14, 6.5, "#e9edf1", "band", null, undefined, "#8b95a1");
    iglow(cx - 10, SLAB + 4.8, cz - 0.9, 8, 1, 0.12, "#37d5ff");
    box(3, 1.4, 3, "#59626e", cx - 10, SLAB, cz + 6); cyl(1, 1, 0.1, "#3a4350", cx - 10, SLAB + 1.4, cz + 6, null, 10);
    for (let i = 0; i < 4; i++) ibox(cx + 6 + (i % 2) * 8, SLAB, cz - 14 + Math.floor(i / 2) * 14, 3, 3.2, 11, "#f59e0b");
    box(20, 4.6, 6, "#dfe3e8", cx + 10, SLAB, cz + 16); tree(cx - 20, cz + 18, 1); tree(cx - 14, cz + 20, 0.8, "pine");
    place("landing", cx - 10, 4, cz - 4); place("manhole", cx - 10, SLAB + 1.6, cz + 6);
  }

  /* ---------- smart home: front wall and roof come away to show the rooms and the 5G router */
  function smartHome(cx, cz) {
    const g = group(cx, SLAB, cz), w = 13, d = 10;
    const ws = walls(g, 0, 0, w, d, 6.6, "#f6efe4", 0, 0.4);
    box(w - 0.6, 0.2, d - 0.6, "#b98a5a", 0, 0, 0, g); box(w - 0.6, 0.25, d - 0.6, "#b98a5a", 0, 3.3, 0, g);
    box(0.25, 3.3, d - 1, "#efe6d6", 1, 0, 0, g); box(0.25, 3.1, d - 1, "#efe6d6", -1.5, 3.55, 0, g);
    ibox(cx - 3.6, SLAB + 0.2, cz - 3.2, 4.2, 0.9, 1.6, "#3b6ea5"); iglow(cx - 3.6, SLAB + 1.4, cz + 4.4, 2.6, 1.5, 0.1, "#9fd8ff");
    ibox(cx + 3.8, SLAB + 0.2, cz - 1, 2.4, 1, 1.4, "#b08968"); ibox(cx + 3.6, SLAB + 0.2, cz - 4.2, 4, 1.2, 0.8, "#e9edf1");
    ibox(cx - 4, SLAB + 3.55, cz - 2.6, 3, 0.7, 4, "#f1f3f5"); ibox(cx - 4, SLAB + 4.25, cz - 2, 2.9, 0.2, 2.6, "#e5484d");
    ibox(cx + 3.4, SLAB + 3.55, cz - 2.8, 2.6, 0.7, 3.6, "#f1f3f5"); ibox(cx + 3.4, SLAB + 4.25, cz - 2.2, 2.5, 0.2, 2.4, "#37a6c9");
    ibox(cx + 5.6, SLAB + 0.2, cz + 3.4, 0.8, 1.1, 0.8, "#b08968"); iglow(cx + 5.6, SLAB + 1.3, cz + 3.4, 0.5, 0.7, 0.3, "#3ddc97");
    person(cx - 3.6, SLAB + 0.2, cz - 1.6, "#8b5cf6"); person(cx + 2.8, SLAB + 3.55, cz + 1.6, "#ffb224");
    /* outdoor 5G receiver on the gable end */
    cyl(0.08, 0.08, 3.2, "#8b95a1", w / 2 + 0.3, 6, 0, g, 5); box(0.5, 1, 0.6, "#fafafa", w / 2 + 0.3, 8.6, 0, g);
    const roof = gable(w, d, 4, "#5d6470", 0, 6.6, 0, g);
    cut("home", [roof, ws[1]]);
    box(1.4, 2.5, 0.12, "#6b4a35", -3, -3.3, 0.22, ws[1]);
    ibox(cx + 11, SLAB, cz + 2, 2.1, 1.5, 4.6, "#1f2937"); tree(cx - 10, cz + 4, 1.1); tree(cx + 2, cz - 9, 0.9);
    person(cx + 8, SLAB, cz + 6.5, "#e5484d");
    W.footprints.push({ x: cx, z: cz, w, d, h: 10 });
    place("home", cx, 4, cz); place("home.cpe", cx + w / 2 + 0.3, SLAB + 9.2, cz); place("home.router", cx + 5.6, SLAB + 1.8, cz + 3.4);
    place("home.tv", cx - 3.6, SLAB + 2.2, cz + 4.2); place("homeUser", cx - 3.6, SLAB + 2.4, cz - 1.6);
  }

  function farm() {
    const fields = [[-128, "#c8a35a", "#b8924c"], [-70, "#7dbf5a", "#69ab4a"], [-12, "#8a6a48", "#7a5b3c"], [42, "#d9c15a", "#c9b04a"]];
    fields.forEach((f, k) => { for (let r = 0; r < 18; r++) ibox(180, 0, f[0] + r * 2.7 - 22, 36, 0.14 + (r % 2) * 0.1, 2.7, r % 2 ? f[1] : f[2]); });
    box(12, 6, 9, "#b8402f", 176, 0, -99); gable(12, 9, 3.6, "#5d6470", 176, 6, -99); cyl(2.6, 2.6, 11, "#e9edf1", 186, 0, -100, null, 12);
    mesh(new T.ConeGeometry(2.8, 2, 12), "#aeb7c2", 186, 12, -100);
    /* an autonomous harvester working the last field */
    const hv = (W.harvester = group(180, 0.2, 42));
    box(4.4, 2.6, 3.2, "#f5c64a", 0, 1, 0, hv); box(2.2, 1.8, 2.6, "#1f2937", 0.8, 3.6, 0, hv); box(1.6, 1, 8, "#f5c64a", 3.2, 0.3, 0, hv);
    for (const z of [-1.8, 1.8]) { const wh = mesh(new T.CylinderGeometry(1.2, 1.2, 0.8, 10), "#15181d", 0.6, 1.2, z, hv); wh.rotation.x = Math.PI / 2; }
    ball(0.3, W.glow("#37d5ff", 2), 0.8, 5.7, 0, hv);
    W.updaters.push((t) => { const u = (t * 0.035) % 1, f = u < 0.5 ? u * 2 : 2 - u * 2; hv.position.x = lerp(165, 195, f); hv.rotation.y = u < 0.5 ? 0 : Math.PI; hv.position.z = 30 + Math.floor((t * 0.035) % 6) * 6; });
    for (const p of [[168, -120], [192, -128], [170, -62], [190, -50], [172, -4], [190, 6], [170, 50], [192, 28]]) {
      cyl(0.08, 0.08, 2.6, "#59626e", p[0], 0.2, p[1], null, 5); box(0.5, 0.5, 0.5, "#fafafa", p[0], 2.8, p[1]); ball(0.16, W.glow("#3ddc97", 2), p[0], 3.6, p[1]);
      W.sensors.push(V(p[0], 3.4, p[1]));
    }
    for (let i = 0; i < 7; i++) { const x = rr(166, 196), z = rr(-88, -52); ibox(x, 0.3, z, 2, 1.1, 0.9, pick(["#f5f5f5", "#6b4a35", "#1f2937"]), rnd() * 3); }
    for (let i = 0; i < 6; i++) tree(160.5, -140 + i * 38, 1, i % 2 ? "pine" : "round", 0);
    /* solar farm */
    for (let r = 0; r < 7; r++) for (let c = 0; c < 3; c++) {
      const p = box(10, 0.2, 5, M("#22457a", { roughness: 0.3, metalness: 0.4 }), 168 + c * 12, 1.6, 86 + r * 9.4); p.rotation.x = 0.5;
      ibox(168 + c * 12, 0, 86 + r * 9.4, 0.3, 1.6, 0.3, "#8b95a1");
    }
    place("farm", 180, 3, -30); place("farm.harvester", 180, 5, 42); place("farm.sensor", 172, 4, -4); place("farm.barn", 178, 8, -99); place("solar", 180, 3, 112);
  }

  /* ---------- hills, wind turbines, hilltop macro site, satellite ground station */
  const HILLS = [[-112, -205, 56, 20, 30], [22, -207, 62, 30, 32], [142, -205, 50, 18, 29]];
  const hillY = (k, x, z) => { const h = HILLS[k], u = 1 - Math.pow((x - h[0]) / h[2], 2) - Math.pow((z - h[1]) / h[4], 2); return -3 + h[3] * Math.sqrt(Math.max(0, u)); };
  function turbine(x, y, z) {
    const g = group(x, y - 0.5, z);
    cyl(0.5, 1, 28, "#f6f8fa", 0, 0, 0, g, 8); box(1.6, 1.6, 3.6, "#f6f8fa", 0, 27.6, 0.6, g);
    const rotor = group(0, 28.4, 2.6, g); ball(0.9, "#e9edf1", 0, 0, 0, rotor);
    for (let k = 0; k < 3; k++) { const b = group(0, 0, 0, rotor); b.rotation.z = (k * 2 * Math.PI) / 3; const bl = box(1.1, 13, 0.25, "#fbfcfd", 0, 0.6, 0, b); bl.rotation.y = 0.25; }
    const sp = rr(0.9, 1.5);
    W.updaters.push((t, dt) => { rotor.rotation.z -= dt * sp; });
  }
  function hills() {
    HILLS.forEach((h, k) => {
      const geo = new T.SphereGeometry(1, 16, 9, 0, Math.PI * 2, 0, Math.PI / 2);
      const m = mesh(geo, k === 1 ? "#74b862" : "#7fc46c", h[0], -3, h[1]); m.scale.set(h[2], h[3], h[4]);
      for (let i = 0; i < 9; i++) { const a = rnd() * 6.28, r = rr(0.5, 0.86); const x = h[0] + Math.cos(a) * h[2] * r, z = h[1] + Math.sin(a) * h[4] * r; tree(x, z, rr(0.9, 1.4), "pine", hillY(k, x, z) - 0.6); }
    });
    for (const p of [[0, -132, -204], [0, -96, -200], [2, 122, -206]]) turbine(p[1], hillY(p[0], p[1], p[2]), p[2]);
    place("wind", -114, 34, -202);
    macroTower("hilltower", 22, hillY(1, 22, -207), -207, 30, 240);
    /* satellite ground station */
    const gx = 156, gz = -204, gy = hillY(2, gx, gz) - 0.4, g = group(gx, gy, gz);
    cyl(1.2, 1.6, 4, "#e9edf1", 0, 0, 0, g, 8);
    const dish = mesh(new T.SphereGeometry(5, 14, 6, 0, Math.PI * 2, 0, Math.PI / 2.6), M("#f6f8fa", { side: T.DoubleSide }), 0, 9.6, 0, g);
    dish.rotation.x = Math.PI + 0.75; dish.rotation.z = -0.3;
    box(5, 2.6, 4, "#cfd6dd", -7, 0, 1, g);
    W.groundStation = V(gx, gy + 7, gz);
    place("ground", gx, gy + 6, gz);
  }
  function macroTower(name, x, y, z, h, r) {
    const g = group(x, y, z), n = 6;
    for (let i = 0; i < n; i++) cyl(lerp(1.5, 0.45, (i + 1) / n), lerp(1.5, 0.45, i / n), h / n, i % 2 ? "#e5484d" : "#f4f6f8", 0, (i * h) / n, 0, g, 4);
    cyl(2, 2, 0.25, "#8b95a1", 0, h - 5.2, 0, g, 8); cyl(1.6, 1.6, 0.25, "#8b95a1", 0, h - 9.4, 0, g, 8);
    for (const tier of [h - 4.6, h - 8.8]) for (let k = 0; k < 3; k++) {
      const a = (k * 2 * Math.PI) / 3 + (tier === h - 4.6 ? 0 : 0.5);
      const p = box(0.95, 3.2, 0.36, "#fbfcfd", Math.sin(a) * 1.7, tier, Math.cos(a) * 1.7, g); p.rotation.y = a;
    }
    const d = mesh(new T.CylinderGeometry(1, 1, 0.4, 12), "#e9edf1", 0.9, h * 0.55, 0.9, g); d.rotation.z = Math.PI / 2; d.rotation.y = -Math.PI / 4;
    ball(0.38, W.glow("#ff3b3b", 2.2), 0, h + 0.5, 0, g);
    box(3.4, 2.4, 2.2, "#cfd6dd", 3.6, 0, 1.2, g); box(1.6, 1.6, 1.2, "#aeb7c2", 3.6, 0, -1.4, g);
    for (let k = 0; k < 8; k++) { const a = (k * Math.PI) / 4; box(0.15, 1.6, 0.15, "#8b95a1", Math.cos(a) * 6, 0, Math.sin(a) * 6, g); }
    W.towers.push({ name, pos: V(x, y + h - 3, z), base: V(x, y + 0.5, z), r: r || 150 });
    place(name, x, y + h - 3, z); place(name + ".base", x + 3.6, y + 2.6, z + 1.2);
  }

  function beach() {
    box(300, 0.2, 30, "#f3e3b5", 0, 0, 175).castShadow = false;
    for (let i = 0; i < 16; i++) {
      const x = -140 + i * 18 + rr(-3, 3), z = rr(164, 172);
      add("trunk", G.trunk, WHITE(), x, 0.2, z, 0.8, 2.2, 0.8, 0, "#9a7b55"); add("round", G.round, WHITE(), x, 2.4, z, 1.1, 0.35, 1.1, rnd() * 6, "#3fa35c");
    }
    for (let i = 0; i < 12; i++) { const x = rr(-130, 130), z = rr(178, 186); cyl(0.06, 0.06, 2.4, "#8b95a1", x, 0.2, z, null, 4); mesh(new T.ConeGeometry(2, 0.9, 8), pick(["#e5484d", "#ffb224", "#37d5ff", "#f5f5f5"]), x, 3, z); ibox(x + 1, 0.2, z + 0.6, 0.7, 0.2, 1.8, "#f5f5f5"); person(x - 1.2, 0.2, z + 1.2); }
    box(4, 0.4, 46, "#b08968", -30, 0.6, 212);
    for (let i = 0; i < 6; i++) box(0.4, 3, 0.4, "#7a5a3c", -32 + (i % 2) * 4, -2, 196 + Math.floor(i / 2) * 18);
    W.boats = [];
    for (let i = 0; i < 3; i++) {
      const b = group(-80 + i * 90, -1.3, 240 + i * 14); box(2.6, 1.3, 7, "#f6f8fa", 0, 0, 0, b); cyl(0.1, 0.1, 8, "#8b95a1", 0, 1.3, 0, b, 5);
      const s = mesh(new T.ConeGeometry(2.6, 7, 3), pick(["#ffffff", "#ffb224", "#ff6b9a"]), 0, 5.4, -0.6, b); s.scale.z = 0.12;
      W.boats.push(b);
    }
    W.updaters.push((t) => W.boats.forEach((b, i) => { b.position.x = -80 + i * 90 + Math.sin(t * 0.05 + i * 2) * 60; b.rotation.z = Math.sin(t + i) * 0.04; }));
    macroTower("southtower", 66, 0.2, 172, 32, 170);
    place("beach", 0, 3, 176);
  }

  /* ================================================================= traffic */
  function makeCar(kind, color) {
    const g = new T.Group(), big = kind === "bus" || kind === "truck", L = kind === "bus" ? 10 : kind === "truck" ? 8 : 4.8, Wd = big ? 2.6 : 2.1;
    if (kind === "bus") { box(L, 2.6, Wd, color, 0, 0.6, 0, g); box(L - 0.6, 0.95, Wd + 0.06, "#1e2a38", 0, 1.85, 0, g); }
    else if (kind === "truck") { box(2.2, 2.3, 2.5, color, L / 2 - 1.1, 0.6, 0, g); box(5.4, 2.9, 2.6, "#f1f3f5", -1.3, 0.6, 0, g); }
    else {
      box(L, 1.0, Wd, color, 0, 0.45, 0, g); box(L * 0.5, 0.85, Wd * 0.88, "#1e2a38", -0.25, 1.45, 0, g);
      if (kind === "taxi") box(0.9, 0.35, 0.5, W.glow("#fff4d6", 1.5), -0.25, 2.3, 0, g);
      if (kind === "ambulance") { box(L * 0.52, 1.5, Wd, "#f6f8fa", -1.1, 1.45, 0, g); box(L + 0.02, 0.3, Wd + 0.04, "#e5484d", 0, 0.9, 0, g); box(0.5, 0.3, 1.2, W.glow("#3b9dff", 2.5), 0.2, 2.3, 0, g); }
      if (kind === "av") { cyl(0.4, 0.4, 0.35, "#1f2937", -0.25, 2.3, 0, g, 10); box(L + 0.04, 0.16, Wd + 0.06, W.glow("#37d5ff", 2), 0, 0.75, 0, g); }
    }
    const wx = L * 0.32;
    for (const a of [-1, 1]) for (const b of [-1, 1]) { const wh = mesh(new T.CylinderGeometry(0.52, 0.52, 0.4, 8), "#15181d", a * wx, 0.52, (b * Wd) / 2, g); wh.rotation.x = Math.PI / 2; }
    box(0.1, 0.3, Wd * 0.8, W.glow("#fffbe6", 1.6), L / 2 + 0.02, 0.8, 0, g); box(0.1, 0.25, Wd * 0.8, W.glow("#ff3b3b", 1.2), -L / 2 - 0.02, 0.85, 0, g);
    g.scale.setScalar(1.22);
    W.city.add(g);
    return g;
  }
  function ringPath(R, dir) {
    let c = [[-R, -R], [R, -R], [R, R], [-R, R]];
    if (dir < 0) c.reverse();
    const pts = c.map((p, i) => {
      const a = c[(i + 3) % 4], b = c[(i + 1) % 4];
      const d1 = [Math.sign(p[0] - a[0]), Math.sign(p[1] - a[1])], d2 = [Math.sign(b[0] - p[0]), Math.sign(b[1] - p[1])];
      /* traffic keeps left, as in India */
      return V(p[0] + (d1[1] + d2[1]) * LANE, 0.1, p[1] - (d1[0] + d2[0]) * LANE);
    });
    const lens = pts.map((p, i) => p.distanceTo(pts[(i + 1) % 4]));
    return { pts, lens, total: lens.reduce((a, b) => a + b, 0) };
  }
  function traffic() {
    const plan = [[150, 9], [90, 6], [30, 3]];
    plan.forEach(([R, n], ri) => {
      for (const dir of [1, -1]) {
        const path = ringPath(R, dir);
        for (let i = 0; i < n; i++) {
          let kind = "car", color = pick(PAL.cars);
          const hero = dir === 1 && i === 0;
          if (ri === 0 && hero) { kind = "car"; color = "#ffb224"; }
          else if (ri === 1 && hero) { kind = "av"; color = "#f6f8fa"; }
          else if (i === 1 && ri === 0) { kind = "bus"; color = dir > 0 ? "#e5484d" : "#3b82f6"; }
          else if (i === 2 && ri < 2) { kind = "truck"; }
          else if (i === 3 && ri === 1 && dir < 0) { kind = "ambulance"; color = "#f6f8fa"; }
          else if (rnd() < 0.2) { kind = "taxi"; color = "#f5c64a"; }
          const car = { obj: makeCar(kind, color), path, s: (i / n) * path.total + rr(-8, 8), v: 13 + ri * 1.5, kind };
          W.cars.push(car);
          if (ri === 0 && hero) W.hoCar = car.obj;
          if (ri === 1 && hero) W.avCar = car.obj;
          if (ri === 1) (W.ringB = W.ringB || []).push(car.obj);
          if (ri === 2) (W.ringC = W.ringC || []).push(car.obj);
        }
      }
    });
    W.updaters.push((t, dt) => {
      for (const c of W.cars) {
        c.s = (c.s + c.v * dt) % c.path.total;
        let s = c.s, i = 0;
        while (s > c.path.lens[i]) { s -= c.path.lens[i]; i++; }
        const a = c.path.pts[i], b = c.path.pts[(i + 1) % 4], o = c.obj;
        o.position.lerpVectors(a, b, s / c.path.lens[i]);
        const want = Math.atan2(-(b.z - a.z), b.x - a.x);
        let d = want - o.rotation.y; d = Math.atan2(Math.sin(d), Math.cos(d));
        o.rotation.y += d * Math.min(1, dt * 6);
      }
    });
  }

  function sky() {
    /* delivery drone circling the park */
    const dr = (W.drone = group(0, 34, 0));
    box(1.4, 0.5, 1.4, "#f6f8fa", 0, 0, 0, dr); box(1, 0.9, 1, "#b08968", 0, -1, 0, dr);
    const rot = [];
    for (const a of [-1, 1]) for (const b of [-1, 1]) { const arm = box(2.6, 0.14, 0.2, "#1f2937", a * 1.2, 0.2, b * 1.2, dr); arm.rotation.y = a * b * -0.78; rot.push(cyl(1, 1, 0.05, M("#cfd6dd", { transparent: true, opacity: 0.55 }), a * 2.1, 0.45, b * 2.1, dr, 10)); }
    ball(0.2, W.glow("#3ddc97", 3), 0, 0.6, 0, dr);
    dr.scale.setScalar(1.5);
    W.updaters.push((t) => { const a = t * 0.22; dr.position.set(20 + Math.cos(a) * 34, 34 + Math.sin(t * 1.3) * 0.8, Math.sin(a) * 34); dr.rotation.y = -a; rot.forEach((r) => (r.rotation.y = t * 30)); });
    /* low-earth-orbit satellite, drifting slowly overhead */
    const sat = (W.sat = group(230, 215, -150));
    box(4, 4, 6, M("#e7c66a", { metalness: 0.5, roughness: 0.35 }), 0, -2, 0, sat);
    for (const a of [-1, 1]) box(13, 0.2, 5, M("#22457a", { metalness: 0.4, roughness: 0.3 }), a * 9, 0, 0, sat);
    const sd = mesh(new T.ConeGeometry(2, 1.6, 12, 1, true), M("#f6f8fa", { side: T.DoubleSide }), 0, -3.4, 0, sat);
    W.updaters.push((t) => { sat.position.set(230 + Math.sin(t * 0.05) * 30, 215 + Math.sin(t * 0.3) * 2, -150 + Math.cos(t * 0.05) * 20); sat.rotation.y = t * 0.05; });
    place("sat", 230, 212, -150);
    /* clouds */
    const clouds = [];
    for (let i = 0; i < 9; i++) {
      const c = group(rr(-600, 600), rr(150, 230), rr(-600, 300));
      const m = M("#ffffff", { transparent: true, opacity: 0.92 });
      for (let k = 0; k < 4; k++) { const b = mesh(new T.IcosahedronGeometry(rr(12, 22), 1), m, k * 16 - 24 + rr(-4, 4), rr(-3, 3), rr(-6, 6), c); b.scale.y = 0.55; b.castShadow = false; b.receiveShadow = false; }
      clouds.push(c);
    }
    W.clouds = clouds;
    W.updaters.push((t, dt) => { for (const c of clouds) { c.position.x += dt * 4; if (c.position.x > 700) c.position.x = -700; } });
  }

  /* ================================================================= assemble */
  W.buildCity = function () {
    land();
    dataCentre(bx(0), bx(0)); museum(bx(1), bx(0)); towersBlock(bx(2), bx(0), 14, 34); hospital(bx(3), bx(0)); campus(bx(4), bx(0));
    factory(bx(0), bx(1)); bizBlock(bx(1), bx(1)); hqBlock(bx(2), bx(1)); towersBlock(bx(3), bx(1), 26, 62); stadium(bx(4), bx(1));
    logistics(bx(0), bx(2)); towersBlock(bx(1), bx(2), 12, 28); park(bx(2), bx(2)); mall(bx(3), bx(2)); towersBlock(bx(4), bx(2), 16, 30);
    housesBlock(bx(1), bx(3)); smartHome(bx(2), bx(3)); housesBlock(bx(2), bx(3), (a, b) => b === 0 || (a === 0)); housesBlock(bx(3), bx(3)); housesBlock(bx(4), bx(3));
    landing(bx(0), bx(4)); housesBlock(bx(1), bx(4)); towersBlock(bx(2), bx(4), 10, 20); housesBlock(bx(3), bx(4)); housesBlock(bx(4), bx(4));
    port(); farm(); hills(); beach();
    macroTower("easttower", 204 - 12, 0, 70, 32, 170);
    macroTower("westtower", -176, 0, -92, 32, 170);
    for (const p of [[-83.4, -37.4], [83.4, -37.4], [-37.4, -83.4], [37.4, -83.4], [-37.4, 83.4], [37.4, 83.4]]) smallCell(p[0], p[1]);
    place("smallcell", 22.6, 7, 22.6); place("street", 0, 1, 30); place("downtown", 0, 30, -60); place("houses", 60, 4, 60); place("av", 0, 2, 90); place("suburb", 0, 5, 110);
    traffic(); sky(); flush();

    /* remember every material so X-ray view can ghost the whole city and put it back */
    const seen = new Set();
    W.city.traverse((o) => { if (o.material) for (const m of [].concat(o.material)) seen.add(m); });
    W.cityMats = Array.from(seen).map((m) => ({ m, opacity: m.opacity, transparent: m.transparent, depthWrite: m.depthWrite }));
    let followLast = null;
    W.updaters.push(() => {
      if (!W.follow) { followLast = null; return; }
      const p = W.follow.position;
      if (followLast && !W.isFlying()) { const dx = p.x - followLast.x, dz = p.z - followLast.z; W.camera.position.x += dx; W.camera.position.z += dz; W.controls.target.x += dx; W.controls.target.z += dz; }
      followLast = (followLast || V(0, 0, 0)).copy(p);
    });
  };
  W.setXray = function (on) {
    if (!!W.xray === !!on) return;
    W.xray = !!on;
    for (const r of W.cityMats) { r.m.transparent = on ? true : r.transparent; r.m.opacity = on ? Math.min(r.opacity, 0.085) : r.opacity; r.m.depthWrite = on ? false : r.depthWrite; }
    W.sun.castShadow = !on && W.hd !== false;
    W.applyNight();
  };
})();
