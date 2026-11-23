/* Accueil : photos qui se dévoilent au défilement, chiffres qui comptent une fois. Inactif si « réduire les animations ». */
(function () {
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var wipes = document.querySelectorAll(".hm-wipe"), wrap = document.querySelector("[data-count-wrap]");
  function show() { Array.prototype.forEach.call(wipes, function (el) { el.classList.add("is-visible"); }); }
  if (reduce || !("IntersectionObserver" in window)) { show(); return; }

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
