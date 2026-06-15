// DOM helpers, outline icons, toast, and a small flat SVG line-chart builder.
// No innerHTML anywhere — nodes are built via DOM APIs / DOMParser (trusted static SVG only).
(function () {
  const SVGNS = "http://www.w3.org/2000/svg";

  // el("div.card#id", {onclick, text, ...attrs}, [children|"text"])
  function el(spec, attrs, children) {
    const m = spec.match(/^([a-z0-9]+)?(#[\w-]+)?((?:\.[\w-]+)*)$/i) || [];
    const tag = m[1] || "div";
    const node = document.createElement(tag);
    if (m[2]) node.id = m[2].slice(1);
    if (m[3]) node.className = m[3].split(".").filter(Boolean).join(" ");
    attrs = attrs || {};
    for (const k in attrs) {
      if (k === "text") node.textContent = attrs[k];
      else if (k.startsWith("on") && typeof attrs[k] === "function") node.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] != null && attrs[k] !== false) node.setAttribute(k, attrs[k]);
    }
    (children == null ? [] : [].concat(children)).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function empty(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function clearView() { return empty(document.getElementById("view")); }
  function mount() { const v = clearView(); [].slice.call(arguments).forEach((n) => n && v.appendChild(n)); return v; }
  function spinner() { return el("div.spinner", { "aria-label": "Loading" }); }

  let toastTimer = null;
  function toast(msg) {
    document.querySelectorAll(".toast").forEach((t) => t.remove());
    const t = el("div.toast", { text: msg });
    document.body.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.remove(), 2600);
  }

  // Parse a trusted, static SVG string into a DOM node (no innerHTML).
  function svgFromString(markup) {
    const doc = new DOMParser().parseFromString(markup, "image/svg+xml");
    return document.importNode(doc.documentElement, true);
  }

  // Outline icons (Lucide-style), inherit currentColor. No PF emblem/gear/thumbs-up.
  const ICONS = {
    today: '<path d="M3 9h18M7 3v4M17 3v4M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/>',
    plan: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    progress: '<path d="M3 3v18h18M7 14l4-4 3 3 5-6"/>',
    more: '<circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/><circle cx="5" cy="12" r="1.4"/>',
    play: '<path d="M6 4l14 8-14 8z" fill="currentColor" stroke="none"/>',
    swap: '<path d="M16 3l4 4-4 4M20 7H8M8 21l-4-4 4-4M4 17h12"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    dumbbell: '<path d="M6 7v10M18 7v10M3 9v6M21 9v6M6 12h12"/>',
  };
  function icon(name, size) {
    const s = size || 22;
    const markup =
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="${s}" height="${s}" ` +
      `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ` +
      `aria-hidden="true">${ICONS[name] || ""}</svg>`;
    return svgFromString(markup);
  }

  // Flat line chart -> SVG element built via createElementNS. series: [{date, value}].
  function lineChart(series, opts) {
    opts = opts || {};
    const W = 320, H = 150, padL = 30, padR = 10, padT = 12, padB = 22;
    const svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "chart");
    svg.setAttribute("role", "img");

    function txt(x, y, s, cls) {
      const t = document.createElementNS(SVGNS, "text");
      t.setAttribute("x", x); t.setAttribute("y", y); t.setAttribute("class", cls || "axis-lbl");
      t.textContent = s; return t;
    }

    if (!series || series.length === 0) {
      const t = txt(W / 2, H / 2, "No data yet"); t.setAttribute("text-anchor", "middle");
      svg.appendChild(t); return svg;
    }

    const vals = series.map((p) => p.value);
    let min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    if (opts.baseline100) min = Math.min(min, 100);
    if (max === min) max = min + 1;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const x = (i) => padL + (series.length === 1 ? plotW / 2 : (i / (series.length - 1)) * plotW);
    const y = (v) => padT + plotH - ((v - min) / (max - min)) * plotH;

    if (opts.baseline100) {
      const g = document.createElementNS(SVGNS, "line");
      g.setAttribute("x1", padL); g.setAttribute("x2", W - padR);
      g.setAttribute("y1", y(100)); g.setAttribute("y2", y(100)); g.setAttribute("class", "grid");
      svg.appendChild(g);
      svg.appendChild(txt(2, y(100) + 3, "100"));
    }

    const d = series.map((p, i) => (i === 0 ? "M" : "L") + x(i).toFixed(1) + " " + y(p.value).toFixed(1)).join(" ");
    const path = document.createElementNS(SVGNS, "path");
    path.setAttribute("d", d); path.setAttribute("class", opts.cls || "trend");
    svg.appendChild(path);

    (opts.badgeIndices || []).forEach((i) => {
      if (i < 0 || i >= series.length) return;
      const c = document.createElementNS(SVGNS, "circle");
      c.setAttribute("cx", x(i)); c.setAttribute("cy", y(series[i].value)); c.setAttribute("r", 3.5);
      c.setAttribute("class", "pr"); svg.appendChild(c);
    });
    return svg;
  }

  function fmtDate(iso) {
    try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }); }
    catch (e) { return iso; }
  }

  window.UI = { el, empty, clearView, mount, spinner, toast, icon, svgFromString, lineChart, fmtDate };
})();
