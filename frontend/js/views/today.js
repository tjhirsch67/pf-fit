window.Views = window.Views || {};

window.Views._autonomyPills = function (mode) {
  const { el } = UI;
  const modes = [["guided", "Guided"], ["coached", "Coached"], ["self_directed", "Self-directed"]];
  return el("div.autonomy", {}, modes.map(([k, label]) =>
    el("div.pill" + (k === mode ? ".active" : ""), { text: label })
  ));
};

window.Views.today = async function () {
  const { el } = UI;
  const me = await API.api("/auth/me");
  const consistency = await API.api("/me/consistency");

  let program = null;
  try { program = await API.api("/programs/active"); } catch (e) { if (e.status !== 404) throw e; }

  const firstName = (me.display_name || "there").split(" ")[0].toLowerCase();
  const streakPct = Math.min(100, (consistency.current_streak_days / 7) * 100);

  let actionCard;
  if (!program) {
    actionCard = el("div.card.stack", {}, [
      el("h2", { text: "let's build your plan" }),
      el("p.muted", { text: "answer a few quick questions and we'll set you up with a plan built for the machines at your club." }),
      el("button.btn.btn-primary", { type: "button", text: "start the intake", onclick: () => Router.go("#/intake") }),
    ]);
  } else {
    const week = program.weeks[0];
    const count = week ? week.slots.length : 0;
    async function start(type) {
      try {
        const body = type === "express_circuit"
          ? { session_type: "express_circuit" }
          : { program_week_id: week.id };
        const s = await API.api("/sessions", { method: "POST", body });
        Router.go("#/session/" + s.id);
      } catch (e) { UI.toast(e.message); }
    }
    const buttons = [
      el("button.btn.btn-primary", { type: "button", text: "start today's workout", onclick: () => start("standard") }),
    ];
    if (me.autonomy_mode === "guided") {
      buttons.push(el("button.btn.btn-secondary", { type: "button", text: "try the 30-min Express Circuit", onclick: () => start("express_circuit") }));
    }
    actionCard = el("div.card.stack", {}, [
      el("h2", { text: "today's workout" }),
      el("p.muted", { text: program.name + " · week " + (week ? week.week_number : 1) + " · " + count + " exercises" }),
    ].concat(buttons).concat([
      el("p.center", {}, [el("a", { href: "#/plan", text: "see the full plan" })]),
    ]));
  }

  UI.mount(
    el("div.card.hero.stack", {}, [
      el("h1", { text: "nice to see you, " + firstName }),
      el("p", { text: "you're in " + me.autonomy_mode.replace("_", "-") + " mode — we'll keep you moving." }),
      Views._autonomyPills(me.autonomy_mode),
    ]),
    el("div.card", {}, [
      el("div.streak", {}, [
        el("span.badge.go", { text: consistency.current_streak_days + "🔥" }),
        el("div.bar", {}, [el("span", { style: "width:" + streakPct + "%" })]),
      ]),
      el("p.faint", { style: "margin:8px 0 0", text: "build a streak and we'll invite you to start customizing — no pressure." }),
    ]),
    el("div.tiles", {}, [
      el("div.tile", {}, [el("div.num", { text: String(consistency.completed_total) }), el("div.lbl", { text: "workouts done" })]),
      el("div.tile", {}, [el("div.num", { text: String(consistency.completed_this_month) }), el("div.lbl", { text: "this month" })]),
    ]),
    actionCard
  );
};
