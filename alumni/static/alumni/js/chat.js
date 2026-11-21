/* Messagerie AEPS-ALUMNI : liste de contacts, conversation, vocal, appels Jitsi.
   Toutes les données utilisateur sont insérées via textContent (pas d'innerHTML). */
(function () {
  "use strict";
  var cfg = JSON.parse(document.getElementById("chat-config").textContent);
  var csrf = (document.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
  var $ = function (id) { return document.getElementById(id); };

  var contacts = [], current = null, lastAt = null, firstLoad = true;
  var audio = null, playingId = null;
  var recorder_type = "", recorder = null, chunks = [], recTimer = null, recSeconds = 0, recCancel = false;
  var jitsi = null;

  function icons() { if (window.lucide) window.lucide.createIcons(); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function icon(name, cls) {
    var i = document.createElement("i");
    i.setAttribute("data-lucide", name);
    i.className = cls || "w-5 h-5";
    return i;
  }
  function api(url, opts) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, opts || {})).then(function (r) {
      if (r.status === 401) { window.location.href = "/login/"; throw new Error("auth"); }
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    });
  }

  /* ---------- Contacts ---------- */
  function renderContacts() {
    var q = $("contact-search").value.trim().toLowerCase();
    var box = $("contacts");
    box.textContent = "";
    var list = contacts.filter(function (c) {
      return !q || (c.first_name + " " + c.last_name).toLowerCase().indexOf(q) !== -1 ||
        String(c.promo || "").toLowerCase().indexOf(q) !== -1;
    });
    if (!list.length) {
      var empty = el("div", "py-10 text-center opacity-40");
      empty.appendChild(el("p", "text-xs font-semibold tracking-wide", "Aucun membre trouvé"));
      box.appendChild(empty);
    }
    list.forEach(function (c) {
      var active = current && current.id === c.id;
      var b = el("button", "w-full p-4 rounded-2xl flex items-center gap-4 transition-all " +
        (active ? "bg-sky-600 text-white shadow-sm" : "hover:bg-gray-50 text-gray-900"));
      b.type = "button";
      var av = el("div", "w-12 h-12 rounded-2xl bg-white shadow-md flex items-center justify-center flex-shrink-0 " + (active ? "text-sky-500" : "text-sky-700"));
      av.appendChild(icon("user", "w-6 h-6"));
      b.appendChild(av);
      var body = el("div", "flex-grow text-left overflow-hidden");
      var top = el("div", "flex justify-between items-center mb-1");
      top.appendChild(el("h4", "font-semibold truncate text-sm", c.first_name + " " + c.last_name));
      top.appendChild(el("span", "text-xs font-bold whitespace-nowrap " + (active ? "text-sky-50" : "text-gray-400"), c.lastTime || ""));
      var bottom = el("div", "flex justify-between items-center");
      bottom.appendChild(el("p", "text-xs truncate font-medium " + (active ? "text-sky-50" : "text-gray-500"), c.lastMessage || "Démarrer une discussion..."));
      if (c.unread > 0) {
        bottom.appendChild(el("span", "min-w-[18px] h-[18px] rounded-full flex items-center justify-center text-xs font-semibold px-1 " +
          (active ? "bg-white text-sky-500" : "bg-red-500 text-white"), String(c.unread)));
      }
      body.appendChild(top); body.appendChild(bottom);
      b.appendChild(body);
      b.addEventListener("click", function () { openChat(c); });
      box.appendChild(b);
    });
    icons();
  }

  function updateTotal(n) {
    var badge = $("total-unread");
    badge.textContent = String(n);
    badge.classList.toggle("hidden", !n);
  }

  function loadContacts() {
    return api(cfg.urls.contacts).then(function (d) {
      contacts = d.contacts || [];
      updateTotal(d.total_unread || 0);
      renderContacts();
    }).catch(function () {});
  }

  /* ---------- Conversation ---------- */
  function atBottom() {
    var h = $("history");
    return h.scrollHeight - h.scrollTop - h.clientHeight < 50;
  }
  function scrollDown() { var h = $("history"); h.scrollTop = h.scrollHeight; }

  function bubble(m) {
    var row = el("div", "flex items-end gap-3 " + (m.mine ? "flex-row-reverse" : "flex-row"));
    row.dataset.id = m.id;
    var av = el("div", "w-8 h-8 rounded-xl shadow-sm bg-white flex items-center justify-center text-sky-400 flex-shrink-0 mb-1");
    av.appendChild(icon("user", "w-4 h-4"));
    row.appendChild(av);
    var col = el("div", "max-w-[85%] md:max-w-[65%] flex flex-col " + (m.mine ? "items-end" : "items-start"));
    if (m.sender && !m.mine) col.appendChild(el("span", "text-xs font-semibold text-sky-700 mb-1 ml-2 tracking-wide", m.sender));
    var b = el("div", "w-full p-4 rounded-2xl shadow-sm relative " +
      (m.mine ? "bg-sky-600 text-white rounded-br-md" : "bg-white border border-gray-100 text-gray-900 rounded-bl-md"));
    var text = m.text || "";
    if (text.indexOf("[AUDIO]") === 0) {
      var wrap = el("div", "flex items-center gap-4 py-1 min-w-[200px]");
      var play = el("button", "w-10 h-10 rounded-full flex items-center justify-center shadow-md " + (m.mine ? "bg-white text-sky-700" : "bg-sky-600 text-white"));
      play.type = "button"; play.setAttribute("aria-label", "Lire le message vocal");
      play.appendChild(icon("play", "w-[18px] h-[18px]"));
      play.addEventListener("click", function () { toggleAudio(text.slice(7), String(m.id), play); });
      wrap.appendChild(play);
      wrap.appendChild(el("span", "text-xs font-semibold opacity-70", "🎤 Message vocal"));
      b.appendChild(wrap);
    } else if (text.indexOf("[CALL]") === 0) {
      var parts = text.slice(6).split(":");
      var type = parts[0] === "video" ? "video" : "audio";
      var room = parts.slice(1).join(":");
      var call = el("div", "flex items-center gap-4 py-1 min-w-[200px]");
      var ic = el("div", "w-10 h-10 rounded-full flex items-center justify-center " + (m.mine ? "bg-sky-400" : "bg-sky-100"));
      ic.appendChild(icon(type === "video" ? "video" : "phone", "w-[18px] h-[18px]"));
      call.appendChild(ic);
      var info = el("div", "flex-grow");
      info.appendChild(el("p", "text-xs font-semibold tracking-wide mb-2", "Appel " + (type === "video" ? "Vidéo" : "Audio")));
      if (m.mine) {
        info.appendChild(el("p", "text-xs font-bold opacity-60", "Appel lancé"));
      } else {
        var join = el("button", "px-4 py-1.5 bg-emerald-700 text-white rounded-full text-xs font-semibold tracking-wide hover:bg-emerald-800", "Rejoindre");
        join.type = "button";
        join.addEventListener("click", function () { startJitsi(type, room); });
        info.appendChild(join);
      }
      call.appendChild(info);
      b.appendChild(call);
    } else {
      b.appendChild(el("p", "text-sm font-medium leading-relaxed whitespace-pre-line break-words", text));
    }
    b.appendChild(el("span", "text-xs font-semibold absolute -bottom-6 tracking-wide whitespace-nowrap " +
      (m.mine ? "right-2 text-sky-700" : "left-2 text-gray-300"), m.time || ""));
    col.appendChild(b);
    row.appendChild(col);
    return row;
  }

  function appendMessages(list, forceScroll) {
    var h = $("history"), stick = forceScroll || atBottom();
    var placeholder = $("history-empty");
    if (placeholder && list.length) placeholder.remove();
    list.forEach(function (m) {
      if (h.querySelector('[data-id="' + String(m.id).replace(/"/g, "") + '"]')) return;
      h.appendChild(bubble(m));
      if (m.created_at) lastAt = m.created_at;
    });
    icons();
    if (stick) scrollDown();
  }

  function convUrl(after) {
    var u = cfg.urls.conversation + "?with=" + encodeURIComponent(current.id);
    if (after) u += "&after=" + encodeURIComponent(after);
    return u;
  }

  function openChat(c) {
    current = c; lastAt = null;
    stopAudio();
    $("chat-empty").classList.add("hidden");
    var main = $("chat-main"); main.classList.remove("hidden"); main.classList.add("flex");
    $("chat").classList.remove("hidden"); $("chat").classList.add("flex");
    $("sidebar").classList.add("hidden", "md:flex");
    $("peer-name").textContent = c.first_name + " " + c.last_name;
    $("peer-sub").textContent = c.group ? "Discussion de groupe" : "Promo " + (c.promo || "N/A") + " · " + (c.job || "Membre");
    $("call-audio").classList.toggle("hidden", !!c.group);
    $("call-video").classList.toggle("hidden", !!c.group);
    var h = $("history"); h.textContent = "";
    api(convUrl()).then(function (d) {
      var msgs = d.messages || [];
      if (!msgs.length) {
        var e = el("div", "h-full flex flex-col items-center justify-center text-gray-300 gap-4 opacity-60");
        e.id = "history-empty";
        e.appendChild(el("p", "font-semibold tracking-wide text-xs", "C'est le début d'une belle histoire..."));
        h.appendChild(e);
      }
      appendMessages(msgs, true);
      loadContacts();
    }).catch(function () {});
    renderContacts();
  }

  function pollConversation() {
    if (!current) return;
    var me = current.id;
    api(convUrl(lastAt)).then(function (d) {
      if (!current || current.id !== me) return;
      if ((d.messages || []).length) { idle = 0; appendMessages(d.messages); loadContacts(); }
    }).catch(function () {});
  }

  function send(text) {
    if (!current || !text) return Promise.resolve();
    return api(cfg.urls.send, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ to: current.id, text: text })
    }).then(function (d) {
      if (d.message) appendMessages([d.message], true);
      loadContacts();
    }).catch(function () { window.alert("Le message n'a pas pu être envoyé. Réessayez."); });
  }

  $("composer").addEventListener("submit", function (e) {
    e.preventDefault();
    var input = $("text"), v = input.value.trim();
    if (!v) return;
    input.value = "";
    send(v);
  });
  $("back").addEventListener("click", function () {
    current = null;
    $("chat").classList.add("hidden"); $("chat").classList.remove("flex");
    $("sidebar").classList.remove("hidden");
    renderContacts();
  });
  $("contact-search").addEventListener("input", renderContacts);

  /* ---------- Audio ---------- */
  function setPlayIcon(btn, name) {
    btn.textContent = ""; btn.appendChild(icon(name, "w-[18px] h-[18px]")); icons();
  }
  function stopAudio() {
    if (audio) { audio.pause(); audio = null; }
    document.querySelectorAll("#history button[aria-label='Lire le message vocal']").forEach(function (b) { setPlayIcon(b, "play"); });
    playingId = null;
  }
  function toggleAudio(dataUrl, id, btn) {
    if (playingId === id) { stopAudio(); return; }
    stopAudio();
    if (dataUrl.indexOf("data:audio") !== 0 && dataUrl.indexOf("https://") !== 0) return;
    audio = new Audio(dataUrl);
    playingId = id;
    setPlayIcon(btn, "pause");
    audio.onended = stopAudio;
    audio.onerror = function () { window.alert("Erreur lors de la lecture du message vocal."); stopAudio(); };
    audio.play().catch(stopAudio);
  }

  function fmt(s) { return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60); }
  function showRecording(on) {
    $("recording").classList.toggle("hidden", !on);
    $("recording").classList.toggle("flex", on);
    $("composer").classList.toggle("hidden", on);
  }
  $("rec-start").addEventListener("click", function () {
    if (!navigator.mediaDevices || !window.MediaRecorder) { window.alert("Enregistrement vocal non supporté par ce navigateur."); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      recorder = new MediaRecorder(stream); recorder_type = recorder.mimeType; chunks = []; recCancel = false;
      recorder.ondataavailable = function (e) { chunks.push(e.data); };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        if (recCancel) return;
        var type = (recorder_type || "audio/webm").split(";")[0];
        var form = new FormData();
        form.append("audio", new Blob(chunks, { type: type }), "vocal." + (type.indexOf("mp4") !== -1 ? "m4a" : "webm"));
        api(cfg.urls.voice, { method: "POST", headers: { "X-CSRFToken": csrf }, body: form })
          .then(function (d) { return send("[AUDIO]" + d.url); })
          .catch(function () { window.alert("Le message vocal n'a pas pu être envoyé."); });
      };
      recorder.start(); recSeconds = 0; $("rec-time").textContent = "0:00"; showRecording(true);
      recTimer = setInterval(function () { recSeconds++; $("rec-time").textContent = fmt(recSeconds); }, 1000);
    }).catch(function () { window.alert("Accès au micro refusé."); });
  });
  function stopRec(cancel) {
    if (!recorder) return;
    recCancel = cancel; clearInterval(recTimer);
    if (recorder.state !== "inactive") recorder.stop();
    recorder = null; showRecording(false);
  }
  $("rec-cancel").addEventListener("click", function () { stopRec(true); });
  $("rec-send").addEventListener("click", function () { stopRec(false); });

  /* ---------- Appels ---------- */
  function newRoom() {
    var bytes = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(bytes);
    return "aeps-" + Array.prototype.map.call(bytes, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }
  function startCall(type) {
    if (!current) return;
    if (current.group) return;
    var room = newRoom();
    send("[CALL]" + type + ":" + room).then(function () { startJitsi(type, room); });
  }
  function startJitsi(type, room) {
    if (!window.JitsiMeetExternalAPI) { window.alert("Le service d'appel n'est pas encore chargé. Réessayez dans un instant."); return; }
    endCall();
    $("call-ui").classList.remove("hidden");
    jitsi = new window.JitsiMeetExternalAPI("meet.jit.si", {
      roomName: room, width: "100%", height: "100%", parentNode: $("jitsi"),
      configOverwrite: { startWithAudioMuted: false, startWithVideoMuted: type === "audio", prejoinPageEnabled: false },
      userInfo: { displayName: cfg.me.first_name + " " + cfg.me.last_name, email: cfg.me.email }
    });
    jitsi.addEventListeners({ readyToClose: endCall, videoConferenceLeft: endCall });
  }
  function endCall() {
    if (jitsi) { jitsi.dispose(); jitsi = null; }
    $("jitsi").textContent = "";
    $("call-ui").classList.add("hidden");
  }
  $("call-audio").addEventListener("click", function () { startCall("audio"); });
  $("call-video").addEventListener("click", function () { startCall("video"); });
  $("call-end").addEventListener("click", endCall);

  /* ---------- Démarrage ---------- */
  loadContacts();
  var idle = 0;
  function tick() {
    if (!document.hidden) {
      if (current) pollConversation();
      if (++idle % 3 === 0) loadContacts();
    }
    // 3 s au début, jusqu'à 15 s quand rien ne se passe
    setTimeout(tick, Math.min(15000, 3000 + Math.floor(idle / 10) * 2000));
  }
  setTimeout(tick, 3000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { idle = 0; if (current) pollConversation(); loadContacts(); } });
  icons();
})();
