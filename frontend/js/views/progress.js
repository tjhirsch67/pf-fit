window.Views = window.Views || {};

window.Views.progress = async function () {
  const { el, lineChart } = UI;
  const patterns = await API.api("/progress/patterns");
  const prs = await API.api("/progress/prs").catch(() => []);
  const cardio = await API.api("/progress/cardio").catch(() => []);

  const hasData = patterns.some((p) => p.series && p.series.length);

  const blocks = [
    el("div.card.stack", {}, [
      el("h1", { text: "your progress" }),
      el("p.muted", { text: "each line is a movement pattern, indexed to your starting point (100). it stays smooth even as exercises rotate." }),
    ]),
  ];

  if (!hasData) {
    blocks.push(el("div.card", {}, [el("p.muted", { text: "complete a few workouts and your trends will show up here." })]));
  }

  patterns.forEach((p) => {
    if (!p.series || !p.series.length) return;
    const card = el("div.card.stack", { role: "button", tabindex: "0",
      onclick: () => Router.go("#/progress/pattern/" + p.pattern.id) }, [
      el("div.row", {}, [
        el("div.grow", {}, [el("div.name", { text: p.pattern.name })]),
        el("span.badge", { text: Math.round(p.current_index) + "% of start" }),
      ]),
      lineChart(p.series, { baseline100: true, cls: "trend" }),
      el("small.faint", { text: p.exercise_count + " exercises feeding this trend · tap for detail" }),
    ]);
    blocks.push(card);
  });

  // Pin-badge celebration surface.
  const badged = (prs || []).filter((x) => x.pin_badges && x.pin_badges.length);
  if (badged.length) {
    blocks.push(el("div.card.stack", {}, [
      el("h3", { text: "milestones" }),
    ].concat(badged.map((x) =>
      el("div.row", {}, [
        el("div.grow", {}, [el("div.name", { text: x.name })]),
        el("span.badge.anchor", { text: "pin " + x.pin_badges[x.pin_badges.length - 1].to_pin + " 🎉" }),
      ])
    ))));
  }

  // Cardio dashboard (its own track).
  if (cardio && cardio.length) {
    const c = cardio[0];
    blocks.push(el("div.card.stack", {}, [
      el("h3", { text: "cardio" }),
      el("p.faint", { text: c.name }),
      lineChart(c.series, { cls: "cardio" }),
      el("small.faint", { text: "distance per session (meters)" }),
    ]));
  }

  UI.mount.apply(UI, blocks);
};

window.Views.patternDetail = async function (params) {
  const { el, lineChart } = UI;
  const d = await API.api("/progress/patterns/" + params.id);

  const blocks = [
    el("div.card.stack", {}, [
      el("p", {}, [el("a", { href: "#/progress", text: "← all patterns" })]),
      el("h1", { text: d.pattern.name }),
      el("span.badge", { text: Math.round(d.current_index || 0) + "% of start" }),
      lineChart(d.trend, { baseline100: true, cls: "trend" }),
      el("small.faint", { text: "the pattern-trend — continuous across rotation" }),
    ]),
  ];

  d.exercises.forEach((ex) => {
    const badgeIdx = (ex.pin_badges || []).map((b) =>
      ex.series.findIndex((p) => p.date === b.date)).filter((i) => i >= 0);
    blocks.push(el("div.card.stack", {}, [
      el("div.row", {}, [
        el("div.grow", {}, [el("div.name", { text: ex.name })]),
        ex.pin_badges && ex.pin_badges.length
          ? el("span.badge.anchor", { text: ex.pin_badges.length + " pin jump" + (ex.pin_badges.length > 1 ? "s" : "") })
          : el("span.faint", { text: "" }),
      ]),
      lineChart(ex.series.map((p) => ({ date: p.date, value: p.indexed })), { baseline100: true, cls: "spark", badgeIndices: badgeIdx }),
    ]));
  });

  UI.mount.apply(UI, blocks);
};
