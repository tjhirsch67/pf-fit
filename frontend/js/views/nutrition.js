window.Views = window.Views || {};

window.Views.nutrition = async function () {
  const { el } = UI;
  const meals = await API.api("/nutrition/meals").catch(() => []);
  const supps = await API.api("/nutrition/supplements").catch(() => []);

  const today = new Date().getDay();
  const todayMeal = meals.find((m) => m.day_of_week === today) || meals[0];

  const blocks = [
    el("div.card.stack", {}, [
      el("h1", { text: "fuel" }),
      el("p.muted", { text: "simple meal ideas and supplements to support your training. suggestions only — not a meal plan." }),
    ]),
  ];

  if (todayMeal) {
    blocks.push(el("div.card.stack", {}, [
      el("span.badge", { text: "today's idea" }),
      el("h3", { text: todayMeal.title }),
      el("p.muted", { text: todayMeal.description || "" }),
      todayMeal.link_url ? el("a", { href: todayMeal.link_url, target: "_blank", rel: "noopener", text: "see the recipe →" }) : null,
    ]));
  }

  if (meals.length) {
    blocks.push(el("div.card.stack", {}, [el("h3", { text: "this week" })].concat(
      meals.map((m) => el("div.row", {}, [
        el("div.grow", {}, [el("div.name", { text: m.title }), el("small.faint", { text: m.description || "" })]),
      ]))
    )));
  }

  if (supps.length) {
    blocks.push(el("div.card.stack", {}, [el("h3", { text: "supplements" })].concat(
      supps.map((sp) => el("div.row", {}, [
        el("div.grow", {}, [el("div.name", { text: sp.name }), el("small.faint", { text: sp.description || "" })]),
        sp.link_url ? el("a", { href: sp.link_url, target: "_blank", rel: "noopener", text: "shop" }) : null,
      ]))
    )));
  }

  blocks.push(el("p.center.faint", { text: "Some links may be affiliate links. Not medical or nutritional advice." }));
  UI.mount.apply(UI, blocks);
};
