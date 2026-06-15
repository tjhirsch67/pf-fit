window.Views = window.Views || {};

let _circuitTimer = null;
function _clearTimer() { if (_circuitTimer) { clearInterval(_circuitTimer); _circuitTimer = null; } }

window.Views.session = async function (params) {
  _clearTimer();
  const s = await API.api("/sessions/" + params.id);
  try { await API.api("/sessions/" + params.id + "/start", { method: "POST" }); } catch (e) {}
  if (s.session_type === "express_circuit") renderCircuit(s);
  else renderStandard(s);
};

async function finishSession(id) {
  _clearTimer();
  try {
    await API.api("/sessions/" + id + "/complete", { method: "POST" });
    UI.toast("nice work — workout logged!");
    Router.go("#/progress");
  } catch (e) { UI.toast(e.message); }
}

// ─── Standard: per-exercise station cards with set logging ────────────────────
function renderStandard(s) {
  const { el } = UI;

  function inputsFor(mt) {
    if (mt === "selectorized")
      return { pin: el("input.input", { type: "number", inputmode: "numeric", placeholder: "pin #" }),
               reps: el("input.input", { type: "number", inputmode: "numeric", placeholder: "reps" }) };
    if (mt === "plate_loaded" || mt === "smith")
      return { weight_value: el("input.input", { type: "number", inputmode: "decimal", placeholder: "lbs" }),
               reps: el("input.input", { type: "number", inputmode: "numeric", placeholder: "reps" }) };
    if (mt === "cardio")
      return { duration_min: el("input.input", { type: "number", inputmode: "numeric", placeholder: "minutes" }),
               distance_value: el("input.input", { type: "number", inputmode: "decimal", placeholder: "miles" }) };
    return { reps: el("input.input", { type: "number", inputmode: "numeric", placeholder: "reps" }) };
  }

  function stationCard(sx) {
    const ex = sx.exercise || {};
    const count = el("small.faint", { text: sx.sets.length + " set(s) logged" });
    const fields = inputsFor(sx.measurement_type);
    const inputWrap = el("div.btn-row", {}, Object.keys(fields).map((k) => fields[k]));

    async function logSet() {
      const body = {};
      if (sx.measurement_type === "cardio") {
        if (fields.duration_min.value) body.duration_seconds = Math.round(parseFloat(fields.duration_min.value) * 60);
        if (fields.distance_value.value) { body.distance_value = parseFloat(fields.distance_value.value); body.distance_unit = "mi"; }
      } else {
        for (const k in fields) if (fields[k].value !== "") body[k] = parseFloat(fields[k].value);
      }
      if (!Object.keys(body).length) { UI.toast("enter your numbers first"); return; }
      try {
        const updated = await API.api("/sessions/" + s.id + "/exercises/" + sx.id + "/sets", { method: "POST", body });
        sx.sets = updated.sets;
        count.textContent = sx.sets.length + " set(s) logged";
        for (const k in fields) fields[k].value = "";
        UI.toast("set logged ✓");
      } catch (e) { UI.toast(e.message); }
    }

    async function doSwap() {
      try {
        const opts = await API.api("/sessions/" + s.id + "/exercises/" + sx.id + "/swap-options");
        if (!opts.length) { UI.toast("no alternatives available at this club"); return; }
        const chooser = el("div.stack", {}, opts.slice(0, 5).map((o) =>
          el("button.btn.btn-secondary", { type: "button", text: "→ " + o.name, onclick: async () => {
            try {
              await API.api("/sessions/" + s.id + "/exercises/" + sx.id + "/swap",
                { method: "POST", body: { to_exercise_id: o.id, reason: "preference" } });
              UI.toast("swapped to " + o.name);
              Views.session({ id: s.id });
            } catch (e) { UI.toast(e.message); }
          } })
        ));
        body.replaceChild(chooser, actions);
      } catch (e) { UI.toast(e.message); }
    }

    const actions = el("div.btn-row", {}, [
      el("button.btn.btn-primary.btn-sm", { type: "button", text: "log set", onclick: logSet }),
      el("button.btn.btn-secondary.btn-sm", { type: "button", text: "swap", onclick: doSwap }),
    ]);

    const thumb = el("a.thumb", { href: ex.video_url || "#", target: "_blank", rel: "noopener" }, [
      el("span.play", {}, [UI.icon("play", 22)]),
    ]);

    const prescribed = sx.prescribed && sx.prescribed.sets
      ? sx.prescribed.sets + " × " + (sx.prescribed.reps || "—")
      : (sx.measurement_type || "").replace("_", " ");

    const body = el("div.body.stack", {}, [
      el("div.name", { text: ex.name || "Exercise" }),
      el("span.chip", { text: prescribed }),
      inputWrap,
      actions,
      count,
    ]);

    return el("div.card.flush.station", {}, [thumb, body]);
  }

  UI.mount.apply(UI, [
    el("div.card.stack", {}, [
      el("h1", { text: "today's workout" }),
      el("p.muted", { text: s.exercises.length + " exercises · log what you do, swap anything that's taken." }),
    ]),
  ].concat(s.exercises.map(stationCard)).concat([
    el("button.btn.btn-primary", { type: "button", text: "finish workout", onclick: () => finishSession(s.id) }),
  ]));
}

// ─── Express Circuit: the guided money shot with the traffic-light timer ──────
function renderCircuit(s) {
  const { el } = UI;
  const stations = s.exercises;
  let idx = 0;

  const WORK = 60, REST = 30;
  let phase = "work", remaining = WORK;

  const view = UI.clearView();

  function paint() {
    UI.empty(view);
    if (idx >= stations.length) {
      view.appendChild(el("div.card.hero.stack.center", {}, [
        el("h1", { text: "circuit complete!" }),
        el("p", { text: "you moved through every station. that's a full workout." }),
      ]));
      view.appendChild(el("button.btn.btn-primary", { type: "button", text: "finish & save", onclick: () => finishSession(s.id) }));
      return;
    }
    const sx = stations[idx];
    const ex = sx.exercise || {};
    const isWork = phase === "work";

    const timer = el("div.timer" + (isWork ? "" : ".rest"), {}, [
      el("span.label", { text: isWork ? "GO" : "SWITCH" }),
      document.createTextNode(remaining + "s"),
    ]);

    function advance() {
      phase = "work"; remaining = WORK; idx += 1; paint();
    }

    view.appendChild(el("div.card.stack", {}, [
      el("span.faint", { text: "station " + (idx + 1) + " of " + stations.length }),
      el("h1", { text: ex.name || "Station" }),
    ]));
    view.appendChild(el("div.card.flush.station", {}, [
      el("a.thumb", { href: ex.video_url || "#", target: "_blank", rel: "noopener" }, [el("span.play", {}, [UI.icon("play", 24)])]),
      el("div.body.stack", {}, [
        el("span.chip", { text: "follow the pacing — green means go, red means switch" }),
        timer,
        el("div.btn-row", {}, [
          el("button.btn.btn-primary.btn-sm", { type: "button", text: "done — next", onclick: advance }),
          el("button.btn.btn-secondary.btn-sm", { type: "button", text: "skip", onclick: advance }),
        ]),
      ]),
    ]));
  }

  function tick() {
    remaining -= 1;
    if (remaining <= 0) {
      if (phase === "work") { phase = "transition"; remaining = REST; }
      else { phase = "work"; remaining = WORK; idx += 1; }
      paint();
      return;
    }
    const t = view.querySelector(".timer");
    if (t) {
      // update just the trailing seconds text node
      t.lastChild.textContent = remaining + "s";
    }
  }

  paint();
  _clearTimer();
  _circuitTimer = setInterval(tick, 1000);
}
