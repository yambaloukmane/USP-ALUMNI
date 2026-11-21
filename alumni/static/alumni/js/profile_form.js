/* Comportements communs aux formulaires de profil (inscription et page profil). */
(function () {
  var school = document.querySelector("[data-school]");
  if (school) {
    var other = document.querySelector("[data-school-other]"), track = document.querySelector("[data-school-track]");
    var sync = function () {
      other.classList.toggle("hidden", school.value.indexOf("Autre école") !== 0);
      track.classList.toggle("hidden", school.value === "" || school.value === "Pas encore intégré");
    };
    school.addEventListener("change", sync);
    sync();
  }
  document.querySelectorAll("[data-count]").forEach(function (area) {
    var out = area.parentNode.querySelector("[data-count-out]");
    var update = function () { if (out) out.textContent = area.value.length; };
    area.addEventListener("input", update);
    update();
  });
})();
