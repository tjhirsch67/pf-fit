// Minimal hash router with :params, auth guards, and bottom-tab management.
(function () {
  // pattern, view name (window.Views[name]), auth required, tab id to highlight (or null = hide tabbar)
  const ROUTES = [
    { p: "/login", v: "login", auth: false, tab: null },
    { p: "/intake", v: "intake", auth: true, tab: null },
    { p: "/today", v: "today", auth: true, tab: "today" },
    { p: "/plan", v: "plan", auth: true, tab: "plan" },
    { p: "/session/:id", v: "session", auth: true, tab: null },
    { p: "/progress", v: "progress", auth: true, tab: "progress" },
    { p: "/progress/pattern/:id", v: "patternDetail", auth: true, tab: "progress" },
    { p: "/nutrition", v: "nutrition", auth: true, tab: "more" },
    { p: "/more", v: "more", auth: true, tab: "more" },
  ];

  function match(path) {
    for (const r of ROUTES) {
      const rp = r.p.split("/"), pp = path.split("/");
      if (rp.length !== pp.length) continue;
      const params = {};
      let ok = true;
      for (let i = 0; i < rp.length; i++) {
        if (rp[i].startsWith(":")) params[rp[i].slice(1)] = decodeURIComponent(pp[i]);
        else if (rp[i] !== pp[i]) { ok = false; break; }
      }
      if (ok) return { route: r, params };
    }
    return null;
  }

  function setTab(tab) {
    const bar = document.querySelector(".tabbar");
    if (!tab) { bar.classList.add("hidden"); return; }
    bar.classList.remove("hidden");
    bar.querySelectorAll("a").forEach((a) => {
      a.classList.toggle("active", a.getAttribute("data-tab") === tab);
    });
  }

  async function render() {
    let path = (location.hash || "").replace(/^#/, "") || "/";
    if (path === "/") path = window.API.isAuthed() ? "/today" : "/login";

    const m = match(path);
    if (!m) { location.hash = window.API.isAuthed() ? "#/today" : "#/login"; return; }

    if (m.route.auth && !window.API.isAuthed()) { location.hash = "#/login"; return; }
    if (!m.route.auth && m.route.v === "login" && window.API.isAuthed()) { location.hash = "#/today"; return; }

    setTab(m.route.tab);
    const view = window.Views[m.route.v];
    UI.mount(UI.spinner());
    try {
      await view(m.params);
    } catch (e) {
      if (e instanceof window.API.ApiError && e.status === 401) return; // already redirected
      UI.mount(UI.el("div.card", {}, [
        UI.el("h2", { text: "Something went wrong" }),
        UI.el("p.muted", { text: (e && e.message) || "Please try again." }),
      ]));
    }
    window.scrollTo(0, 0);
  }

  function go(hash) { location.hash = hash; }

  window.Router = { go, render };
  window.addEventListener("hashchange", render);
  window.addEventListener("DOMContentLoaded", render);
})();
