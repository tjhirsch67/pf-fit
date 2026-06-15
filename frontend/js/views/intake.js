window.Views = window.Views || {};

window.Views.intake = async function () {
  const { el } = UI;
  const me = await API.api("/auth/me");
  let clubs = [];
  try { clubs = await API.api("/clubs"); } catch (e) {}

  const transcript = [];

  // ── optional coach chat ──
  const chatThread = el("div.chat", {});
  const chatInput = el("input.input", { type: "text", placeholder: "say hi, or ask anything…" });
  function addBubble(role, text) {
    transcript.push(role + ": " + text);
    chatThread.appendChild(el("div.bubble." + (role === "coach" ? "coach" : "me"), { text }));
    chatThread.scrollTop = chatThread.scrollHeight;
  }
  async function sendChat() {
    const msg = chatInput.value.trim();
    if (!msg) return;
    chatInput.value = "";
    addBubble("me", msg);
    const thinking = el("div.bubble.coach", { text: "…" });
    chatThread.appendChild(thinking);
    try {
      const msgs = transcript.map((t) => {
        const i = t.indexOf(": ");
        return { role: t.slice(0, i) === "coach" ? "assistant" : "user", content: t.slice(i + 2) };
      });
      const r = await API.api("/intake/chat", { method: "POST", body: { messages: msgs } });
      thinking.remove();
      addBubble("coach", r.reply);
    } catch (e) {
      thinking.remove();
      UI.toast(e.status === 503 ? "coach chat needs the AI key configured" : e.message);
    }
  }

  // ── structured fields ──
  const goal = el("input.input", { type: "text", placeholder: "e.g. feel stronger, lose a bit of weight" });
  const experience = el("select.input", {}, [
    el("option", { value: "beginner", text: "brand new" }),
    el("option", { value: "intermediate", text: "some experience" }),
    el("option", { value: "advanced", text: "very experienced" }),
  ]);
  const days = el("select.input", {}, ["2", "3", "4", "5", "6"].map((d) =>
    el("option", { value: d, text: d + " days / week" })));
  days.value = "3";
  const confidence = el("select.input", {}, [
    el("option", { value: "nervous", text: "pretty nervous — I don't know the machines" }),
    el("option", { value: "okay", text: "okay — I've been before" }),
    el("option", { value: "confident", text: "confident — I know my way around" }),
  ]);
  const clubSelect = el("select.input", {}, clubs.map((c) =>
    el("option", { value: c.id, text: c.name })));
  if (me.home_club_id) clubSelect.value = me.home_club_id;

  const submitBtn = el("button.btn.btn-primary", { type: "button", text: "build my plan" });
  const result = el("div", {});

  submitBtn.onclick = async function () {
    const clubId = clubSelect.value || null;
    submitBtn.disabled = true;
    result.replaceChildren(UI.spinner(), el("p.center.faint", { text: "your coach is reading your answers…" }));
    try {
      if (clubId && clubId !== me.home_club_id) {
        await API.api("/me", { method: "PATCH", body: { home_club_id: clubId } });
      }
      const answers = { goal: goal.value.trim(), experience: experience.value,
        days_per_week: parseInt(days.value, 10), confidence: confidence.value };
      const r = await API.api("/intake/submit", { method: "POST",
        body: { answers, club_id: clubId, transcript: transcript.join("\n") || null, generate_program: true } });
      const pl = r.placement || {};
      result.replaceChildren(
        el("div.card.hero.stack", {}, [
          el("h2", { text: "you're all set" }),
          Views._autonomyPills(pl.recommended_mode),
          el("p", { text: pl.rationale || "" }),
        ]),
        el("button.btn.btn-primary", { type: "button", text: "go to my plan", onclick: () => Router.go("#/today") })
      );
    } catch (e) {
      submitBtn.disabled = false;
      result.replaceChildren(el("div.notice", { text:
        e.status === 503 ? "The AI key isn't configured on the server, so placement can't run right now."
                         : (e.message || "Couldn't build your plan.") }));
    }
  };

  UI.mount(
    el("div.card.hero.stack", {}, [
      el("h1", { text: "let's keep it simple" }),
      el("p", { text: "a few quick questions and we'll place you on the right starting point. you can change everything later." }),
    ]),
    el("div.card.stack", {}, [
      el("h3", { text: "talk to your coach (optional)" }),
      chatThread,
      el("div.btn-row", {}, [chatInput, el("button.btn.btn-secondary.btn-sm", { type: "button", text: "send", onclick: sendChat })]),
    ]),
    el("div.card.stack", {}, [
      el("h3", { text: "the essentials" }),
      el("div.field", {}, [el("label", { text: "your goal" }), goal]),
      el("div.field", {}, [el("label", { text: "experience" }), experience]),
      el("div.field", {}, [el("label", { text: "days per week" }), days]),
      el("div.field", {}, [el("label", { text: "how confident do you feel?" }), confidence]),
      clubs.length ? el("div.field", {}, [el("label", { text: "your club" }), clubSelect]) : null,
      submitBtn,
    ]),
    result
  );
};
