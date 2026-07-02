/*!
 * Clara — widget de chat embeddable pour Voyage d'Ô (location-cure.net)
 * Vanilla JS, zéro dépendance, zéro build. Intégration :
 *   <script src="clara-widget.js" data-api-url="https://votre-backend"></script>
 * (un <div id="clara-widget"></div> est optionnel ; sinon le widget s'ajoute au body)
 *
 * DA reprise de location-cure.net : bleu thermal #449fb5, orange CTA #e5811d,
 * slate #2c3e50, police Lato. Conçu pour des curistes seniors :
 * grande typographie, fort contraste, boutons larges, ARIA + clavier.
 */
(function () {
  "use strict";

  if (window.__claraWidgetLoaded) return;
  window.__claraWidgetLoaded = true;

  // ── Configuration (data-* du <script>, ou window.ClaraWidgetConfig) ──────────
  var script = document.currentScript || (function () {
    var s = document.getElementsByTagName("script");
    return s[s.length - 1];
  })();
  var cfg = window.ClaraWidgetConfig || {};
  function opt(key, dataKey, fallback) {
    if (cfg[key] != null) return cfg[key];
    if (script && script.dataset && script.dataset[dataKey] != null) return script.dataset[dataKey];
    return fallback;
  }
  var API_URL = (opt("apiUrl", "apiUrl", window.location.origin) || "").replace(/\/$/, "");
  var LOGO = opt("logo", "logo", "");
  var TITLE = opt("title", "title", "Clara");
  var SUBTITLE = opt("subtitle", "subtitle", "Assistante Voyage d'Ô");
  var WELCOME = opt("welcome", "welcome",
    "Bonjour, je suis Clara 👋 Posez-moi votre question sur votre cure, un logement ou votre séjour.");
  var STARTER_SUGGESTIONS = opt("suggestions", "suggestions",
    "Trouver un logement|Une question sur l'assurance|Le déroulement du séjour")
    .split("|").map(function (s) { return s.trim(); }).filter(Boolean);

  // ── Session ───────────────────────────────────────────────────────────────
  var SESSION_KEY = "clara_session_id";
  function sessionId() {
    var id = null;
    try { id = window.localStorage.getItem(SESSION_KEY); } catch (e) {}
    if (!id) {
      id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : "s-" + Date.now() + "-" + Math.random().toString(16).slice(2);
      try { window.localStorage.setItem(SESSION_KEY, id); } catch (e) {}
    }
    return id;
  }

  // ── Styles (scopés sous .clara-root pour ne pas affecter le site hôte) ───────
  var CSS = [
    ".clara-root{--clara-blue:#449fb5;--clara-blue-dk:#2c3e50;--clara-orange:#e5811d;",
    "--clara-ink:#2c3e50;--clara-soft:#eef0f1;--clara-bot:#f3f7f9;--clara-white:#fff;",
    "font-family:Lato,'Segoe UI',system-ui,Arial,sans-serif;font-size:17px;line-height:1.55;}",
    ".clara-root *{box-sizing:border-box;}",
    ".clara-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0;}",
    // launcher
    ".clara-launcher{position:fixed;right:24px;bottom:24px;width:66px;height:66px;border-radius:50%;",
    "background:var(--clara-blue);color:#fff;border:none;cursor:pointer;box-shadow:0 6px 22px rgba(44,62,80,.28);",
    "display:flex;align-items:center;justify-content:center;z-index:2147483600;transition:transform .15s,background .2s;}",
    ".clara-launcher:hover{background:#3a8a9e;transform:translateY(-2px);}",
    ".clara-launcher:focus-visible{outline:3px solid var(--clara-orange);outline-offset:3px;}",
    ".clara-launcher svg{width:32px;height:32px;}",
    ".clara-badge{position:absolute;top:-3px;right:-3px;background:var(--clara-orange);color:#fff;",
    "min-width:20px;height:20px;border-radius:10px;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;padding:0 5px;}",
    // panel
    ".clara-panel{position:fixed;right:24px;bottom:104px;width:384px;max-width:calc(100vw - 32px);",
    "height:580px;max-height:calc(100vh - 132px);background:var(--clara-white);border-radius:18px;",
    "box-shadow:0 16px 48px rgba(44,62,80,.32);display:flex;flex-direction:column;overflow:hidden;",
    "z-index:2147483601;opacity:0;transform:translateY(12px) scale(.98);pointer-events:none;transition:opacity .18s,transform .18s;}",
    ".clara-panel.clara-open{opacity:1;transform:none;pointer-events:auto;}",
    // header
    ".clara-header{background:var(--clara-blue);color:#fff;padding:16px 18px;display:flex;align-items:center;gap:12px;}",
    ".clara-header__logo{width:40px;height:40px;border-radius:50%;background:#fff;flex:0 0 auto;",
    "display:flex;align-items:center;justify-content:center;overflow:hidden;font-size:22px;}",
    ".clara-header__logo img{width:100%;height:100%;object-fit:contain;}",
    ".clara-header__txt{flex:1;min-width:0;}",
    ".clara-header__title{font-weight:700;font-size:19px;}",
    ".clara-header__sub{font-size:14px;opacity:.92;}",
    ".clara-close{background:rgba(255,255,255,.18);border:none;color:#fff;width:38px;height:38px;",
    "border-radius:50%;cursor:pointer;font-size:22px;line-height:1;display:flex;align-items:center;justify-content:center;}",
    ".clara-close:hover{background:rgba(255,255,255,.32);}",
    ".clara-close:focus-visible{outline:3px solid var(--clara-orange);outline-offset:2px;}",
    // body
    ".clara-body{flex:1;overflow-y:auto;padding:18px 16px;background:var(--clara-soft);display:flex;flex-direction:column;gap:12px;}",
    ".clara-msg{max-width:85%;padding:12px 15px;border-radius:16px;white-space:pre-wrap;word-wrap:break-word;font-size:17px;}",
    ".clara-msg--bot{align-self:flex-start;background:var(--clara-bot);color:var(--clara-ink);border:1px solid #e3ebef;border-bottom-left-radius:5px;}",
    ".clara-msg--user{align-self:flex-end;background:var(--clara-blue);color:#fff;border-bottom-right-radius:5px;}",
    ".clara-msg--err{align-self:flex-start;background:#fbe6e1;color:#9c2b16;border:1px solid #f3c4b8;}",
    ".clara-sources{align-self:flex-start;font-size:13px;color:#5b7385;font-style:italic;margin-top:-4px;padding:0 6px;max-width:85%;}",
    ".clara-suggestions{display:flex;flex-wrap:wrap;gap:8px;align-self:flex-start;max-width:94%;margin-top:2px;}",
    ".clara-chip{background:#fff;color:var(--clara-blue-dk);border:1.5px solid var(--clara-blue);",
    "border-radius:18px;padding:9px 14px;font-size:15px;font-family:inherit;cursor:pointer;line-height:1.2;}",
    ".clara-chip:hover{background:var(--clara-blue);color:#fff;}",
    ".clara-chip:focus-visible{outline:3px solid var(--clara-orange);outline-offset:2px;}",
    // typing
    ".clara-typing{align-self:flex-start;background:var(--clara-bot);border:1px solid #e3ebef;border-radius:16px;",
    "border-bottom-left-radius:5px;padding:14px 16px;display:none;}",
    ".clara-typing.clara-on{display:flex;gap:5px;}",
    ".clara-typing span{width:8px;height:8px;border-radius:50%;background:#9ab4be;animation:clara-bounce 1.2s infinite;}",
    ".clara-typing span:nth-child(2){animation-delay:.2s;}.clara-typing span:nth-child(3){animation-delay:.4s;}",
    "@keyframes clara-bounce{0%,60%,100%{transform:translateY(0);opacity:.6;}30%{transform:translateY(-6px);opacity:1;}}",
    // footer / input
    ".clara-footer{border-top:1px solid #e3ebef;background:#fff;padding:12px;display:flex;gap:10px;align-items:flex-end;}",
    ".clara-input{flex:1;resize:none;border:2px solid #d7e2e8;border-radius:12px;padding:12px 14px;",
    "font-family:inherit;font-size:17px;line-height:1.4;max-height:120px;color:var(--clara-ink);}",
    ".clara-input:focus{outline:none;border-color:var(--clara-blue);}",
    ".clara-send{flex:0 0 auto;background:var(--clara-orange);color:#fff;border:none;border-radius:12px;",
    "min-width:56px;height:50px;cursor:pointer;font-weight:700;display:flex;align-items:center;justify-content:center;}",
    ".clara-send:hover{background:#cf7016;}.clara-send:disabled{opacity:.5;cursor:default;}",
    ".clara-send:focus-visible{outline:3px solid var(--clara-blue-dk);outline-offset:2px;}",
    ".clara-send svg{width:24px;height:24px;}",
    ".clara-hint{font-size:12px;color:#7a8a92;text-align:center;padding:0 12px 10px;background:#fff;}",
    // responsive (mobile = plein écran)
    "@media (max-width:480px){.clara-panel{right:0;left:0;bottom:0;top:0;width:100%;max-width:100%;",
    "height:100%;max-height:100%;border-radius:0;}.clara-launcher{right:16px;bottom:16px;}}",
  ].join("");

  function injectStyle() {
    if (document.getElementById("clara-widget-style")) return;
    var st = document.createElement("style");
    st.id = "clara-widget-style";
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  // ── Icônes (SVG inline) ─────────────────────────────────────────────────────
  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3C6.5 3 2 6.8 2 11.5c0 2.2 1 4.2 2.7 5.7-.1 1.2-.5 2.5-1.4 3.6 1.6-.2 3.1-.8 4.3-1.7 1.3.5 2.8.7 4.4.7 5.5 0 10-3.8 10-8.5S17.5 3 12 3z"/></svg>';
  var ICON_SEND = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3.4 20.4l17.5-7.5c.9-.4.9-1.6 0-2L3.4 3.6c-.7-.3-1.5.3-1.4 1.1L3.5 11l9 1-9 1-1.5 6.3c-.1.8.7 1.4 1.4 1.1z"/></svg>';

  // ── Construction du DOM ──────────────────────────────────────────────────────
  var root, panel, body, input, sendBtn, launcher, typingEl, started = false;

  function el(tag, cls, attrs) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function build() {
    injectStyle();
    root = el("div", "clara-root");

    // Launcher
    launcher = el("button", "clara-launcher", {
      type: "button", "aria-label": "Ouvrir la discussion avec Clara",
      "aria-haspopup": "dialog", "aria-expanded": "false", "aria-controls": "clara-panel"
    });
    launcher.innerHTML = ICON_CHAT;

    // Panel
    panel = el("div", "clara-panel", { id: "clara-panel", role: "dialog", "aria-label": "Assistante Clara", "aria-modal": "false" });

    var header = el("div", "clara-header");
    var logo = el("div", "clara-header__logo");
    if (LOGO) { var img = el("img", null, { src: LOGO, alt: "" }); logo.appendChild(img); }
    else { logo.textContent = "💧"; }
    var htxt = el("div", "clara-header__txt");
    var ht = el("div", "clara-header__title"); ht.textContent = TITLE;
    var hs = el("div", "clara-header__sub"); hs.textContent = SUBTITLE;
    htxt.appendChild(ht); htxt.appendChild(hs);
    var close = el("button", "clara-close", { type: "button", "aria-label": "Fermer la discussion" });
    close.innerHTML = "&times;";
    header.appendChild(logo); header.appendChild(htxt); header.appendChild(close);

    body = el("div", "clara-body", { id: "clara-body", role: "log", "aria-live": "polite", "aria-relevant": "additions", "aria-label": "Conversation avec Clara" });

    typingEl = el("div", "clara-typing", { "aria-hidden": "true" });
    typingEl.innerHTML = "<span></span><span></span><span></span>";
    body.appendChild(typingEl); // toujours présent : addMessage insère avant lui

    var footer = el("div", "clara-footer");
    input = el("textarea", "clara-input", { rows: "1", "aria-label": "Votre message à Clara", placeholder: "Écrivez votre message…" });
    sendBtn = el("button", "clara-send", { type: "button", "aria-label": "Envoyer le message" });
    sendBtn.innerHTML = ICON_SEND;
    footer.appendChild(input); footer.appendChild(sendBtn);

    var hint = el("div", "clara-hint");
    hint.textContent = "Clara peut se tromper. Pour une urgence, contactez l'équipe.";

    panel.appendChild(header); panel.appendChild(body); panel.appendChild(footer); panel.appendChild(hint);
    root.appendChild(launcher); root.appendChild(panel);

    var mount = document.getElementById("clara-widget") || document.body;
    mount.appendChild(root);

    // Public API : ouvrir Clara depuis le site hôte (ex. bouton « Besoin d'aide ? »)
    window.ClaraWidget = {
      open: open, close: close,
      toggle: function () { isOpen() ? close() : open(); },
      send: function (t) { send(t); }
    };

    // Live region for "Clara écrit…" (annonce lecteur d'écran)
    var live = el("div", "clara-sr", { "aria-live": "polite", id: "clara-live" });
    root.appendChild(live);
    root.__live = live;

    wire();
  }

  // ── Messages ────────────────────────────────────────────────────────────────
  function cleanMarkdown(text) {
    // Widget affiche du texte brut : on retire les artefacts Markdown éventuels.
    return String(text)
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/(^|\n)\s*#{1,6}\s*/g, "$1");
  }

  function addMessage(text, who) {
    var cls = who === "user" ? "clara-msg clara-msg--user"
      : who === "err" ? "clara-msg clara-msg--err" : "clara-msg clara-msg--bot";
    var m = el("div", cls);
    m.textContent = who === "user" ? text : cleanMarkdown(text);
    body.insertBefore(m, typingEl);
    scrollDown();
  }

  function addSources(list) {
    var s = el("div", "clara-sources");
    s.textContent = "Sources : " + list.join(", ");
    body.insertBefore(s, typingEl);
    scrollDown();
  }

  function clearSuggestions() {
    var nodes = body.querySelectorAll(".clara-suggestions");
    for (var i = 0; i < nodes.length; i++) nodes[i].remove();
  }

  function addSuggestions(list) {
    if (!list || !list.length) return;
    var box = el("div", "clara-suggestions", { role: "group", "aria-label": "Suggestions" });
    list.forEach(function (label) {
      var b = el("button", "clara-chip", { type: "button" });
      b.textContent = label;
      b.addEventListener("click", function () { send(label); });
      box.appendChild(b);
    });
    body.insertBefore(box, typingEl);
    scrollDown();
  }

  function typeBotMessage(text, onDone) {
    var m = el("div", "clara-msg clara-msg--bot");
    body.insertBefore(m, typingEl);
    var parts = cleanMarkdown(text).split(/(\s+)/);
    var i = 0;
    var step = Math.max(10, Math.min(35, Math.round(700 / Math.max(parts.length, 1))));
    (function tick() {
      if (i < parts.length) {
        m.textContent += parts[i++];
        scrollDown();
        setTimeout(tick, step);
      } else if (onDone) {
        onDone();
      }
    })();
  }

  function scrollDown() { body.scrollTop = body.scrollHeight; }

  function setTyping(on) {
    typingEl.classList.toggle("clara-on", on);
    if (on) scrollDown();
    root.__live.textContent = on ? "Clara est en train d'écrire…" : "";
  }

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }

  // ── Envoi ─────────────────────────────────────────────────────────────────
  var sending = false;
  function send(forced) {
    var text = ((forced != null ? forced : input.value) || "").trim();
    if (!text || sending) return;
    sending = true; sendBtn.disabled = true;
    clearSuggestions();            // les anciens boutons disparaissent dès qu'on agit
    addMessage(text, "user");
    input.value = ""; autoGrow();
    setTyping(true);

    fetch(API_URL + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId() })
    })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        setTyping(false);
        typeBotMessage(data.response || "…", function () {
          if (data.sources && data.sources.length) addSources(data.sources);
          if (data.suggestions && data.suggestions.length) addSuggestions(data.suggestions);
        });
      })
      .catch(function () {
        setTyping(false);
        addMessage("Désolée, je n'arrive pas à répondre pour le moment. Merci de réessayer dans un instant, ou d'écrire à service.client@voyagedo.fr.", "err");
      })
      .then(function () { sending = false; sendBtn.disabled = false; input.focus(); });
  }

  // ── Ouverture / fermeture ────────────────────────────────────────────────────
  function open() {
    panel.classList.add("clara-open");
    launcher.setAttribute("aria-expanded", "true");
    if (!started) {
      started = true;
      typeBotMessage(WELCOME, function () { addSuggestions(STARTER_SUGGESTIONS); });
    }
    setTimeout(function () { input.focus(); }, 60);
  }
  function close() {
    panel.classList.remove("clara-open");
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  }
  function isOpen() { return panel.classList.contains("clara-open"); }

  function wire() {
    launcher.addEventListener("click", function () { isOpen() ? close() : open(); });
    panel.querySelector(".clara-close").addEventListener("click", close);
    sendBtn.addEventListener("click", send);
    input.addEventListener("input", autoGrow);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen()) close();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
