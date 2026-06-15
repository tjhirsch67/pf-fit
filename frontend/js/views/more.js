window.Views = window.Views || {};

window.Views.more = async function () {
  const { el } = UI;
  const me = await API.api("/auth/me");

  const modes = [
    ["guided", "Guided", "zero decisions — we tell you exactly what to do."],
    ["coached", "Coached", "we drive the plan; you can swap and rate difficulty."],
    ["self_directed", "Self-directed", "you customize; we advise on form and plateaus."],
  ];

  function modeRow([key, label, desc]) {
    const active = key === me.autonomy_mode;
    return el("div.row", {}, [
      el("div.grow", {}, [el("div.name", { text: label }), el("small.faint", { text: desc })]),
      active
        ? el("span.badge", { text: "current" })
        : el("button.btn.btn-secondary.btn-sm", { type: "button", text: "switch", onclick: async () => {
            try {
              await API.api("/me/autonomy", { method: "POST", body: { mode: key, trigger: "self_declared" } });
              UI.toast("you're now in " + label.toLowerCase() + " mode");
              Views.more();
            } catch (e) { UI.toast(e.message); }
          } }),
    ]);
  }

  UI.mount(
    el("div.card.hero.stack", {}, [
      el("h1", { text: (me.display_name || "Member").toLowerCase() }),
      el("p", { text: me.email }),
      Views._autonomyPills(me.autonomy_mode),
    ]),
    el("div.card.stack", {}, [
      el("h3", { text: "your autonomy" }),
      el("p.faint", { text: "move at your own pace — advance when you're ready, drop back any time. no gates." }),
    ].concat(modes.map(modeRow))),
    el("div.card.stack", {}, [
      el("h3", { text: "more" }),
      el("button.btn.btn-secondary", { type: "button", text: "fuel & supplements", onclick: () => Router.go("#/nutrition") }),
      el("button.btn.btn-secondary", { type: "button", text: "redo my intake", onclick: () => Router.go("#/intake") }),
    ]),
    el("div.card.stack", {}, [
      el("button.btn.btn-secondary", { type: "button", text: "sign out", onclick: () => { API.clearToken(); Router.go("#/login"); } }),
    ]),
    el("p.center.faint", { text: "PF Coach is a concept demo — not affiliated with, endorsed by, or approved by Planet Fitness. Not medical advice." })
  );
};
