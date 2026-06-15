window.Views = window.Views || {};

window.Views.plan = async function () {
  const { el } = UI;
  let program = null;
  try { program = await API.api("/programs/active"); } catch (e) { if (e.status !== 404) throw e; }

  if (!program) {
    UI.mount(el("div.card.stack", {}, [
      el("h2", { text: "no plan yet" }),
      el("p.muted", { text: "let's build one — it only takes a minute." }),
      el("button.btn.btn-primary", { type: "button", text: "start the intake", onclick: () => Router.go("#/intake") }),
    ]));
    return;
  }

  const week = program.weeks[0];

  function prescription(slot) {
    const ex = slot.exercise || {};
    if (slot.prescribed_target && slot.prescribed_target.duration_min) return slot.prescribed_target.duration_min + " min";
    if (slot.prescribed_target && slot.prescribed_target.work_sec) return slot.prescribed_target.work_sec + "s on / " + slot.prescribed_target.rest_sec + "s off";
    if (slot.prescribed_sets && slot.prescribed_reps) return slot.prescribed_sets + " × " + slot.prescribed_reps;
    return ex.measurement_type || "";
  }

  const rows = (week ? week.slots : []).map((slot) => {
    const ex = slot.exercise || {};
    const right = [el("span.faint", { text: prescription(slot) })];
    return el("div.row", {}, [
      el("div.grow", {}, [
        el("div.name", { text: ex.name || "Exercise" }),
        el("small.faint", { text: (ex.measurement_type || "").replace("_", " ") }),
      ]),
      slot.is_anchor ? el("span.badge.anchor", { text: "anchor" }) : el("span.badge", { text: "rotates" }),
      el("div", {}, right),
    ]);
  });

  async function startWorkout() {
    try {
      const s = await API.api("/sessions", { method: "POST", body: { program_week_id: week.id } });
      Router.go("#/session/" + s.id);
    } catch (e) { UI.toast(e.message); }
  }

  UI.mount(
    el("div.card.stack", {}, [
      el("h1", { text: "your plan" }),
      el("p.muted", { text: program.name + " · week " + (week ? week.week_number : 1) + " of " + program.week_count }),
      el("p.faint", { text: "anchors stay fixed so you can progress them; the rest rotate each week to keep things fresh — your progress tracks across the changes." }),
    ]),
    el("div.card", {}, rows.length ? rows : [el("p.muted", { text: "No exercises this week." })]),
    el("button.btn.btn-primary", { type: "button", text: "start this workout", onclick: startWorkout })
  );
};
