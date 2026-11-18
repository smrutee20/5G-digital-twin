/* SetuCity: 3D engine.
   Renderer, lights, sky, camera flights, day/night, snapshots and the small geometry helpers
   the city builder (city.js) and the network effects (fx.js) are written with. */
(function () {
  "use strict";
  const T = THREE;
  const SC = (window.SC = window.SC || {});
  const W = (SC.W = { places: {}, updaters: [], winMats: [], glowMats: [], night: 0, w: 1, h: 1 });
  const V = (W.V = (x, y, z) => new T.Vector3(x, y, z));
  const lerp = (W.lerp = (a, b, k) => a + (b - a) * k);

  let renderer, scene, camera, controls, sun, hemi, sky, stars, clock, fly = null, nightTarget = 0;

  /* ---------- seeded random, so the city is the same every time */
  let seed = 20260518;
  const rnd = (W.rnd = () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  });
  W.rr = (a, b) => a + (b - a) * rnd();
  W.pick = (arr) => arr[Math.floor(rnd() * arr.length)];

  /* ---------- materials and mesh helpers */
  const matCache = {};
  const M = (W.M = function (color, opt) {
    const key = color + (opt ? JSON.stringify(opt) : "");
    return matCache[key] || (matCache[key] = new T.MeshStandardMaterial(Object.assign({ color, roughness: 0.82, metalness: 0.02, flatShading: true }, opt || {})));
  });
  /* A material that glows at night (lamps, signs, screens). */
  W.glow = function (color, base) {
    const key = "glow" + color + (base || 1);
    if (matCache[key]) return matCache[key];
    const m = new T.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.2, roughness: 0.5, flatShading: true });
    m.userData.base = base || 1;
    W.glowMats.push(m);
    return (matCache[key] = m);
  };
  W.basic = (color, opacity) => new T.MeshBasicMaterial({ color, transparent: opacity !== undefined && opacity < 1, opacity: opacity === undefined ? 1 : opacity, depthWrite: !(opacity < 1), toneMapped: false });

  const asMat = (c) => (c && c.isMaterial) || Array.isArray(c) ? c : M(c);
  const mesh = (W.mesh = function (geo, color, x, y, z, parent) {
    const m = new T.Mesh(geo, asMat(color));
    m.position.set(x || 0, y || 0, z || 0);
    m.castShadow = true;
    m.receiveShadow = true;
    (parent || W.city).add(m);
    return m;
  });
  /* y is always the base of the shape, not its centre. */
  W.box = (w, h, d, color, x, y, z, parent) => mesh(new T.BoxGeometry(w, h, d), color, x, (y || 0) + h / 2, z, parent);
  W.cyl = (rt, rb, h, color, x, y, z, parent, seg) => mesh(new T.CylinderGeometry(rt, rb, h, seg || 10), color, x, (y || 0) + h / 2, z, parent);
  W.ball = (r, color, x, y, z, parent, detail) => mesh(new T.IcosahedronGeometry(r, detail === undefined ? 1 : detail), color, x, y, z, parent);
  W.group = function (x, y, z, parent) {
    const g = new T.Group();
    g.position.set(x || 0, y || 0, z || 0);
    (parent || W.city).add(g);
    return g;
  };
  W.place = (name, x, y, z) => (W.places[name] = V(x, y, z));

  /* Text on a rounded plate that always faces the camera. */
  W.label = function (text, color, scale, parent) {
    const c = document.createElement("canvas"), g = c.getContext("2d"), fs = 44;
    g.font = "700 " + fs + "px Outfit, Inter, system-ui, sans-serif";
    const tw = Math.ceil(g.measureText(text).width) + 44;
    c.width = tw; c.height = 72;
    g.font = "700 " + fs + "px Outfit, Inter, system-ui, sans-serif";
    g.fillStyle = "rgba(10,16,32,.86)";
    const r = 20;
    g.beginPath(); g.moveTo(r, 2); g.arcTo(tw - 2, 2, tw - 2, 70, r); g.arcTo(tw - 2, 70, 2, 70, r); g.arcTo(2, 70, 2, 2, r); g.arcTo(2, 2, tw - 2, 2, r); g.closePath(); g.fill();
    g.lineWidth = 3; g.strokeStyle = color || "#37d5ff"; g.stroke();
    g.fillStyle = "#fff"; g.textBaseline = "middle"; g.textAlign = "center"; g.fillText(text, tw / 2, 38);
    const tex = new T.CanvasTexture(c); tex.encoding = T.sRGBEncoding;
    const s = new T.Sprite(new T.SpriteMaterial({ map: tex, depthTest: false, transparent: true, toneMapped: false }));
    const k = (scale || 1) * 0.085;
    s.scale.set(tw * k, 72 * k, 1);
    s.renderOrder = 20;
    if (parent) parent.add(s);
    return s;
  };

  /* ---------- start */
  W.init = function (canvas) {
    renderer = W.renderer = new T.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.toneMapping = T.NoToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;

    scene = W.scene = new T.Scene();
    scene.fog = new T.Fog(0xbfe6f5, 520, 1700);
    W.city = new T.Group();
    scene.add(W.city);

    camera = W.camera = new T.PerspectiveCamera(36, 1, 2, 5000);
    camera.position.set(250, 210, 330);
    controls = W.controls = new T.OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.475;
    controls.minDistance = 16;
    controls.maxDistance = 640;
    controls.screenSpacePanning = false;
    controls.zoomSpeed = 0.9;
    controls.rotateSpeed = 0.55;
    controls.autoRotateSpeed = 0.35;
    controls.target.set(0, 6, -10);

    hemi = new T.HemisphereLight(0xe4f4ff, 0x8f9a72, 0.6);
    scene.add(hemi);
    sun = W.sun = new T.DirectionalLight(0xfff0d2, 0.85);
    sun.position.set(-230, 330, 190);
    sun.castShadow = true;
    sun.shadow.mapSize.set(4096, 4096);
    const sc = sun.shadow.camera;
    sc.left = -310; sc.right = 310; sc.top = 310; sc.bottom = -310; sc.near = 60; sc.far = 950;
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.7;
    scene.add(sun);

    /* sky dome with a vertical gradient */
    sky = new T.Mesh(
      new T.SphereGeometry(2600, 24, 14),
      new T.ShaderMaterial({
        side: T.BackSide, depthWrite: false, fog: false,
        uniforms: { top: { value: new T.Color(0x3d8fe0) }, bottom: { value: new T.Color(0xcdeefa) } },
        vertexShader: "varying float h; void main(){ h = normalize(position).y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
        fragmentShader: "uniform vec3 top; uniform vec3 bottom; varying float h; void main(){ float k = pow(clamp(h*1.25+0.04,0.0,1.0),0.55); gl_FragColor = vec4(mix(bottom, top, k),1.0); }",
      })
    );
    scene.add(sky);

    const sp = [];
    for (let i = 0; i < 700; i++) {
      const a = rnd() * Math.PI * 2, e = Math.asin(rnd() * 0.95 + 0.04), r = 2300;
      sp.push(Math.cos(a) * Math.cos(e) * r, Math.sin(e) * r, Math.sin(a) * Math.cos(e) * r);
    }
    const sg = new T.BufferGeometry();
    sg.setAttribute("position", new T.Float32BufferAttribute(sp, 3));
    stars = new T.Points(sg, new T.PointsMaterial({ color: 0xffffff, size: 2.2, sizeAttenuation: false, transparent: true, opacity: 0, fog: false, depthWrite: false }));
    scene.add(stars);

    clock = new T.Clock();
    W.resize();
    window.addEventListener("resize", W.resize);
    controls.addEventListener("start", () => { if (W.onUserMove) W.onUserMove(); });
  };

  W.resize = function () {
    W.w = window.innerWidth; W.h = window.innerHeight;
    renderer.setPixelRatio(W.hd === false ? 1 : Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W.w, W.h, false);
    camera.aspect = W.w / W.h;
    /* keep the same horizontal coverage on tall, narrow screens */
    camera.fov = camera.aspect < 1 ? 52 : 36;
    camera.updateProjectionMatrix();
  };

  W.setQuality = function (hd) {
    W.hd = hd;
    sun.castShadow = hd;
    W.resize();
  };

  /* ---------- day / night */
  const C = (h) => new T.Color(h);
  const DAY = { top: C(0x3d8fe0), bottom: C(0xcdeefa), fog: C(0xbfe6f5), sun: C(0xfff0d2), hemi: C(0xe4f4ff), ground: C(0x8f9a72) };
  const NIGHT = { top: C(0x050a1c), bottom: C(0x1b2a55), fog: C(0x141d3c), sun: C(0x8fa8ff), hemi: C(0x5a6cb0), ground: C(0x1a2035) };
  function applyNight() {
    const n = W.night, u = sky.material.uniforms;
    u.top.value.copy(DAY.top).lerp(NIGHT.top, n);
    u.bottom.value.copy(DAY.bottom).lerp(NIGHT.bottom, n);
    scene.fog.color.copy(DAY.fog).lerp(NIGHT.fog, n);
    sun.color.copy(DAY.sun).lerp(NIGHT.sun, n);
    sun.intensity = lerp(0.85, 0.2, n);
    hemi.color.copy(DAY.hemi).lerp(NIGHT.hemi, n);
    hemi.groundColor.copy(DAY.ground).lerp(NIGHT.ground, n);
    hemi.intensity = lerp(0.6, 0.34, n);
    stars.material.opacity = n;
    for (const m of W.winMats) m.emissiveIntensity = 0.015 + n * 1.25;
    for (const m of W.glowMats) m.emissiveIntensity = m.userData.base * (0.18 + n * 1.1);
    if (W.xray) { u.top.value.set(0x0b0d12); u.bottom.value.set(0x1d2129); scene.fog.color.set(0x15181e); stars.material.opacity = 0; }
  }
  W.applyNight = applyNight;
  W.setNight = function (on, instant) {
    nightTarget = on ? 1 : 0;
    if (instant) { W.night = nightTarget; applyNight(); }
  };

  /* ---------- camera */
  /* spec: { at: "place" | [x,y,z], d: distance, az: degrees (0 = camera south of the target), el: degrees, dy: lift the target } */
  W.resolveCam = function (spec) {
    const p = typeof spec.at === "string" ? W.places[spec.at] : V(spec.at[0], spec.at[1], spec.at[2]);
    if (!p) throw new Error("unknown place " + spec.at);
    const target = p.clone();
    target.y += spec.dy || 0;
    const az = ((spec.az || 0) * Math.PI) / 180, el = ((spec.el === undefined ? 30 : spec.el) * Math.PI) / 180;
    /* portrait screens see less sideways, so stand further back */
    const d = (spec.d || 100) * (camera.aspect < 1 ? 1.45 : 1);
    const pos = V(target.x + d * Math.sin(az) * Math.cos(el), target.y + d * Math.sin(el), target.z + d * Math.cos(az) * Math.cos(el));
    return { pos, target };
  };
  W.flyTo = function (spec, dur, done) {
    const r = W.resolveCam(spec);
    fly = { p0: camera.position.clone(), t0: controls.target.clone(), p1: r.pos, t1: r.target, k: 0, dur: dur === undefined ? 1.7 : dur, done };
    if (fly.dur <= 0) { fly.k = 1; stepFly(0); }
  };
  function stepFly(dt) {
    fly.k = Math.min(1, fly.k + (fly.dur > 0 ? dt / fly.dur : 1));
    const k = fly.k, e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    camera.position.lerpVectors(fly.p0, fly.p1, e);
    camera.position.y += Math.sin(Math.PI * e) * Math.min(60, fly.p0.distanceTo(fly.p1) * 0.12);
    controls.target.lerpVectors(fly.t0, fly.t1, e);
    if (k >= 1) { const d = fly.done; fly = null; if (d) d(); }
  }
  W.isFlying = () => !!fly;
  W.setAutoRotate = (on) => { controls.autoRotate = on; };
  W.setZoom = function (k) {
    /* k: 0 = far, 1 = close */
    const d = lerp(controls.maxDistance * 0.9, 40, k), dir = camera.position.clone().sub(controls.target).normalize();
    camera.position.copy(controls.target).addScaledVector(dir, d);
  };
  W.getZoom = () => {
    const d = camera.position.distanceTo(controls.target);
    return Math.max(0, Math.min(1, (controls.maxDistance * 0.9 - d) / (controls.maxDistance * 0.9 - 40)));
  };

  const pv = new T.Vector3();
  W.project = function (p, out) {
    pv.copy(p).project(camera);
    out.x = (pv.x * 0.5 + 0.5) * W.w;
    out.y = (-pv.y * 0.5 + 0.5) * W.h;
    out.vis = pv.z > -1 && pv.z < 1;
    return out;
  };

  /* Render the city from another viewpoint into a small image (lesson thumbnails). */
  W.snapshot = function (spec, w, h) {
    w = w || 320; h = h || 180;
    /* thumbnails and info cards ask for different sizes: the target must match, or the read-back comes out black */
    const rt = W._rt || (W._rt = new T.WebGLRenderTarget(w, h));
    if (rt.width !== w || rt.height !== h) rt.setSize(w, h);
    rt.texture.encoding = T.sRGBEncoding;
    const cam = W._cam2 || (W._cam2 = new T.PerspectiveCamera(36, w / h, 2, 5000));
    if (cam.aspect !== w / h) { cam.aspect = w / h; cam.updateProjectionMatrix(); }
    const r = W.resolveCam(Object.assign({}, spec, { d: (spec.d || 100) / (camera.aspect < 1 ? 1.45 : 1) }));
    cam.position.copy(r.pos); cam.lookAt(r.target); cam.updateMatrixWorld();
    const auto = renderer.shadowMap.autoUpdate;
    renderer.shadowMap.autoUpdate = false;
    renderer.setRenderTarget(rt);
    renderer.render(scene, cam);
    const buf = new Uint8Array(w * h * 4);
    renderer.readRenderTargetPixels(rt, 0, 0, w, h, buf);
    renderer.setRenderTarget(null);
    renderer.shadowMap.autoUpdate = auto;
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const g = c.getContext("2d"), img = g.createImageData(w, h);
    for (let y = 0; y < h; y++) img.data.set(buf.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);
    g.putImageData(img, 0, 0);
    return c.toDataURL("image/jpeg", 0.82);
  };

  /* ---------- frame loop */
  W.start = function () {
    applyNight();
    (function frame() {
      requestAnimationFrame(frame);
      const raw = clock.getDelta(), dt = Math.min(raw, 0.05), t = clock.elapsedTime;
      if (W.night !== nightTarget) {
        W.night += Math.sign(nightTarget - W.night) * Math.min(Math.abs(nightTarget - W.night), dt * 0.9);
        applyNight();
      }
      if (fly) stepFly(Math.min(raw, 0.4)); /* flights keep real time even when frames are slow */
      controls.enabled = !fly && !W.locked;
      controls.update();
      const tg = controls.target;
      tg.x = Math.max(-240, Math.min(240, tg.x)); tg.z = Math.max(-270, Math.min(240, tg.z)); tg.y = Math.max(0, Math.min(260, tg.y));
      for (let i = 0; i < W.updaters.length; i++) W.updaters[i](t, dt);
      renderer.render(scene, camera);
      if (W.onFrame) W.onFrame(t, dt);
    })();
  };
})();
