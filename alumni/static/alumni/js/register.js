/* Inscription en 4 étapes : validation à chaque étape, indicateur de force du mot de passe. */
(function () {
  var form = document.getElementById("register-form");
  if (!form) return;
  var sections = Array.prototype.slice.call(form.querySelectorAll("[data-step]"));
  var tabs = document.querySelectorAll("[data-step-tab]");
  var prev = document.getElementById("btn-prev"), next = document.getElementById("btn-next"), submit = document.getElementById("btn-submit");
  var current = 1, last = sections.length;

  function show(n) {
    current = n;
    sections.forEach(function (s) { s.classList.toggle("hidden", Number(s.dataset.step) !== n); });
    tabs.forEach(function (t) {
      var k = Number(t.dataset.stepTab);
      t.classList.toggle("border-sky-600", k <= n); t.classList.toggle("text-gray-900", k <= n);
      t.classList.toggle("border-gray-200", k > n); t.classList.toggle("text-gray-400", k > n);
      if (k === n) t.setAttribute("aria-current", "step"); else t.removeAttribute("aria-current");
    });
    prev.classList.toggle("invisible", n === 1);
    next.classList.toggle("hidden", n === last);
    submit.classList.toggle("hidden", n !== last);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function stepValid(n) {
    var section = sections[n - 1], fields = section.querySelectorAll("input, select, textarea");
    for (var i = 0; i < fields.length; i++) {
      if (!fields[i].checkValidity()) { fields[i].reportValidity(); return false; }
    }
    return true;
  }

  next.addEventListener("click", function () { if (stepValid(current)) show(current + 1); });
  prev.addEventListener("click", function () { show(current - 1); });
  form.addEventListener("submit", function (e) {
    for (var n = 1; n <= last; n++) {
      if (!stepValid(n)) { e.preventDefault(); show(n); stepValid(n); return; }
    }
    var terms = document.getElementById("terms");
    if (!terms.checked) { e.preventDefault(); terms.setCustomValidity("Acceptez les conditions pour continuer."); terms.reportValidity(); terms.addEventListener("change", function () { terms.setCustomValidity(""); }, { once: true }); }
  });
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.tagName !== "TEXTAREA" && current < last) { e.preventDefault(); next.click(); }
  });

  var pw = document.getElementById("id_password"), bar = document.getElementById("pw-bar"), text = document.getElementById("pw-text");
  pw.addEventListener("input", function () {
    var v = pw.value, score = 0;
    if (v.length >= 8) score++;
    if (v.length >= 12) score++;
    if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++;
    if (/\d/.test(v) && /[^A-Za-z0-9]/.test(v)) score++;
    var labels = ["Trop court", "Faible", "Correct", "Bon", "Très bon"], colors = ["#ef4444", "#ef4444", "#f59e0b", "#0ea5e9", "#059669"];
    if (!v) { bar.style.width = "0"; text.textContent = pw.getAttribute("minlength") + " caractères minimum."; return; }
    bar.style.width = (20 + score * 20) + "%"; bar.style.background = colors[score]; text.textContent = labels[score];
  });

  show(Number(form.dataset.errorStep) || 1);
})();
