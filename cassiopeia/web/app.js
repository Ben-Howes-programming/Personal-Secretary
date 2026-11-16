/* app.js: everything the Cassiopeia window does. Plain JavaScript, no build step.
   Rule: text from the server is always passed through esc() before it becomes HTML. */

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, body, raw) {
  const options = { headers: { "X-Cassiopeia": "1" } };
  if (raw !== undefined) { options.method = "POST"; options.body = raw; }
  else if (body !== undefined) { options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function toast(message) {
  const box = $("#toast");
  box.textContent = message; box.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => box.classList.remove("show"), 3800);
}

async function busy(button, work) {          // disable a button while its request runs, and report errors
  if (button) button.disabled = true;
  try { return await work(); } catch (error) { toast(error.message); } finally { if (button) button.disabled = false; }
}

/* Small markdown: paragraphs, bullets, bold, inline code, code blocks. Escapes first. */
function markdown(text) {
  const blocks = esc(text).split(/```(?:\w+)?\n?/);
  return blocks.map((block, i) => {
    if (i % 2) return `<pre>${block}</pre>`;
    const html = [], lines = block.split("\n"); let list = false;
    for (const line of lines) {
      const bullet = line.match(/^\s*[-*•]\s+(.*)/);
      if (bullet) { if (!list) { html.push("<ul>"); list = true; } html.push(`<li>${bullet[1]}</li>`); continue; }
      if (list) { html.push("</ul>"); list = false; }
      if (line.trim()) html.push(`<p>${line}</p>`);
    }
    if (list) html.push("</ul>");
    return html.join("").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  }).join("");
}

const pct = (x) => (x == null ? "" : `<span class="${x >= 0 ? "up" : "down"}">${(x * 100).toFixed(1)}%</span>`);
const when = (ts) => new Date(ts * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/* ---------- Navigation ---------- */
const loaders = {};
function show(view) {
  document.querySelectorAll(".view").forEach((section) => { section.hidden = section.id !== view; });
  document.querySelectorAll(".star").forEach((star) => star.setAttribute("aria-current", star.dataset.view === view));
  location.hash = view;
  if (loaders[view]) loaders[view]();
}
document.querySelectorAll(".star").forEach((star) => star.addEventListener("click", () => show(star.dataset.view)));

/* ---------- Today ---------- */
let state = null;
async function loadState() {
  state = await api("/api/state");
  const now = new Date(state.now), hour = now.getHours();
  $("#greeting").textContent = `${hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"}, ${state.owner}`;
  $("#clock").textContent = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  const status = $("#status");
  status.className = "status" + (state.ai.active ? " on" : "");
  status.textContent = state.ai.active ? (state.ai.active === "claude_code" ? "Claude plan connected" : "Claude API connected") : "Claude not connected";

  const latest = state.briefings[0];
  $("#briefing").innerHTML = latest
    ? markdown(latest.text) + `<p class="hint">${esc(latest.kind)} briefing, ${when(latest.created_ts)}</p>`
    : `<p class="hint">No briefing yet. One is written at ${esc(state.schedule["morning briefing"])} each day, or write one now.</p>`;

  let day = "", html = "";
  for (const event of state.events) {
    if (event.day !== day) { day = event.day; html += `<div class="day">${esc(day)}</div>`; }
    const remove = event.local_id ? `<button class="danger" data-event="${event.local_id}">Remove</button>` : "";
    html += `<div class="row"><span class="grow">${esc(event.line)}</span><span class="tag">${esc(event.source)}</span>${remove}</div>`;
  }
  for (const error of state.calendar_errors) html += `<p class="hint">${esc(error)}</p>`;
  $("#schedule").innerHTML = html || `<p class="hint">Nothing in the next seven days. Connect Google in the classic dashboard, or plan an event below.</p>`;

  html = "";
  for (const [group, rows] of Object.entries(state.tasks)) {
    if (!rows.length) continue;
    html += `<div class="day">${esc(group)}</div>`;
    for (const task of rows) html += `<div class="row"><input type="checkbox" data-task="${task.id}" aria-label="Mark done"><span class="grow">${esc(task.title)}</span><span class="meta">${esc(task.due || "")}</span><span class="tag ${task.priority === "High" ? "warm" : ""}">${esc(task.priority)}</span></div>`;
  }
  $("#tasks").innerHTML = html || `<p class="hint">No open tasks. Add one below, or tell Cassiopeia in Talk.</p>`;

  $("#activity-panel").hidden = !state.activity.length;
  $("#activity").innerHTML = state.activity.map((a) => `<div class="row"><span class="grow">${esc(a.app)}</span><span class="meta">${a.minutes} min</span></div>`).join("");
}

async function loadSide() {
  api("/api/weather").then((w) => {
    $("#weather").innerHTML = w.error ? `<h2>Weather</h2><p class="hint">${esc(w.error)}</p>` :
      `<h2>${esc(w.place)}</h2><div class="temp">${Math.round(w.temperature)}°</div><p>${esc(w.summary)}, feels like ${Math.round(w.feels_like)}°, wind ${Math.round(w.wind_mph)} mph</p>` +
      w.days.map((d) => `<div class="row"><span class="grow">${new Date(d.day).toLocaleDateString("en-GB", { weekday: "long" })}</span><span class="meta">${esc(d.summary)}, ${Math.round(d.low)}° to ${Math.round(d.high)}°, rain ${d.rain_chance}%</span></div>`).join("");
  }).catch(() => {});
  api("/api/headlines").then((items) => {
    $("#headlines").innerHTML = items.map((i) => `<div class="row"><span class="grow"><a href="${esc(i.link)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a><br><span class="meta" title="${esc(i.lean)}">${esc(i.source)}: ${esc(i.lean)}</span></span></div>`).join("")
      || `<p class="hint">No headlines could be loaded.</p>`;
  }).catch(() => {});
}
loaders.today = () => { loadState(); loadSide(); };

document.addEventListener("click", (event) => {
  const target = event.target;
  if (target.dataset.brief) busy(target, async () => { await api("/api/briefing", { kind: target.dataset.brief, send: false }); await loadState(); });
  if (target.dataset.event) busy(target, async () => { await api("/api/events/remove", { id: +target.dataset.event }); await loadState(); });
  if (target.dataset.task) busy(target, async () => { await api("/api/tasks/done", { id: +target.dataset.task }); await loadState(); });
});
$("#event-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { await api("/api/events", { title: f.elements.title.value, start: f.start.value }); f.reset(); await loadState(); toast("Event planned"); }); });
$("#task-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { await api("/api/tasks", { title: f.elements.title.value, due: f.due.value }); f.reset(); await loadState(); toast("Task added"); }); });

/* ---------- Talk ---------- */
let conversation = null, agent = "cassiopeia", listening = false, recogniser = null;
function addMessage(role, text, actions) {
  const chips = (actions || []).map((a) => `<span class="tag ${a.ok ? "ok" : "bad"}">${esc(a.detail)}</span>`).join("");
  $("#starter")?.remove();
  const box = document.createElement("div");
  box.className = `msg ${role}`;
  box.innerHTML = role === "user" ? esc(text) : `<div class="who">${esc(state?.agents?.[agent]?.label || "Cassiopeia")}</div><div class="prose">${markdown(text)}</div>${chips ? `<div class="chips">${chips}</div>` : ""}`;
  $("#thread").append(box); box.scrollIntoView({ behavior: "smooth", block: "end" });
  return box;
}
function speak(text, done) {
  if (!$("#speak").checked && !listening) return done && done();
  const plain = text.replace(/```[\s\S]*?```/g, " code block. ").replace(/[#*_`|>]/g, "");
  const voice = new SpeechSynthesisUtterance(plain.slice(0, 1600));
  voice.lang = "en-GB"; voice.rate = 1.05; voice.onend = voice.onerror = () => done && done();
  speechSynthesis.cancel(); speechSynthesis.speak(voice);
}
async function send(text) {
  if (!text.trim()) return;
  addMessage("user", text);
  const waiting = addMessage("assistant", "Thinking...");
  try {
    const result = await api("/api/chat", { text, conversation_id: conversation, agent });
    conversation = result.conversation_id; waiting.remove();
    addMessage("assistant", result.reply, result.actions);
    speak(result.reply, () => { if (listening) hear(); });
  } catch (error) { waiting.remove(); addMessage("assistant", `That did not work: ${error.message}`); if (listening) hear(); }
}
$("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); const box = e.target.text; send(box.value); box.value = ""; });
$("#chat-form textarea").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chat-form").requestSubmit(); } });

/* Voice conversation: listen, send, speak the reply, listen again, until you press Stop. */
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
function hear() {
  if (!listening) return;
  recogniser = new Recognition(); recogniser.lang = "en-GB"; recogniser.interimResults = false;
  let heard = false;
  recogniser.onresult = (e) => { heard = true; send(e.results[0][0].transcript); };
  recogniser.onerror = (e) => { if (e.error === "not-allowed") { stopListening(); toast("Microphone permission was refused. Allow it for this window and try again."); } };
  recogniser.onend = () => { if (listening && !heard) setTimeout(hear, 300); };   // silence: keep listening
  recogniser.start();
}
function stopListening() { listening = false; recogniser && recogniser.abort(); speechSynthesis.cancel(); $("#mic").setAttribute("aria-pressed", "false"); $("#mic").textContent = "Start talking"; }
$("#mic").addEventListener("click", () => {
  if (listening) return stopListening();
  if (!Recognition) return toast("This window has no speech recognition. Open Cassiopeia in Chrome or Safari for voice.");
  listening = true; $("#mic").setAttribute("aria-pressed", "true"); $("#mic").textContent = "Stop talking"; hear();
});
loaders.talk = async () => {
  if (!state) await loadState();
  $("#voice-hint").textContent = Recognition ? "Voice uses your browser's speech recognition, which may send audio to Apple or Google to transcribe it." : "Voice needs Chrome or Safari. Typing works everywhere.";
  $("#agents").innerHTML = Object.entries(state.agents).map(([key, a]) => `<button type="button" data-agent="${key}" aria-pressed="${key === agent}" title="${esc(a.about)}">${esc(a.label)}</button>`).join("");
};
$("#agents").addEventListener("click", (e) => { if (e.target.dataset.agent) { agent = e.target.dataset.agent; loaders.talk(); } });

/* ---------- Vault ---------- */
async function loadVault() {
  const data = await api("/api/vault");
  const options = (list) => `<option value="">Auto</option>` + list.map((x) => `<option>${esc(x)}</option>`).join("");
  if (!$("#up-area").options.length) { $("#up-area").innerHTML = options(data.areas); $("#up-unit").innerHTML = options(data.units); $("#up-kind").innerHTML = options(data.kinds); }
  let html = "", heading = "";
  for (const f of data.files) {
    const group = `${f.area} / ${f.unit} / ${f.kind}`;
    if (group !== heading) { heading = group; html += `<div class="day">${esc(group)}</div>`; }
    html += `<div class="row"><a class="grow" href="/api/vault/file?id=${f.id}">${esc(f.name)}</a><span class="meta">${Math.max(1, Math.round(f.size / 1024))} KB${f.text_chars ? ", searchable" : ""}</span><button class="danger" data-remove="${f.id}">Remove</button></div>`;
  }
  $("#vault-tree").innerHTML = `<div class="panel">${html || `<p class="hint">The vault is empty. Drop your first file above.</p>`}</div>`;
}
async function upload(files) {
  for (const file of files) {
    const query = new URLSearchParams({ name: file.name, area: $("#up-area").value, unit: $("#up-unit").value, kind: $("#up-kind").value });
    try { const row = await api(`/api/vault/upload?${query}`, undefined, file); $("#upload-log").textContent = `Filed ${row.name} under ${row.area} / ${row.unit} / ${row.kind}`; }
    catch (error) { toast(`${file.name}: ${error.message}`); }
  }
  loadVault();
}
const drop = $("#drop");
["dragenter", "dragover"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));
$("#file-input").addEventListener("change", (e) => upload(e.target.files));
$("#vault-tree").addEventListener("click", (e) => { if (e.target.dataset.remove) busy(e.target, async () => { await api("/api/vault/remove", { id: +e.target.dataset.remove }); loadVault(); toast("Moved to vault/_removed"); }); });
$("#vault-search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { results } = await api(`/api/vault?q=${encodeURIComponent(e.target.q.value)}`);
  $("#vault-results").innerHTML = `<div class="panel">${results.map((r) => `<div class="row"><span class="grow"><a href="/api/vault/file?id=${r.id}">${esc(r.path)}</a><br><span class="hint">${esc(r.snippet)}</span></span>${r.assessed ? `<span class="tag warm">Assessed</span>` : ""}</div>`).join("") || `<p class="hint">Nothing matched. Scanned PDFs have no searchable text.</p>`}</div>`;
});
loaders.vault = loadVault;

/* ---------- Lab ---------- */
function simCard(s) {
  const figures = s.files.filter((f) => /\.(png|svg)$/i.test(f)).map((f) => `<img class="figure" src="/sandbox/${s.id}/${encodeURIComponent(f)}" alt="Simulation figure ${esc(f)}">`).join("");
  const others = s.files.filter((f) => !/\.(png|svg)$/i.test(f)).map((f) => `<a href="/sandbox/${s.id}/${encodeURIComponent(f)}" target="_blank">${esc(f)}</a>`).join(" ");
  const warn = s.problems.length ? `<p class="hint">Blocked: the script ${esc(s.problems.join(", "))}.</p>` : "";
  const action = s.status === "awaiting approval" && !s.problems.length ? `<button data-run="${s.id}">Run this script</button>` : "";
  return `<details ${s.status === "awaiting approval" ? "open" : ""}><summary>${esc(s.prompt)} <span class="tag ${s.status === "done" ? "ok" : s.status === "awaiting approval" ? "warm" : "bad"}">${esc(s.status)}</span></summary>
    <pre>${esc(s.code)}</pre>${warn}${action}${s.output ? `<pre>${esc(s.output)}</pre>` : ""}${figures}${others}</details>`;
}
async function loadLab() {
  $("#sims").innerHTML = (await api("/api/sims")).map(simCard).join("") || `<p class="hint">No simulations yet. Describe one above. You read the script before it runs.</p>`;
  const lab = await api("/api/lab");
  $("#lab-note").textContent = `${lab.disclaimer} Each result subtracts an assumed ${lab.cost_bps / 100}% cost per round trip. Paper accounts start at £${lab.start_cash.toLocaleString("en-GB")} and move forward one trading day per night.`;
  const bySymbol = {};
  for (const row of lab.backtests) (bySymbol[row.symbol] ||= {})[row.strategy] = row;
  const paper = {};
  for (const row of lab.paper) paper[`${row.symbol}|${row.strategy}`] = row;
  let html = "";
  for (const [symbol, strategies] of Object.entries(bySymbol)) {
    html += `<div class="day">${esc(lab.names[symbol] || symbol)} (${esc(symbol)})</div><table><tr><th>Pattern</th><th class="num">Whole period</th><th class="num">Per year</th><th class="num">Days up</th><th class="num">Worst fall</th><th class="num">Paper account</th></tr>`;
    for (const [key, label] of Object.entries(lab.strategies)) {
      const r = strategies[key]; if (!r) continue;
      const p = paper[`${symbol}|${key}`];
      html += `<tr><td>${esc(label)}</td><td class="num">${pct(r.total_return)}</td><td class="num">${pct(r.annualised)}</td><td class="num">${(r.win_rate * 100).toFixed(0)}%</td><td class="num">${pct(r.max_drawdown)}</td><td class="num">${p ? `£${Math.round(p.equity).toLocaleString("en-GB")} after ${p.days} day${p.days === 1 ? "" : "s"}` : ""}</td></tr>`;
    }
    html += "</table>";
  }
  html += `<div class="day">Study list (things to learn from, not things to buy)</div>` + lab.study_list.map((s) => `<div class="row"><span class="grow">${esc(s.name)} (${esc(s.symbol)})</span><span class="meta">${esc(s.teaches)}</span></div>`).join("");
  $("#lab-tables").innerHTML = lab.backtests.length ? html : `<p class="hint">No results yet. The lab runs at night, or press "Run the lab now". It needs the yfinance package and an internet connection.</p>` + html;
}
$("#sim-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { await api("/api/sims/draft", { prompt: f.prompt.value }); f.reset(); await loadLab(); }); });
$("#sims").addEventListener("click", (e) => { if (e.target.dataset.run) busy(e.target, async () => { await api("/api/sims/run", { id: +e.target.dataset.run }); await loadLab(); }); });
$("#lab-run").addEventListener("click", (e) => busy(e.target, async () => { toast((await api("/api/lab/run", {})).summary); await loadLab(); }));
loaders.lab = loadLab;

/* ---------- Control ---------- */
async function loadControl() {
  await loadState();
  $("#protocols").innerHTML = Object.entries(state.protocols).map(([name, about]) => `<div class="row"><span class="grow"><strong>${esc(name)}</strong><br><span class="hint">${esc(about)}</span></span><button data-protocol="${esc(name)}">Initiate</button></div>`).join("");
  const channel = (on, label, kind) => `<div class="row"><span class="grow">${label}</span><span class="tag ${on ? "ok" : ""}">${on ? "On" : "Off in .env"}</span><button class="quiet" data-test="${kind}">Send test</button></div>`;
  $("#channels").innerHTML = channel(state.channels.text, "Texts to your phone (iMessage)", "text") + channel(state.channels.email, "Emails to your own address", "email");
  $("#outbox").innerHTML = state.outbox.map((m) => `<div class="row"><span class="grow hint">${esc(m.body.slice(0, 70))}</span><span class="tag ${m.status === "sent" ? "ok" : m.status === "failed" ? "bad" : ""}">${esc(m.channel)}: ${esc(m.status)}</span></div>`).join("");
  $("#memories").innerHTML = state.memories.map((m) => `<div class="row"><span class="grow">${esc(m.text)}</span><button class="danger" data-forget="${m.id}">Forget</button></div>`).join("") || `<p class="hint">Nothing yet. Say "remember that..." in Talk.</p>`;
  const ran = Object.fromEntries(state.jobs.map((j) => [j.name, j]));
  $("#jobs").innerHTML = Object.entries(state.schedule).map(([name, at]) => { const j = ran[name]; return `<div class="row"><span class="grow">${esc(name)} at ${esc(at)}</span><span class="meta">${j ? `${esc(j.last_status)}, ${when(j.last_run_ts)}` : "not run yet"}</span></div>`; }).join("") + `<p class="hint">Jobs run while Cassiopeia is running. A job missed during sleep runs when the Mac wakes, within a few hours.</p>`;
  const b = state.budget;
  $("#budget").innerHTML = `<div class="row"><span class="grow">Connection</span><span class="meta">${esc({ claude_code: "Claude plan through Claude Code", api: "API key" }[state.ai.active] || "none")}${state.ai.last_error ? ", last error: " + esc(state.ai.last_error.slice(0, 80)) : ""}</span></div><div class="row"><span class="grow">API spend this month</span><span class="meta">${b.spent_gbp == null ? "unknown" : "£" + b.spent_gbp.toFixed(2)} of £${b.cap_gbp.toFixed(0)} cap${b.over ? ", API route paused" : ""}</span></div><p class="hint">The Claude plan route is not counted. The estimate treats a dollar as a pound until an exchange rate is cached, so it reads high.</p>`;
  const updates = await api("/api/updates");
  $("#updates").innerHTML = updates.map((u) => `<details ${/awaiting|working|failed/.test(u.status) ? "open" : ""}><summary>${esc(u.instruction)} <span class="tag ${u.status === "awaiting approval" ? "warm" : /merged/.test(u.status) ? "ok" : ""}">${esc(u.status)}</span></summary>${u.diff ? `<pre>${esc(u.diff)}</pre>` : ""}${u.test_output ? `<pre>${esc(u.test_output)}</pre>` : ""}${u.status === "awaiting approval" ? `<button data-approve="${u.id}">Approve and merge</button> ` : ""}${/awaiting|tests failed/.test(u.status) ? `<button class="danger" data-reject="${u.id}">Reject</button>` : ""}</details>`).join("");
  if (updates.some((u) => u.status === "working")) setTimeout(() => { if (!$("#control").hidden) loadControl(); }, 8000);
}
$("#control").addEventListener("click", (e) => {
  const d = e.target.dataset;
  if (d.protocol) busy(e.target, async () => { const r = await api("/api/protocols/run", { name: d.protocol }); $("#protocol-log").innerHTML = r.steps.map((s) => `<div>${s.ok ? "Done" : "Skipped"}: ${esc(s.detail)}</div>`).join(""); });
  if (d.test) busy(e.target, async () => { toast((await api("/api/test-message", { channel: d.test })).detail); loadControl(); });
  if (d.forget) busy(e.target, async () => { await api("/api/memories/forget", { id: +d.forget }); loadControl(); });
  if (d.approve) busy(e.target, async () => { await api("/api/updates/approve", { id: +d.approve }); loadControl(); toast("Merged. Restart Cassiopeia to load the change."); });
  if (d.reject) busy(e.target, async () => { await api("/api/updates/reject", { id: +d.reject }); loadControl(); });
});
$("#memory-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { await api("/api/memories", { text: f.text.value }); f.reset(); loadControl(); }); });
$("#update-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { await api("/api/updates/propose", { instruction: f.instruction.value }); f.reset(); loadControl(); }); });
loaders.control = loadControl;

loadState().catch(() => {});
show(["today", "talk", "vault", "lab", "control"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "today");
setInterval(() => { if (!$("#today").hidden) loadState(); }, 120000);   // keep Today fresh
