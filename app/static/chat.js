(() => {
  const $ = (id) => document.getElementById(id);
  const app = document.querySelector(".app");
  const scroll = $("scroll"), log = $("log"), form = $("form"), input = $("input"), send = $("send");
  const name = document.querySelector(".who h1").textContent;
  const KEY = "rory-web-log-v2";
  const status = $("status");
  let statusTimer;
  const say_ = (t) => { clearTimeout(statusTimer); status.textContent = ""; statusTimer = setTimeout(() => { status.textContent = t; }, 50); };   // re-set so repeats are announced
  const hush = () => { clearTimeout(statusTimer); status.textContent = ""; };
  let busy = false;
  let stick = true;                                       // follow the newest message until the visitor scrolls up to read
  const follow = () => { if (stick) scroll.scrollTop = scroll.scrollHeight; };
  // Only the visitor's own scrolling decides whether to keep following: content growing underneath the view also fires scroll events.
  let touched = 0;
  for (const type of ["wheel", "touchstart", "touchmove", "touchend", "pointerdown", "keydown"]) scroll.addEventListener(type, () => { touched = performance.now(); }, { passive: true });
  scroll.addEventListener("scroll", () => {
    const gap = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight;
    if (gap < 8) stick = true;
    else if (performance.now() - touched < 1000) stick = gap < 80;
  }, { passive: true });
  // Anything that changes the size of the conversation or of its viewport (a reply's Copy button, the quick-reply row, the typeahead,
  // late-loading emoji, the keyboard) re-pins the view, so the last message is never left half under the controls.
  new ResizeObserver(follow).observe($("log"));
  new ResizeObserver(follow).observe(scroll);
  let history = [];
  const quick = $("quick"), suggest = $("suggest");
  const examples = (() => { try { return JSON.parse($("examples").textContent); } catch { return []; } })();
  const AMOUNT = /(^|\s)\d+(?:\.\d+)?(?=\s|$)/;                  // a standalone number: "100 usd to pkr", not "2:255" or "roll 2d6"
  const sent = [];                                  // what this visitor typed, for the up arrow
  let recall = -1, active = -1, shown = [];

  const ALLOWED = new Set(["STRONG", "EM", "S", "A", "BR"]);
  function clean(html) {                                  // restored markup is only ever what the server rendered; trim it to that anyway
    const t = document.createElement("template");
    t.innerHTML = html;
    t.content.querySelectorAll("*").forEach((el) => {
      if (!ALLOWED.has(el.tagName)) { el.replaceWith(document.createTextNode(el.textContent)); return; }
      [...el.attributes].forEach((a) => {
        const ok = el.tagName === "A" && ((a.name === "href" && /^https?:\/\//i.test(a.value)) || a.name === "target" || a.name === "rel");
        if (!ok) el.removeAttribute(a.name);
      });
    });
    return t.innerHTML;
  }

  const load = () => { try { return JSON.parse(sessionStorage.getItem(KEY)) || []; } catch { return []; } };
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify(history.slice(-60))); } catch { /* storage may be blocked */ } };

  const clock = new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit" });

  function stamp(li, ts) {
    const t = document.createElement("time");
    t.dateTime = new Date(ts).toISOString();
    t.textContent = clock.format(ts);
    t.title = new Date(ts).toLocaleString();
    li.append(t);
  }

  function bubble(role, html, extra = "", ts = null, label = "") {
    const li = document.createElement("li");
    li.className = `msg ${role} ${extra}`.trim();
    if (role === "bot") { const n = document.createElement("span"); n.className = "name"; const av = document.createElement("span"); av.className = "av"; av.append(document.querySelector(".mark svg").cloneNode(true)); n.append(av, name); if (label) { const tl = document.createElement("span"); tl.className = "tool"; tl.textContent = label; n.append(tl); } li.append(n); }
    const t = document.createElement("div");
    t.className = "text";
    t.innerHTML = html;                       // only ever server-rendered, escaped markup, or text we escaped below
    li.append(t);
    if (ts) stamp(li, ts);
    log.append(li);
    app.classList.add("started");
    if (role === "me") stick = true;
    follow();
    return li;
  }
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const starters = [...document.querySelectorAll(".intro [data-say]")].map((b) => b.dataset.say);
  let turn = 0;
  const ideas = (said) => { const pool = starters.filter((x) => x !== said); return pool.map((_, i) => pool[(turn + i) % pool.length]).slice(0, 3); };
  function rotatePlaceholder() { if (starters.length) input.placeholder = `Try: ${starters[turn % starters.length]}`; }

  // Examples are starting points: they fill the box (number selected, ready to overtype) instead of sending. Actions ("again", "quit", "help") send at once.
  function fill(text) {
    input.value = text; send.disabled = busy || !text.trim(); hideSuggest(); input.focus();
    const m = AMOUNT.exec(text);
    if (m) { const at = m.index + m[1].length; input.setSelectionRange(at, at + m[0].length - m[1].length); } else input.setSelectionRange(text.length, text.length);
  }

  function setQuick(items, asExamples = false) {
    quick.replaceChildren(...(items || []).map((t) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = t; b.addEventListener("click", () => (asExamples ? fill(t) : say(t)));
      return b;
    }));
  }

  function addCopy(li, text) {
    if (!navigator.clipboard) return;
    const b = document.createElement("button");
    b.type = "button"; b.className = "copy"; b.textContent = "Copy";
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; } catch { b.textContent = "Couldn't copy"; }
      say_(b.textContent);
      setTimeout(() => { b.textContent = "Copy"; }, 1500);
    });
    li.append(b);
  }

  function hideSuggest() { suggest.hidden = true; quick.hidden = false; input.setAttribute("aria-expanded", "false"); active = -1; input.removeAttribute("aria-activedescendant"); }
  function pick(i) { input.value = shown[i]; hideSuggest(); send.disabled = false; input.focus(); }
  function showSuggest() {
    const q = input.value.trim().toLowerCase();
    const typed = (q.match(AMOUNT) || [])[0]?.trim();                  // the number the visitor is typing, e.g. "786"
    const pool = [...new Set(examples.map((e) => (typed && e.amount && AMOUNT.test(e.text) ? e.text.replace(AMOUNT, (_, pre) => pre + typed) : e.text)))];
    shown = q.length < 2 ? [] : pool.filter((e) => e.toLowerCase().includes(q) && e.toLowerCase() !== q)
      .sort((a, b) => a.toLowerCase().indexOf(q) - b.toLowerCase().indexOf(q)).slice(0, matchMedia("(max-width: 40rem)").matches ? 3 : 5);
    if (!shown.length) return hideSuggest();
    suggest.replaceChildren(...shown.map((e, i) => {
      const li = document.createElement("li");
      li.id = `s${i}`; li.setAttribute("role", "option"); li.setAttribute("aria-selected", "false");
      const at = e.toLowerCase().indexOf(q);
      li.append(e.slice(0, at));
      const m = document.createElement("mark"); m.textContent = e.slice(at, at + q.length); li.append(m, e.slice(at + q.length));
      li.addEventListener("mousedown", (ev) => { ev.preventDefault(); pick(i); });
      return li;
    }));
    suggest.hidden = false; quick.hidden = true; active = -1; input.setAttribute("aria-expanded", "true");
    say_(`${shown.length} suggestion${shown.length > 1 ? "s" : ""}`);
  }
  function mark(i) {
    active = i;
    [...suggest.children].forEach((li, n) => li.setAttribute("aria-selected", String(n === i)));
    if (i >= 0) input.setAttribute("aria-activedescendant", `s${i}`); else input.removeAttribute("aria-activedescendant");
  }

  function setBusy(v) { busy = v; send.disabled = v || !input.value.trim(); }

  async function say(text) {
    if (busy || !text.trim()) return;
    text = text.trim();
    bubble("me", esc(text), "", Date.now());
    history.push({ role: "me", text, ts: Date.now() });
    sent.push(text); turn++; rotatePlaceholder(); recall = -1; hideSuggest(); setQuick([]);
    input.value = ""; setBusy(true);
    const typing = bubble("bot", "<i></i><i></i><i></i>", "typing");
    typing.setAttribute("aria-hidden", "true");
    say_(`${name} is typing`);
    try {
      const res = await fetch("chat/message", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      const data = await res.json().catch(() => ({}));
      typing.remove();
      if (res.ok && data.ok) { const ts = Date.now(), li = bubble("bot", data.html, "", ts, data.label || ""); addCopy(li, data.text); history.push({ role: "bot", html: data.html, ts, label: data.label || "" }); hush(); data.suggestions && data.suggestions.length ? setQuick(data.suggestions) : setQuick(ideas(text), true); }
      else fail(data.error || "Something went wrong on my side. Try again.", text);
    } catch {
      typing.remove();
      fail("Can't reach " + name + " right now. Check your connection.", text);
    }
    save(); setBusy(false); input.focus({ preventScroll: true });
  }

  function fail(message, text) {
    hush();
    const li = bubble("bot", esc(message), "error");
    const b = document.createElement("button");
    b.type = "button"; b.className = "ghost retry"; b.textContent = "Try again";
    b.onclick = () => { input.focus(); li.remove(); history = history.filter((h) => h.text !== text || h.role !== "me"); say(text); };
    li.append(b);
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); say(input.value); });
  input.addEventListener("input", () => { send.disabled = busy || !input.value.trim(); showSuggest(); });
  input.addEventListener("blur", hideSuggest);
  input.addEventListener("keydown", (e) => {
    if (!suggest.hidden) {
      if (e.key === "ArrowDown") { e.preventDefault(); return mark((active + 1) % shown.length); }
      if (e.key === "ArrowUp") { e.preventDefault(); return mark((active - 1 + shown.length) % shown.length); }
      if ((e.key === "Tab" || e.key === "Enter") && active >= 0) { e.preventDefault(); return pick(active); }
      if (e.key === "Tab") return hideSuggest();                  // no option chosen: let focus move on
      if (e.key === "Escape") { e.preventDefault(); return hideSuggest(); }
    } else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && !input.value.includes("\n") && sent.length && (input.value === "" || recall >= 0)) {
      e.preventDefault();
      recall = e.key === "ArrowUp" ? Math.max(0, (recall < 0 ? sent.length : recall) - 1) : recall + 1;
      if (recall >= sent.length) { recall = -1; input.value = ""; } else input.value = sent[recall];
      send.disabled = busy || !input.value.trim();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  document.querySelectorAll(".intro [data-say]").forEach((b) => b.addEventListener("click", () => fill(b.dataset.say)));
  $("help-btn").addEventListener("click", () => say("help"));

  $("new-chat").addEventListener("click", async () => {
    try { await fetch("chat/reset", { method: "POST" }); } catch { /* the cookie is rotated server-side when reachable */ }
    history = []; sent.length = 0; setQuick([]); save(); log.replaceChildren(); app.classList.remove("started"); input.focus();
  });

  rotatePlaceholder();
  history = load();
  history = history.filter((h) => (h.role === "me" ? typeof h.text === "string" : typeof h.html === "string"));
  history.forEach((h) => {
    if (h.role === "me") { sent.push(h.text); bubble("me", esc(h.text), "", h.ts); }
    else bubble("bot", clean(h.html), "", h.ts, h.label || "");
  });
  if (matchMedia("(pointer: fine)").matches) input.focus({ preventScroll: true });       // on touch screens focusing would raise the keyboard over the intro
})();
