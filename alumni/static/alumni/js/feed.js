/* Fil Actualités & Emplois AEPS-ALUMNI : filtres, recherche, "J'aime" et commentaires en direct.
   Toutes les données utilisateur sont insérées via textContent (pas d'innerHTML). */
(function () {
  "use strict";
  var csrf = (document.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
  var list = document.getElementById("feed-list");
  if (!list) return;

  function icons() { if (window.lucide) window.lucide.createIcons(); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function api(url, opts) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, opts || {})).then(function (r) {
      if (r.status === 401) { window.location.href = "/login/"; throw new Error("auth"); }
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; });
    });
  }

  /* ---------- Filtres + recherche ---------- */
  var search = document.getElementById("feed-search");
  var filterBtns = document.querySelectorAll(".filter-btn");
  var posts = document.querySelectorAll(".feed-post");
  var empty = document.getElementById("feed-empty");
  var activeFilter = "all";
  var ON = ["bg-white", "text-gray-900", "shadow-sm"];
  var OFF = ["text-gray-500"];

  function applyFilter() {
    var q = search.value.trim().toLowerCase();
    var visible = 0;
    posts.forEach(function (post) {
      var typeOk = activeFilter === "all" || post.dataset.type === activeFilter;
      var textOk = !q || post.dataset.search.indexOf(q) !== -1;
      var match = typeOk && textOk;
      post.classList.toggle("hidden", !match);
      if (match) visible++;
    });
    empty.classList.toggle("hidden", visible > 0);
  }

  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activeFilter = btn.dataset.filter;
      filterBtns.forEach(function (b) {
        var on = b === btn;
        ON.forEach(function (c) { b.classList.toggle(c, on); });
        OFF.forEach(function (c) { b.classList.toggle(c, !on); });
      });
      applyFilter();
    });
  });
  if (filterBtns.length) filterBtns[0].click();
  search.addEventListener("input", applyFilter);

  /* ---------- "J'aime" ---------- */
  list.querySelectorAll(".like-btn").forEach(function (btn) {
    var icon = btn.querySelector(".like-icon");
    var count = btn.querySelector(".like-count");
    function paint(liked) {
      btn.classList.toggle("text-red-500", liked);
      btn.classList.toggle("text-gray-500", !liked);
      if (icon) icon.style.fill = liked ? "currentColor" : "none";
    }
    paint(btn.dataset.liked === "1");
    btn.addEventListener("click", function () {
      var post = btn.closest(".feed-post");
      btn.disabled = true;
      api(post.dataset.likeUrl, { method: "POST", headers: { "X-CSRFToken": csrf } })
        .then(function (res) {
          if (res.ok) {
            btn.dataset.liked = res.data.liked ? "1" : "0";
            paint(res.data.liked);
            count.textContent = res.data.count;
          }
        })
        .finally(function () { btn.disabled = false; });
    });
  });

  /* ---------- Commentaires ---------- */
  function commentRow(c) {
    var row = el("div", "flex items-start gap-2.5");
    var av = el("div", "w-8 h-8 rounded-xl bg-gray-300 text-gray-600 text-[11px] font-bold flex items-center justify-center shrink-0");
    av.textContent = (c.author || "?").split(" ").map(function (p) { return p.slice(0, 1); }).slice(0, 2).join("").toUpperCase();
    row.appendChild(av);
    var bubble = el("div", "bg-white rounded-2xl px-4 py-2.5 flex-grow");
    var head = el("div", "flex items-baseline justify-between gap-3");
    head.appendChild(el("span", "font-bold text-xs text-gray-900", c.author));
    bubble.appendChild(head);
    bubble.appendChild(el("p", "text-sm text-gray-700 font-medium mt-0.5", c.body));
    row.appendChild(bubble);
    return row;
  }

  list.querySelectorAll(".feed-post").forEach(function (post) {
    var toggle = post.querySelector(".comment-toggle");
    var panel = post.querySelector(".comments-panel");
    var commentsList = post.querySelector(".comments-list");
    var countEl = post.querySelector(".comment-count");
    var pluralEl = post.querySelector(".comment-plural");
    var form = post.querySelector(".comment-form");
    var input = post.querySelector(".comment-input");
    var loaded = false;

    function setCount(n) {
      countEl.textContent = n;
      pluralEl.textContent = n > 1 ? "s" : "";
    }

    function load() {
      if (loaded) return;
      loaded = true;
      commentsList.appendChild(el("p", "text-xs text-gray-400 font-semibold", "Chargement..."));
      api(post.dataset.commentsUrl).then(function (res) {
        commentsList.textContent = "";
        if (res.ok && res.data.comments && res.data.comments.length) {
          res.data.comments.forEach(function (c) { commentsList.appendChild(commentRow(c)); });
        }
      });
    }

    toggle.addEventListener("click", function () {
      var opening = panel.classList.contains("hidden");
      panel.classList.toggle("hidden");
      if (opening) load();
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      input.disabled = true;
      api(post.dataset.commentUrl, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ body: text }),
      }).then(function (res) {
        if (res.ok && res.data.comment) {
          commentsList.appendChild(commentRow(res.data.comment));
          setCount(parseInt(countEl.textContent, 10) + 1 || 1);
          input.value = "";
        } else {
          window.alert((res.data && res.data.error) || "Le commentaire n'a pas pu être envoyé.");
        }
      }).finally(function () { input.disabled = false; input.focus(); });
    });
  });

  icons();
})();
