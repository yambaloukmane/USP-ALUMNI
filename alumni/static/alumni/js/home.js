/* Accueil : bandeau à deux écrans (titre qui s'écrit, mot sélectionné, écran qui glisse), photos dévoilées au défilement,
   chiffres qui comptent. Avec « réduire les animations » : tout s'affiche tout de suite, sans défilement automatique. */
(function () {
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var doc = document.documentElement;

  /* ---------- Bandeau ---------- */
  var hero = document.querySelector("[data-hero]");
  if (hero) {
    var track = hero.querySelector("[data-track]"), viewport = hero.querySelector(".hm-viewport");
    var slides = Array.prototype.slice.call(hero.querySelectorAll("[data-slide]"));
    var dots = Array.prototype.slice.call(hero.querySelectorAll("[data-dot]"));
    var next = hero.querySelector("[data-next]");
    var index = 0, typeTimer = null, autoTimer = null, token = 0, rounds = 0, hovering = false;

    function segmentsOf(ghost) {
      var out = [];
      Array.prototype.forEach.call(ghost.childNodes, function (n) {
        if (n.nodeType === 3) out.push({ t: n.textContent, sel: false });
        else if (n.classList && n.classList.contains("sel")) out.push({ t: n.textContent, sel: true });
      });
      return out;
    }
    function render(live, segs, n) {
      var html = "", left = n;
      segs.forEach(function (sg) {
        if (left <= 0) return;
        var part = sg.t.slice(0, left); left -= part.length;
        var esc = part.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        html += sg.sel ? '<span class="sel">' + esc + "</span>" : esc;
      });
      live.innerHTML = html;
    }
    function addHandles(live) {
      var sel = live.querySelector(".sel");
      if (!sel) return;
      ["tl", "tr", "bl", "br"].forEach(function (c) { var i = document.createElement("i"); i.className = "hd " + c; sel.appendChild(i); });
      requestAnimationFrame(function () { requestAnimationFrame(function () { sel.classList.add("is-selected"); }); });
    }
    function typeSlide(slide, done) {
      var live = slide.querySelector("[data-live]"), ghost = slide.querySelector(".tw-ghost");
      var my = ++token;
      slide.classList.remove("is-typed");
      if (!live || !ghost) { slide.classList.add("is-typed"); done && done(); return; }
      live.classList.remove("is-done"); live.innerHTML = "";
      var segs = segmentsOf(ghost), total = segs.reduce(function (a, s) { return a + s.t.length; }, 0), n = 0;
      (function step() {
        if (my !== token) return;
        n++; render(live, segs, n);
        if (n < total) { typeTimer = setTimeout(step, 34); return; }
        live.classList.add("is-done"); addHandles(live);
        typeTimer = setTimeout(function () { if (my !== token) return; slide.classList.add("is-typed"); done && done(); }, 650);
      })();
    }
    function resetSlide(slide) {
      slide.classList.remove("is-typed");
      var live = slide.querySelector("[data-live]"); if (live) live.innerHTML = "";
    }
    function fit() { viewport.style.height = slides[index].offsetHeight + "px"; }
    if ("ResizeObserver" in window) { var ro = new ResizeObserver(function () { fit(); }); slides.forEach(function (sl) { ro.observe(sl); }); }
    window.addEventListener("resize", fit);
    function show(i, animate) {
      clearTimeout(typeTimer); clearTimeout(autoTimer); token++;
      var prev = slides[index]; index = (i + slides.length) % slides.length;
      if (!animate) track.style.transition = "none";
      track.style.transform = "translateX(" + (-100 * index) + "%)";
      if (!animate) { void track.offsetWidth; track.style.transition = ""; }
      fit();
      slides.forEach(function (s, k) { s.inert = k !== index; s.setAttribute("aria-hidden", k === index ? "false" : "true"); });
      dots.forEach(function (d, k) { d.setAttribute("aria-current", k === index ? "true" : "false"); });
      if (prev && prev !== slides[index]) setTimeout(function () { if (slides[index] !== prev) resetSlide(prev); }, 1000);
      if (reduce) { slides[index].classList.add("is-typed"); return; }
      setTimeout(function () { typeSlide(slides[index], schedule); }, animate ? 600 : 0);
    }
    function schedule() {
      clearTimeout(autoTimer);
      if (reduce || hovering) return;
      if (index === 0 && rounds >= 1) return;           /* un seul tour, puis l'écran 1 reste affiché */
      autoTimer = setTimeout(function () { if (index === slides.length - 1) rounds++; show(index + 1, true); }, index === 0 ? 4200 : 6500);
    }

    next.addEventListener("click", function () { rounds = 1; show(index + 1, true); });
    dots.forEach(function (d) { d.addEventListener("click", function () { rounds = 1; show(Number(d.getAttribute("data-dot")), true); }); });
    hero.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight") { rounds = 1; show(index + 1, true); }
      else if (e.key === "ArrowLeft") { rounds = 1; show(index - 1, true); }
    });
    hero.addEventListener("mouseenter", function () { hovering = true; clearTimeout(autoTimer); });
    hero.addEventListener("mouseleave", function () { hovering = false; if (slides[index].classList.contains("is-typed")) autoTimer = setTimeout(schedule, 1500); });
    document.addEventListener("visibilitychange", function () { if (document.hidden) clearTimeout(autoTimer); else if (slides[index].classList.contains("is-typed")) schedule(); });

    if (!reduce) doc.classList.add("tw-on");
    show(0, false);
  }

  /* ---------- Photos et chiffres ---------- */
  var wipes = document.querySelectorAll(".hm-wipe"), wrap = document.querySelector("[data-count-wrap]");
  function showAll() { Array.prototype.forEach.call(wipes, function (el) { el.classList.add("is-visible"); }); }
  if (reduce || !("IntersectionObserver" in window)) { showAll(); return; }

  function countUp(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(target) || target <= 0) return;
    var start = null, dur = 1200;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    }
    el.textContent = "0";
    requestAnimationFrame(step);
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add("is-visible");
      if (e.target === wrap) Array.prototype.forEach.call(wrap.querySelectorAll("[data-count]"), countUp);
      io.unobserve(e.target);
    });
  }, { threshold: 0.2 });
  Array.prototype.forEach.call(wipes, function (el) { io.observe(el); });
  if (wrap) io.observe(wrap);
})();
