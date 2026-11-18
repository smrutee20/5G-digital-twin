/* SetuCity: the app.
   Views: splash, learn (path circles), path (lesson timeline), explore (free roam), quiz.
   A "story" (a lesson, a use case or a concept) can play on top of learn or explore: it steps through slides,
   and each slide moves the camera and switches on effects, cutaways, X-ray and labels. */
(function () {
  "use strict";
  const SC = window.SC, W = SC.W;
  const $ = (s) => document.querySelector(s);
  const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const ic = (d, extra) => '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">' + d + (extra || "") + "</svg>";
  const I = {
    check: ic('<path d="M5 12.5l4.5 4.5L19 7.5"/>'), lock: ic('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
    cap: ic('<path d="M2 9l10-5 10 5-10 5zM6 11.5V16c0 1.5 3 3 6 3s6-1.5 6-3v-4.5"/>'), play: ic('<path d="M7 5l12 7-12 7z"/>'),
    pin: ic('<path d="M12 21s7-6.2 7-11.5a7 7 0 1 0-14 0C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.4"/>'), cam: ic('<rect x="3" y="7" width="12" height="10" rx="2"/><path d="M15 11l6-3v8l-6-3z"/>'),
    x: ic('<path d="M6 6l12 12M18 6L6 18"/>'), left: ic('<path d="M15 5l-7 7 7 7"/>'), right: ic('<path d="M9 5l7 7-7 7"/>'), up: ic('<path d="M6 15l6-6 6 6"/>'), down: ic('<path d="M6 9l6 6 6-6"/>'),
    caret: ic('<path d="M7 10l5 5 5-5"/>'), compass: ic('<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>'), help: ic('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7M12 17h.01"/>'),
    sound: ic('<path d="M4 9v6h4l5 4V5L8 9zM16.5 8.5a5 5 0 0 1 0 7"/>'), moon: ic('<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>'), bolt: ic('<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>'),
    unlock: ic('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>'), reset: ic('<path d="M4 12a8 8 0 1 0 2.6-5.9M4 4v5h5"/>'), ext: ic('<path d="M14 5h5v5M19 5l-8 8M11 7H6v11h11v-5"/>'),
  };
  const KIND = { usecase: { name: "Use case", c: "#ffb224", icon: I.pin }, concept: { name: "Concept", c: "#37d5ff", icon: I.cam }, info: { name: "Info", c: "#ffffff", icon: "<span>i</span>" } };

  /* ---------- saved progress */
  const KEY = "setucity.v1", OLD_KEY = "signalcity.v1";
  let save = { done: {}, quiz: {}, seen: {}, sound: false, hd: true, unlocked: false };
  try { Object.assign(save, JSON.parse(localStorage.getItem(KEY) || localStorage.getItem(OLD_KEY) || "{}")); } catch (e) {}
  const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(save)); } catch (e) {} };

  const st = { view: "splash", path: null, story: null, idx: 0, card: null, layers: {}, show: { usecase: true, concept: true, info: true }, night: false, from: "learn" };
  const body = document.body;
  const pathById = (id) => SC.PATHS.find((p) => p.id === id);
  const lessonInfo = (p, i) => { const l = p.lessons[i], sc = l.scene ? SC.SCENES[l.scene] : null; return { title: l.title || sc.title, slides: sc ? sc.slides : l.slides, pins: sc ? sc.pins : null, kind: sc ? sc.kind : "lesson" }; };
  const lessonMins = (p, i) => Math.max(2, Math.round(lessonInfo(p, i).slides.length * 1.3));
  const pathMins = (p) => p.lessons.reduce((a, l, i) => a + lessonMins(p, i), 3);
  const lessonDone = (p, i) => !!save.done[p.id + ":" + i];
  const pathPct = (p) => { const n = p.lessons.filter((l, i) => lessonDone(p, i)).length + (save.quiz[p.id] >= 0.7 ? 1 : 0); return Math.round((n / (p.lessons.length + 1)) * 100); };
  const unlocked = (p, i) => save.unlocked || i === 0 || lessonDone(p, i - 1);

  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 2400); }

  /* ================================================================= world state follows app state */
  function syncWorld(flyDur) {
    const s = st.story ? st.story.slides[st.idx] : null, c = st.card;
    let fx = [], xray = false, cuts = [];
    if (s) { fx = s.fx || []; xray = !!s.xray; cuts = s.cut || []; }
    else if (st.view === "explore") { fx = Object.keys(st.layers).filter((k) => st.layers[k] && k !== "xray"); xray = !!st.layers.xray; if (c && c.fx) fx = fx.concat(c.fx); }
    W.setCuts(cuts); W.setXray(xray); W.setFx(fx);
    W.follow = null;
    if (s) {
      let spec = s.cam;
      const obj = s.follow ? W.objs[s.follow] : null;
      if (obj) spec = Object.assign({}, s.cam, { at: [obj.position.x, s.cam.dy || 2, obj.position.z], dy: 0 });
      W.flyTo(spec, flyDur === undefined ? 1.8 : flyDur, () => { if (obj && st.story && st.story.slides[st.idx] === s) W.follow = obj; });
    }
    const idle = st.view === "splash" || st.view === "learn" || st.view === "path" || st.view === "quiz";
    W.locked = idle; W.setAutoRotate(idle);
    buildPins();
  }

  /* ================================================================= pins, labels, hover tips */
  let pins = [], tip = null;
  const tv = new THREE.Vector3(), sp = { x: 0, y: 0, vis: false };
  function target(t, dy) {
    const o = W.objs && W.objs[t];
    if (o) o.getWorldPosition(tv); else if (W.places[t]) tv.copy(W.places[t]); else tv.set(0, 0, 0);
    tv.y += dy || 0;
    return tv;
  }
  function buildPins() {
    const root = $("#pins"); root.textContent = ""; pins = []; tip = null;
    const addPin = (cls, html, t, dy, color, label, onClick, tipData) => {
      const b = h("button", cls, html); b.style.setProperty("--c", color); b.setAttribute("aria-label", label);
      b.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
      if (tipData) { const show = () => showTip(tipData, b); b.addEventListener("pointerenter", show); b.addEventListener("focus", show); b.addEventListener("pointerleave", hideTip); b.addEventListener("blur", hideTip); }
      root.appendChild(b); pins.push({ el: b, t, dy });
    };
    if (st.story) {
      const s = st.story.slides[st.idx];
      (st.story.pins || []).forEach((p, i) => addPin("pin inner" + (save.seen[st.story.id + "#" + i] ? " seen" : ""), "<span>i</span>", p.at, p.dy || 1.5, "#fff", p.h, () => openCard({ h: p.h, t: p.t, art: p.art, snap: { at: p.at, d: p.d || 20, az: 35, el: 24 }, key: st.story.id + "#" + i })));
      (s.labels || []).forEach((l) => { const e = h("div", "tag", esc(l[1])); e.style.setProperty("--c", l[2] || "#37d5ff"); root.appendChild(e); pins.push({ el: e, t: l[0], dy: W.objs[l[0]] ? 6 : 2.5 }); });
    } else if (st.view === "explore" && !st.card) {
      for (const id in SC.SCENES) {
        const sc = SC.SCENES[id]; if (sc.noPin || !st.show[sc.kind]) continue;
        const k = KIND[sc.kind];
        addPin("pin" + (save.seen[id] ? " seen" : ""), k.icon, sc.place, sc.dy || 8, k.c, k.name + ": " + sc.title, () => play(sceneStory(id)), { kind: k.name, c: k.c, title: sc.title, text: sc.blurb });
      }
      if (st.show.info) SC.INFO.forEach((f) => addPin("pin" + (save.seen[f.id] ? " seen" : ""), "<span>i</span>", f.place, f.dy || 6, "#ffffff", f.h, () => openInfo(f), { kind: "Info", c: "#cfd8ea", title: f.h, text: f.t.split(". ")[0] + "." }));
    }
    renderViewer();
  }
  function showTip(d, anchor) {
    hideTip();
    tip = h("div", "tip glass", "<small>" + esc(d.kind) + "</small><b>" + esc(d.title) + "</b><span>" + esc(d.text) + "</span>");
    tip.style.setProperty("--c", d.c); tip.anchor = anchor; $("#pins").appendChild(tip);
  }
  function hideTip() { if (tip) { tip.remove(); tip = null; } }
  function placePins() {
    for (const p of pins) {
      W.project(target(p.t, p.dy), sp);
      const on = sp.vis && sp.x > -40 && sp.x < W.w + 40 && sp.y > 40 && sp.y < W.h + 40;
      p.el.style.display = on ? "" : "none";
      if (on) { p.el.style.translate = sp.x.toFixed(1) + "px " + sp.y.toFixed(1) + "px"; p.x = sp.x; p.y = sp.y; }
    }
    if (tip) {
      const a = pins.find((p) => p.el === tip.anchor);
      if (a) { const x = Math.min(W.w - 280, Math.max(8, a.x + 22)), y = Math.min(W.h - 150, Math.max(64, a.y - 40)); tip.style.translate = x + "px " + y + "px"; }
    }
    const zr = $("#zr"); if (document.activeElement !== zr && !zr.dragging) zr.value = Math.round(W.getZoom() * 100);
  }

  /* ---------- hotspot viewer (bottom right) */
  function renderViewer() {
    const v = $("#viewer");
    const show = st.story ? !!st.story.pins : st.view === "explore";
    v.hidden = !show; if (!show) return;
    v.textContent = "";
    v.appendChild(h("span", "", "Hotspot viewer:"));
    if (st.story) {
      const n = st.story.pins.length, seen = st.story.pins.filter((p, i) => save.seen[st.story.id + "#" + i]).length;
      const k = h("span", "k", "<i><span style='font:800 .7rem var(--display)'>i</span></i>" + seen + "/" + n); k.style.setProperty("--c", "#fff"); v.appendChild(k);
    } else {
      const counts = { usecase: [0, 0], concept: [0, 0], info: [SC.INFO.filter((f) => save.seen[f.id]).length, SC.INFO.length] };
      for (const id in SC.SCENES) { const sc = SC.SCENES[id]; if (sc.noPin) continue; counts[sc.kind][1]++; if (save.seen[id]) counts[sc.kind][0]++; }
      for (const kind of ["usecase", "concept", "info"]) {
        const k = h("button", "k" + (st.show[kind] ? "" : " off"), "<i>" + (kind === "info" ? "<span style='font:800 .7rem var(--display)'>i</span>" : KIND[kind].icon) + "</i>" + counts[kind][0] + "/" + counts[kind][1]);
        k.style.setProperty("--c", KIND[kind].c); k.title = "Show or hide " + KIND[kind].name.toLowerCase() + " markers"; k.setAttribute("aria-pressed", st.show[kind]);
        k.onclick = () => { st.show[kind] = !st.show[kind]; buildPins(); };
        v.appendChild(k);
      }
      v.appendChild(h("span", "sep"));
      const all = h("button", "k", "Toggle all"); all.id = "toggleAll";
      all.onclick = () => { const any = st.show.usecase || st.show.concept || st.show.info; st.show = { usecase: !any, concept: !any, info: !any }; buildPins(); };
      v.appendChild(all);
    }
    const q = h("button", "k", I.help); q.setAttribute("aria-label", "Help"); q.onclick = openHelp; v.appendChild(q);
  }

  /* ================================================================= info card */
  function openCard(d) {
    st.card = d; if (d.key) { save.seen[d.key] = true; persist(); }
    const c = $("#card");
    let pic = "";
    if (d.art && SC.ART[d.art]) pic = '<div class="pic">' + SC.ART[d.art] + "</div>";
    else if (d.snap) { try { pic = '<div class="pic"><img alt="" src="' + W.snapshot(d.snap, 480, 250) + '"></div>'; } catch (e) {} }
    c.innerHTML = '<div class="hd"><span class="badge">i</span><button class="ibtn" id="cspeak" aria-label="Read aloud" title="Read aloud">' + I.sound + '</button><button class="ibtn" id="cclose" aria-label="Close">' + I.x + "</button></div><h3>" + esc(d.h) + "</h3><p>" + esc(d.t) + "</p>" + pic;
    c.hidden = false; c.scrollTop = 0;
    $("#cclose").onclick = closeCard; $("#cspeak").onclick = () => speak(d.h + ". " + d.t, true);
    if (save.sound) speak(d.h + ". " + d.t);
    if (st.story) { buildPins(); } else { syncWorld(); render(); }
  }
  function closeCard() { if (!st.card) return; st.card = null; $("#card").hidden = true; stopSpeak(); if (st.story) buildPins(); else { syncWorld(); render(); } }
  function openInfo(f) { W.flyTo(f.cam, 1.6); openCard({ h: f.h, t: f.t, art: f.art, snap: f.art ? null : Object.assign({}, f.cam, { d: f.cam.d * 0.7 }), key: f.id, fx: f.fx }); }

  /* ================================================================= stories */
  function sceneStory(id) { const sc = SC.SCENES[id]; return { id, kind: sc.kind, title: sc.title, slides: sc.slides, pins: sc.pins, label: KIND[sc.kind].name }; }
  function lessonStory(p, i) { const l = lessonInfo(p, i); return { id: p.lessons[i].scene || p.id + ":" + i, kind: "lesson", title: l.title, slides: l.slides, pins: l.pins, label: "Lesson " + (i + 1) + " of " + p.lessons.length, path: p, li: i }; }
  function play(story, at) {
    st.from = st.view; st.story = story; st.idx = at || 0; st.card = null; $("#card").hidden = true;
    if (story.kind !== "lesson") st.view = "explore";
    else st.view = "lesson";
    render(); syncWorld(); narrate();
  }
  function step(d) {
    const n = st.story.slides.length, i = st.idx + d;
    if (i < 0) return;
    if (i >= n) return finish();
    st.idx = i; st.card = null; $("#card").hidden = true;
    renderStory(); syncWorld(); narrate();
  }
  function finish() {
    const s = st.story; stopSpeak();
    st.story = null; st.card = null; $("#card").hidden = true;
    if (s.kind === "lesson") {
      const first = !lessonDone(s.path, s.li);
      save.done[s.path.id + ":" + s.li] = true; persist();
      if (first) toast("Lesson complete");
      st.view = "path"; st.path = s.path;
    } else { save.seen[s.id] = true; persist(); st.view = "explore"; }
    render(); syncWorld();
    if (st.view === "explore") W.flyTo(SC.OVERVIEW, 2);
  }
  function leaveStory() {
    const s = st.story; stopSpeak(); st.story = null; st.card = null; $("#card").hidden = true;
    if (s && s.kind === "lesson") { st.view = "path"; st.path = s.path; } else st.view = "explore";
    render(); syncWorld();
    if (st.view === "explore") W.flyTo(SC.OVERVIEW, 2);
  }
  function renderStory() {
    const s = st.story, sl = s.slides[st.idx], n = s.slides.length, box = $("#story");
    box.querySelector("h3").textContent = sl.h; box.querySelector("p").textContent = sl.t;
    const art = box.querySelector(".art"); art.innerHTML = sl.art && SC.ART[sl.art] ? SC.ART[sl.art] : ""; art.hidden = !art.innerHTML;
    box.querySelector(".count").textContent = st.idx + 1 + "/" + n;
    box.querySelector(".bar i").style.width = ((st.idx + 1) / n) * 100 + "%";
    $("#prev").disabled = st.idx === 0;
    const last = st.idx === n - 1;
    $("#next").hidden = last; $("#finish").hidden = !last;
    $("#finish").textContent = s.kind === "lesson" ? "Finish lesson" : "Done";
    $("#speak").classList.toggle("on", !!save.sound);
    const chip = $("#chip");
    chip.innerHTML = "<small>" + esc(s.label) + "</small><b>" + esc(s.title) + "</b>";
  }

  /* ---------- narration (the browser's own text-to-speech) */
  function speak(text, force) {
    if (!("speechSynthesis" in window) || (!save.sound && !force)) return;
    try { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.rate = 1; speechSynthesis.speak(u); } catch (e) {}
  }
  function stopSpeak() { try { if ("speechSynthesis" in window) speechSynthesis.cancel(); } catch (e) {} }
  function narrate() { if (st.story) { const s = st.story.slides[st.idx]; speak(s.h + ". " + s.t); } }

  /* ================================================================= study mode */
  function renderLearn() {
    const root = $("#paths"); root.textContent = "";
    const desc = $("#pdesc"), base = "<b>Hover over a path</b>to see what it covers. Your progress is saved in this browser.";
    desc.innerHTML = base;
    SC.PATHS.forEach((p) => {
      const pct = pathPct(p);
      const b = h("button", "pcircle", "<b>" + esc(p.title) + "</b><small>" + pathMins(p) + " mins</small>" + (pct === 100 ? '<span class="done">' + I.check + "</span>" : ""));
      b.style.setProperty("--p", pct); b.style.setProperty("--c", p.color);
      b.setAttribute("aria-label", p.title + ", " + pathMins(p) + " minutes, " + pct + " percent complete");
      const on = () => { desc.innerHTML = "<b>" + esc(p.title) + " · " + pct + "% complete</b>" + esc(p.blurb); };
      b.addEventListener("pointerenter", on); b.addEventListener("focus", on);
      b.addEventListener("pointerleave", () => (desc.innerHTML = base));
      b.onclick = () => openPath(p);
      root.appendChild(b);
    });
  }
  const thumbs = {};
  function openPath(p) { st.view = "path"; st.path = p; st.story = null; render(); syncWorld(); }
  function renderPath() {
    const p = st.path, track = $("#track"); track.textContent = ""; track.style.setProperty("--c", p.color);
    $("#phead p").textContent = p.blurb;
    let firstOpen = null;
    p.lessons.forEach((l, i) => {
      const info = lessonInfo(p, i), done = lessonDone(p, i), open = unlocked(p, i);
      const w = h("div", "lesson" + (done ? " done" : "") + (open ? "" : " locked"));
      const card = h("button", "lcard", '<div class="ph"></div><span>' + esc(info.title) + "<small>" + lessonMins(p, i) + " min · " + info.slides.length + " steps</small></span>");
      card.setAttribute("aria-label", info.title + (done ? ", completed" : open ? "" : ", locked"));
      card.onclick = () => { if (open) play(lessonStory(p, i)); else toast("Finish the previous lesson to unlock this one"); };
      w.appendChild(card); w.appendChild(h("div", "stem")); w.appendChild(h("div", "node", done ? I.check : open ? I.play : I.lock));
      track.appendChild(w);
      if (!done && open && !firstOpen) firstOpen = w;
      /* thumbnails are rendered from the 3D scene itself, a few at a time so the page stays responsive */
      const key = p.id + ":" + i, put = (src) => { const im = new Image(); im.alt = ""; im.src = src; card.replaceChild(im, card.firstChild); };
      if (thumbs[key]) put(thumbs[key]);
      else setTimeout(() => { if (st.view !== "path" || st.path !== p) return; try { const s0 = info.slides[0]; W.setCuts(s0.cut || []); thumbs[key] = W.snapshot(s0.cam, 336, 210); W.setCuts([]); put(thumbs[key]); } catch (e) {} }, 60 + i * 90);
    });
    const allDone = p.lessons.every((l, i) => lessonDone(p, i)), passed = save.quiz[p.id] >= 0.7, qOpen = allDone || save.unlocked;
    const q = h("div", "lesson quiz" + (passed ? " done" : "") + (qOpen ? "" : " locked"));
    const qc = h("button", "lcard", "<div>Path quiz" + (save.quiz[p.id] !== undefined ? "<small style='color:#aab6cc'>Best " + Math.round(save.quiz[p.id] * 100) + "%</small>" : "") + "</div>");
    qc.onclick = () => { if (qOpen) startQuiz(p); else toast("Complete every lesson to unlock the quiz"); };
    q.appendChild(qc); q.appendChild(h("div", "stem")); q.appendChild(h("div", "node", passed ? I.check : qOpen ? I.cap : I.lock));
    track.appendChild(q);
    $("#pbar i").style.width = pathPct(p) + "%";
    const focus = firstOpen || (allDone && !passed ? q : null);
    if (focus) requestAnimationFrame(() => focus.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" }));
  }

  /* ================================================================= quiz */
  let qz = null;
  function startQuiz(p) { qz = { p, i: 0, right: 0 }; st.view = "quiz"; st.story = null; render(); syncWorld(); renderQ(); }
  function renderQ() {
    const p = qz.p, q = p.quiz[qz.i], b = $("#qbody"); b.textContent = "";
    $("#quiz .qtop b").textContent = p.title + " quiz"; $("#quiz .qtop span").textContent = "Question " + (qz.i + 1) + " of " + p.quiz.length;
    b.appendChild(h("h3", "", esc(q.q)));
    let check;
    if (q.type === "order") {
      /* fixed shuffle so nobody is handed the right order */
      let order = q.items.map((t, i) => i); const n = order.length; order = order.map((v, i) => order[(i * 2 + 1 + (n % 2 ? 0 : 1)) % n]); if (order.every((v, i) => v === i)) order.reverse();
      const list = h("div", "order"); b.appendChild(list);
      let picked = null, locked = false;
      const draw = () => {
        list.textContent = "";
        order.forEach((v, pos) => {
          const o = h("div", "opt" + (picked === pos ? " sel" : ""), "<i>" + (pos + 1) + "</i><span>" + esc(q.items[v]) + '</span><span class="mv"><button aria-label="Move up">' + I.up + '</button><button aria-label="Move down">' + I.down + "</button></span>");
          o.tabIndex = 0; o.draggable = !locked;
          if (locked) o.classList.add(v === pos ? "right" : "wrong");
          const move = (to) => { if (locked || to < 0 || to >= order.length) return; const x = order.splice(pos, 1)[0]; order.splice(to, 0, x); picked = null; draw(); };
          const [upB, dnB] = o.querySelectorAll(".mv button");
          upB.onclick = (e) => { e.stopPropagation(); move(pos - 1); }; dnB.onclick = (e) => { e.stopPropagation(); move(pos + 1); };
          o.onclick = () => { if (locked) return; if (picked === null) picked = pos; else if (picked === pos) picked = null; else { const x = order[picked]; order[picked] = order[pos]; order[pos] = x; picked = null; } draw(); };
          o.ondragstart = (e) => { picked = null; e.dataTransfer.setData("text/plain", pos); o.classList.add("drag"); };
          o.ondragend = () => o.classList.remove("drag");
          o.ondragover = (e) => e.preventDefault();
          o.ondrop = (e) => { e.preventDefault(); const from = +e.dataTransfer.getData("text/plain"); if (isNaN(from) || from === pos || locked) return; const x = order.splice(from, 1)[0]; order.splice(pos, 0, x); draw(); };
          list.appendChild(o);
        });
      };
      draw();
      b.appendChild(h("div", "qhint", "Drag items into the correct order, or tap two to swap them."));
      check = () => { locked = true; picked = null; draw(); return order.every((v, i) => v === i); };
    } else {
      const list = h("div", "opts"); b.appendChild(list);
      let sel = -1;
      const btns = q.options.map((t, i) => { const o = h("button", "opt", "<i>" + "ABCD"[i] + "</i><span>" + esc(t) + "</span>"); o.onclick = () => { sel = i; btns.forEach((x, k) => x.classList.toggle("sel", k === i)); sub.disabled = false; }; list.appendChild(o); return o; });
      check = () => { btns.forEach((x, k) => { x.disabled = true; x.classList.remove("sel"); if (k === q.answer) x.classList.add("right"); else if (k === sel) x.classList.add("wrong"); }); return sel === q.answer; };
    }
    const sub = h("button", "btn pri", "Submit"); sub.disabled = q.type !== "order"; b.appendChild(sub);
    sub.onclick = () => {
      const ok = check(); if (ok) qz.right++;
      const why = h("div", "why glass", "<b style='color:" + (ok ? "var(--green)" : "var(--pink)") + "'>" + (ok ? "Correct. " : "Not quite. ") + "</b>" + esc(q.why)); why.setAttribute("role", "status");
      const nx = h("button", "btn pri", qz.i === p.quiz.length - 1 ? "See result" : "Next question");
      nx.onclick = () => { qz.i++; if (qz.i >= p.quiz.length) endQuiz(); else renderQ(); };
      sub.replaceWith(why); b.appendChild(nx); nx.focus();
      const hint = b.querySelector(".qhint"); if (hint) hint.remove();
    };
  }
  function endQuiz() {
    const p = qz.p, score = qz.right / p.quiz.length, pass = score >= 0.7, b = $("#qbody");
    save.quiz[p.id] = Math.max(save.quiz[p.id] || 0, score); persist();
    b.innerHTML = '<div class="score">' + qz.right + "/" + p.quiz.length + "</div><h3>" + (pass ? "Path complete. Well done." : "Close. You need 70% to complete the path.") + '</h3><div class="cta"></div>';
    const cta = b.querySelector(".cta");
    if (!pass) { const r = h("button", "btn pri", "Try again"); r.onclick = () => startQuiz(p); cta.appendChild(r); }
    const back = h("button", "btn" + (pass ? " pri" : ""), "Back to the path"); back.onclick = () => openPath(p); cta.appendChild(back);
    const all = h("button", "btn", "All paths"); all.onclick = () => go("learn"); cta.appendChild(all);
  }

  /* ================================================================= chrome */
  function go(view) {
    stopSpeak(); st.story = null; st.card = null; $("#card").hidden = true; st.view = view;
    render(); syncWorld();
    if (view === "explore") { W.flyTo(SC.OVERVIEW, 2.2); const hint = $("#hint"); hint.hidden = false; hint.style.opacity = 1; clearTimeout(go.t); go.t = setTimeout(() => (hint.style.opacity = 0), 5200); }
  }
  function render() {
    const v = st.view, story = !!st.story;
    body.dataset.view = v; body.classList.toggle("instory", story);
    $("#splash").hidden = v !== "splash"; $("#learn").hidden = v !== "learn"; $("#path").hidden = v !== "path"; $("#quiz").hidden = v !== "quiz";
    $("#story").hidden = !story; $("#chip").hidden = !story;
    const free = v === "explore" || v === "lesson";
    $("#zoom").hidden = !free; $("#dock").hidden = !free; $("#layerBtn").hidden = v !== "explore" || story;
    if (v !== "explore" || story) { $("#layers").hidden = true; }
    if (v !== "explore") $("#hint").hidden = true;
    const mode = $("#modeBtn"); mode.hidden = v === "splash";
    const inExplore = v === "explore";
    mode.innerHTML = inExplore ? I.cap + "<span>Study mode</span>" : I.compass + "<span>Explore mode</span>";
    mode.setAttribute("aria-label", inExplore ? "Study mode" : "Explore mode");
    $("#homeBtn").hidden = !(story || v === "path" || v === "quiz");
    const crumb = $("#crumb");
    if (v === "learn") crumb.textContent = "Study Mode";
    else if (v === "explore") crumb.textContent = "Explore Mode";
    else if ((v === "path" || v === "lesson" || v === "quiz") && (st.path || (st.story && st.story.path) || (qz && qz.p))) {
      const p = v === "quiz" ? qz.p : st.story ? st.story.path : st.path;
      crumb.innerHTML = '<button id="pathPick" aria-haspopup="true">' + esc(p.title) + I.caret + "</button>";
      $("#pathPick").onclick = (e) => { e.stopPropagation(); const m = $("#pathMenu"); m.hidden = !m.hidden; };
    } else crumb.textContent = "";
    $("#pathMenu").hidden = true; $("#menu").hidden = true;
    if (v === "learn") renderLearn();
    if (v === "path") renderPath();
    if (story) renderStory();
    $("#hdBtn").textContent = save.hd ? "HD" : "SD";
    $("#nightBtn").classList.toggle("on", st.night);
  }
  function buildPathMenu() {
    const m = $("#pathMenu"); m.textContent = "";
    SC.PATHS.forEach((p) => { const b = h("button", "", "<i style='background:" + p.color + "'></i>" + esc(p.title) + "<small>" + pathPct(p) + "%</small>"); b.onclick = () => { stopSpeak(); openPath(p); }; m.appendChild(b); });
  }
  function buildLayers() {
    const box = $("#layers"); box.innerHTML = "<h4>Network layers</h4>";
    [["cells", "Coverage cells"], ["waves", "Radio waves"], ["heat", "Signal heat map"], ["smallcells", "Small cells"], ["backhaul", "Fibre backhaul"], ["fibre", "All ducts and risers"], ["xray", "X-ray the city"], ["iot", "IoT sensor traffic"], ["core", "Core network diagram"]].forEach(([k, name]) => {
      const l = h("label", "", '<input type="checkbox">' + name), c = l.firstChild;
      c.checked = !!st.layers[k]; c.onchange = () => { st.layers[k] = c.checked; syncWorld(); };
      box.appendChild(l);
    });
  }
  function openMenu() {
    const m = $("#menu"); m.textContent = "";
    const item = (icon, text, state, fn) => { const b = h("button", "", icon + "<span>" + text + "</span>" + (state !== null ? '<span class="state' + (state ? " on" : "") + '">' + (state ? "On" : "Off") + "</span>" : "")); b.onclick = () => { fn(); if (!m.hidden) openMenu(); }; m.appendChild(b); };
    item(I.cap, "Study mode", null, () => go("learn")); item(I.compass, "Explore mode", null, () => go("explore"));
    m.appendChild(h("hr"));
    item(I.sound, "Read each step aloud", save.sound, () => { save.sound = !save.sound; persist(); if (!save.sound) stopSpeak(); else narrate(); if (st.story) renderStory(); });
    item(I.moon, "Night", st.night, toggleNight);
    item(I.bolt, "High quality (shadows, sharper)", save.hd, toggleHd);
    item(I.unlock, "Unlock every lesson", save.unlocked, () => { save.unlocked = !save.unlocked; persist(); if (st.view === "path") renderPath(); });
    m.appendChild(h("hr"));
    item(I.help, "How to use SetuCity", null, () => { m.hidden = true; openHelp(); });
    item(I.reset, "Reset my progress", null, () => { if (confirm("Clear all completed lessons, quiz scores and visited markers?")) { save.done = {}; save.quiz = {}; save.seen = {}; persist(); m.hidden = true; go("learn"); toast("Progress cleared"); } });
    m.appendChild(h("hr"));
    for (const [href, text] of [["../understand_5g/index.html", "5G Core Explorer: call flows and messages"], ["../../viewer.html", "Campus digital twin viewer"]]) { const a = h("a", "", I.ext + "<span>" + text + "</span>"); a.href = href; a.target = "_blank"; a.rel = "noopener"; m.appendChild(a); }
    m.hidden = false; $("#menuBtn").setAttribute("aria-expanded", "true");
  }
  function openHelp() {
    const box = $("#help .box"); box.className = "box glass";
    box.innerHTML = "<h3>How to use SetuCity</h3><dl>" +
      "<dt>Study mode</dt><dd>Seven paths, each a row of short lessons and a quiz. Lessons unlock in order; progress is saved in this browser.</dd>" +
      "<dt>Explore mode</dt><dd>Roam freely. Amber markers are use cases, blue are concepts, white are quick facts. Click one to start it.</dd>" +
      "<dt>Look around</dt><dd>Drag to orbit, right-drag or two fingers to pan, scroll or pinch to zoom. The view stays free during lessons.</dd>" +
      "<dt>Steps</dt><dd>Use the arrows on the card, or the left and right arrow keys. Esc closes a card or leaves a scene.</dd>" +
      "<dt>Cutaways</dt><dd>Some scenes lift the roof off a building. White “i” markers inside explain what you see.</dd>" +
      "<dt>Layers</dt><dd>In Explore mode the layers button (bottom left) overlays coverage, heat map, fibre and more on the city.</dd>" +
      "<dt>Read aloud</dt><dd>The speaker button narrates each step using your browser's voice.</dd></dl>" +
      '<button class="btn pri sm" id="helpOk">Got it</button>';
    $("#help").hidden = false; $("#helpOk").onclick = () => ($("#help").hidden = true); $("#helpOk").focus();
  }
  function toggleNight() { st.night = !st.night; W.setNight(st.night); $("#nightBtn").classList.toggle("on", st.night); }
  function toggleHd() { save.hd = !save.hd; persist(); W.setQuality(save.hd); $("#hdBtn").textContent = save.hd ? "HD" : "SD"; }

  function wire() {
    $("#goLearn").onclick = () => go("learn"); $("#goExplore").onclick = () => go("explore");
    $("#brand").onclick = (e) => { e.preventDefault(); go("splash"); };
    $("#modeBtn").onclick = () => go(st.view === "explore" ? "learn" : "explore");
    $("#homeBtn").onclick = () => { if (st.story) leaveStory(); else go("learn"); };
    $("#menuBtn").onclick = (e) => { e.stopPropagation(); const m = $("#menu"); if (m.hidden) openMenu(); else { m.hidden = true; $("#menuBtn").setAttribute("aria-expanded", "false"); } };
    $("#prev").onclick = () => step(-1); $("#next").onclick = () => step(1); $("#finish").onclick = finish;
    $("#speak").onclick = () => { save.sound = !save.sound; persist(); $("#speak").classList.toggle("on", save.sound); if (save.sound) narrate(); else stopSpeak(); };
    $("#qexit").onclick = () => openPath(qz.p);
    $("#layerBtn").onclick = (e) => { e.stopPropagation(); const l = $("#layers"); if (l.hidden) buildLayers(); l.hidden = !l.hidden; $("#layerBtn").setAttribute("aria-expanded", String(!l.hidden)); };
    $("#nightBtn").onclick = toggleNight; $("#hdBtn").onclick = toggleHd;
    const zr = $("#zr");
    zr.oninput = () => { zr.dragging = true; W.setZoom(zr.value / 100); }; zr.onchange = () => { zr.dragging = false; zr.blur(); };
    $("#zin").onclick = () => W.setZoom(Math.min(1, W.getZoom() + 0.12)); $("#zout").onclick = () => W.setZoom(Math.max(0, W.getZoom() - 0.12));
    $("#zreset").onclick = () => { if (st.story) syncWorld(1.2); else W.flyTo(SC.OVERVIEW, 1.4); };
    $("#help").onclick = (e) => { if (e.target.id === "help" || e.target.closest(".zoom")) $("#help").hidden = true; };
    const zoomArt = (e) => { const svg = e.target.closest("svg"); if (!svg || svg.classList.contains("ic")) return; const box = $("#help .box"); box.className = "box glass zoom"; box.innerHTML = svg.outerHTML; $("#help").hidden = false; };
    $("#story .art").onclick = zoomArt; $("#card").addEventListener("click", (e) => { if (e.target.closest(".pic")) zoomArt(e); });
    document.addEventListener("click", (e) => {
      if (!$("#menu").hidden && !e.target.closest("#menu")) { $("#menu").hidden = true; $("#menuBtn").setAttribute("aria-expanded", "false"); }
      if (!$("#pathMenu").hidden && !e.target.closest("#pathMenu")) $("#pathMenu").hidden = true;
      if (!$("#layers").hidden && !e.target.closest("#layers")) $("#layers").hidden = true;
    });
    document.addEventListener("keydown", (e) => {
      if (e.target.matches("input")) return;
      if (e.key === "Escape") { if (!$("#help").hidden) $("#help").hidden = true; else if (!$("#menu").hidden) $("#menu").hidden = true; else if (st.card) closeCard(); else if (st.story) leaveStory(); else if (st.view === "path") go("learn"); }
      else if (st.story && e.key === "ArrowRight") step(1);
      else if (st.story && e.key === "ArrowLeft") step(-1);
    });
    W.onUserMove = () => { W.follow = null; hideTip(); };
  }

  /* ================================================================= start */
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  async function boot() {
    /* The city is built in stages so the loading screen can paint between them. */
    const t0 = performance.now(), bar = $("#bootBar"), msg = $("#bootMsg");
    const stage = async (pct, text) => { bar.style.width = pct + "%"; msg.textContent = text; await pause(90); };
    await stage(12, "Starting the 3D engine…");
    W.init($("#gl"));
    await stage(34, "Building the city…");
    W.buildCity();
    await stage(72, "Switching on the network…");
    W.initFx();
    W.setQuality(save.hd);
    W.flyTo(SC.OVERVIEW, 0);
    W.onFrame = placePins;
    W.start();
    wire(); buildPathMenu();
    render(); syncWorld();
    await stage(100, "Ready");
    /* keep the credit on screen long enough to read, then fade into the city */
    await pause(Math.max(500, 2200 - (performance.now() - t0)));
    $("#boot").classList.add("gone");
    /* deep links: ?go=learn | explore | path:gen | lesson:gen:1:0 | scene:av:1 | info:i-macro | quiz:gen ; &night=1 ; &layers=heat,cells */
    const q = new URLSearchParams(location.search), g = (q.get("go") || "").split(":");
    if (q.get("night")) { st.night = true; W.setNight(true, true); }
    if (q.get("layers")) q.get("layers").split(",").forEach((k) => (st.layers[k] = true));
    try {
      if (g[0] === "learn" || g[0] === "explore") go(g[0]);
      else if (g[0] === "path") openPath(pathById(g[1]));
      else if (g[0] === "lesson") { st.path = pathById(g[1]); play(lessonStory(st.path, +g[2] || 0), +g[3] || 0); }
      else if (g[0] === "scene") { st.view = "explore"; play(sceneStory(g[1]), +g[2] || 0); }
      else if (g[0] === "info") { go("explore"); openInfo(SC.INFO.find((f) => f.id === g[1])); }
      else if (g[0] === "quiz") startQuiz(pathById(g[1]));
    } catch (e) { console.error(e); go("splash"); }
    SC.app = { st, go, play, step, sceneStory, lessonStory, openPath, startQuiz };
  }
  /* let the "Building the city" message paint before the heavy work starts */
  requestAnimationFrame(() => setTimeout(() => boot().catch((e) => { console.error(e); $("#bootMsg").textContent = "Something went wrong while building the city: " + e.message; }), 30));
})();
