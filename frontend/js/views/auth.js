window.Views = window.Views || {};

window.Views.login = async function () {
  const { el } = UI;
  let mode = "login"; // 'login' | 'register'

  function render() {
    const email = el("input.input", { type: "email", placeholder: "you@email.com", autocomplete: "email" });
    const password = el("input.input", { type: "password", placeholder: "at least 8 characters", autocomplete: "current-password" });
    const name = el("input.input", { type: "text", placeholder: "your name (optional)" });
    const err = el("p.faint", { text: "" });

    async function submit() {
      err.textContent = "";
      const body = { email: email.value.trim(), password: password.value };
      try {
        if (mode === "register") {
          if (name.value.trim()) body.display_name = name.value.trim();
          const r = await API.api("/auth/register", { method: "POST", body, auth: false });
          API.setToken(r.access_token);
          Router.go("#/intake");
        } else {
          const r = await API.api("/auth/login", { method: "POST", body, auth: false });
          API.setToken(r.access_token);
          Router.go("#/today");
        }
      } catch (e) {
        err.textContent = e.message || "Could not sign in.";
      }
    }

    async function demo() {
      err.textContent = "";
      try {
        const r = await API.api("/auth/login", { method: "POST", auth: false,
          body: { email: "demo@pfcoach.app", password: "demo1234" } });
        API.setToken(r.access_token);
        Router.go("#/today");
      } catch (e) { err.textContent = "Demo unavailable: " + e.message; }
    }

    const fields = [
      el("div.field", {}, [el("label", { text: "email" }), email]),
    ];
    if (mode === "register") fields.push(el("div.field", {}, [el("label", { text: "name" }), name]));
    fields.push(el("div.field", {}, [el("label", { text: "password" }), password]));

    UI.mount(
      el("div.card.hero.stack", {}, [
        el("h1", { text: mode === "login" ? "welcome back" : "let's get you started" }),
        el("p", { text: "no experience needed — we'll walk you onto the floor, one step at a time." }),
      ]),
      el("div.card", {}, fields.concat([
        el("button.btn.btn-primary", { onclick: submit, type: "button",
          text: mode === "login" ? "sign in" : "create account" }),
        err,
        el("p.center.muted", { style: "margin-top:8px" }, [
          el("a", { href: "javascript:void 0", onclick: () => { mode = mode === "login" ? "register" : "login"; render(); },
            text: mode === "login" ? "new here? create an account" : "already have an account? sign in" }),
        ]),
      ])),
      el("div.card.center", {}, [
        el("p.muted", { text: "just want to look around?" }),
        el("button.btn.btn-secondary", { onclick: demo, type: "button", text: "explore the demo" }),
      ]),
      el("p.center.faint", { text: "a concept demo — not affiliated with Planet Fitness. not medical advice." })
    );
  }

  render();
};
