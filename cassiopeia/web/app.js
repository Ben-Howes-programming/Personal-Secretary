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

  $("#inbox-count").textContent = state.inbox_waiting || "";
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


/* ---------- Tabs inside Today ---------- */
const tabLoaders = {};
function showTab(name) {
  document.querySelectorAll("#today .tab").forEach((tab) => { tab.hidden = tab.id !== `tab-${name}`; });
  document.querySelectorAll("#today-tabs button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.tab === name));
  if (tabLoaders[name]) tabLoaders[name]();
}
$("#today-tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) showTab(b.dataset.tab); });

/* ---------- Calendar ---------- */
const DAY_START = 7, DAY_HOURS = 16, HOUR_PX = 40;        // the grid shows 07:00 to 23:00
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const hhmm = (d) => d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
function mondayOf(date) { const d = new Date(date); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d; }
let weekStart = mondayOf(new Date());

function lanes(dayEvents) {            // events that overlap sit side by side
  const ends = [];
  for (const ev of dayEvents) {
    let lane = ends.findIndex((end) => end <= ev.from);
    if (lane < 0) { lane = ends.length; ends.push(0); }
    ends[lane] = ev.to; ev.lane = lane;
  }
  dayEvents.forEach((ev) => { ev.lanes = ends.length; });
}

async function loadCalendar() {
  const data = await api(`/api/calendar?start=${isoDay(weekStart)}&days=7`);
  const last = new Date(weekStart); last.setDate(last.getDate() + 6);
  $("#cal-title").textContent = `${weekStart.toLocaleDateString("en-GB", { day: "numeric", month: "long" })} to ${last.toLocaleDateString("en-GB", { day: "numeric", month: "long" })}, ${data.hours_booked} hours booked`;
  $("#cal-errors").innerHTML = data.errors.map((e) => `<p class="hint">${esc(e)}</p>`).join("");
  const days = [...Array(7)].map((_, i) => { const d = new Date(weekStart); d.setDate(d.getDate() + i); return { date: d, key: isoDay(d), timed: [], allDay: [] }; });
  const byKey = Object.fromEntries(days.map((d) => [d.key, d]));
  for (const ev of data.events) {
    const start = new Date(ev.start), end = new Date(ev.end), day = byKey[isoDay(start)];
    if (!day) continue;
    if (ev.all_day) { day.allDay.push(ev); continue; }
    const from = Math.max(0, (start.getHours() - DAY_START) * 60 + start.getMinutes());
    const to = Math.min(DAY_HOURS * 60, Math.max(from + 25, (end - start) / 60000 + (start.getHours() - DAY_START) * 60 + start.getMinutes()));
    day.timed.push({ ...ev, from, to, label: `${hhmm(start)} to ${hhmm(end)}` });
  }
  let html = `<div class="head"></div>` + days.map((d) => `<div class="head ${d.key === data.today ? "now" : ""}">${d.date.toLocaleDateString("en-GB", { weekday: "short" })}<strong>${d.date.getDate()}</strong></div>`).join("");
  html += `<div class="allday"></div>` + days.map((d) => `<div class="allday">${d.allDay.map((ev) => `<span class="chip" title="${esc(ev.title)}">${esc(ev.title)}</span>`).join("")}</div>`).join("");
  html += `<div class="gutter">${[...Array(DAY_HOURS)].map((_, i) => (i ? `<span style="top:${i * HOUR_PX}px">${String(DAY_START + i).padStart(2, "0")}:00</span>` : "")).join("")}</div>`;
  const now = new Date(), nowTop = ((now.getHours() - DAY_START) * 60 + now.getMinutes()) / 60 * HOUR_PX;
  for (const d of days) {
    d.timed.sort((a, b) => a.from - b.from); lanes(d.timed);
    const blocks = d.timed.map((ev) => `<div class="ev ${ev.local_id ? "mine" : ""} ${ev.to - ev.from < 70 ? "short" : ""}" title="${esc(ev.label)}  ${esc(ev.title)} (${esc(ev.source)})" style="top:${ev.from / 60 * HOUR_PX}px;height:${(ev.to - ev.from) / 60 * HOUR_PX - 2}px;left:${ev.lane / ev.lanes * 100}%;width:calc(${100 / ev.lanes}% - 3px)">${esc(ev.title)}<small>${esc(ev.label)}</small></div>`).join("");
    const line = d.key === data.today && nowTop > 0 && nowTop < DAY_HOURS * HOUR_PX ? `<div class="nowline" style="top:${nowTop}px"></div>` : "";
    html += `<div class="col ${d.key === data.today ? "now" : ""}">${blocks}${line}</div>`;
  }
  $("#week").innerHTML = html;
  if (!$("#free-form").day.value) $("#free-form").day.value = data.today;
}
tabLoaders.calendar = () => loadCalendar().catch((e) => toast(e.message));
const shiftWeek = (days) => { weekStart.setDate(weekStart.getDate() + days); tabLoaders.calendar(); };
$("#cal-prev").addEventListener("click", () => shiftWeek(-7));
$("#cal-next").addEventListener("click", () => shiftWeek(7));
$("#cal-now").addEventListener("click", () => { weekStart = mondayOf(new Date()); tabLoaders.calendar(); });
$("#plan-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => {
  await api("/api/events", { title: f.elements.title.value, start: f.start.value, end: f.end.value, notes: f.notes.value });
  weekStart = mondayOf(new Date(f.start.value)); f.reset(); await loadCalendar(); loadState(); toast("Event planned");
}); });
$("#free-form").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => {
  const r = await api("/api/calendar/free", { day: f.day.value, start: f.start.value, end: f.end.value, minutes: +f.minutes.value });
  $("#free-result").innerHTML = r.gaps.length
    ? r.gaps.map((g) => `<div class="row"><span class="grow">${esc(g.from)} to ${esc(g.to)}</span><span class="meta">${g.hours} h free</span></div>`).join("") + `<p class="hint">${r.slots} slot${r.slots === 1 ? "" : "s"} of ${r.minutes} minutes fit.</p>`
    : `<p class="hint">No free time in that window.</p>`;
}); });

/* ---------- Inbox ---------- */
let mailFilter = "action"; const openMail = new Set();
function mailCard(m, info) {
  const a = m.analysis, analysed = m.analysed_by === "claude";
  const tag = analysed ? `<span class="tag ${a.priority === "High" ? "warm" : ""}">${esc(a.priority)}</span>` : m.analysed_by === "rules" ? `<span class="tag">${esc(a.category)}</span>` : `<span class="tag ${m.urgent ? "warm" : ""}">${m.urgent ? "Looks urgent" : "Not analysed"}</span>`;
  const id = esc(m.id);
  const draft = m.draft_reply != null ? `<textarea data-draft-text="${id}" aria-label="Reply draft">${esc(m.draft_reply)}</textarea><div class="buttons"><button data-mail="save" data-id="${id}">Save draft</button>${info.gmail_drafts ? `<button class="quiet" data-mail="gmail" data-id="${id}">Save to Gmail drafts</button>` : ""}<button class="danger" data-mail="discard" data-id="${id}">Discard draft</button></div><p class="hint">Cassiopeia never sends a reply. ${info.gmail_drafts ? "Send it from Gmail." : "Copy it into your mail app."}</p>` : "";
  return `<details class="mail" data-mail-id="${id}" ${openMail.has(m.id) ? "open" : ""}><summary>${tag}<span class="from">${esc(m.sender)}</span><span class="subject">${esc(m.subject)}</span><span class="meta">${m.received_ts ? when(m.received_ts) : ""}</span></summary>
    ${analysed || m.analysed_by === "rules" ? `<p>${esc(a.summary || "")}</p>` : `<p class="hint">Claude has not read this one. ${esc(a.summary || "")}</p>`}
    <pre class="body">${esc(m.body)}</pre>
    <div class="buttons">${m.draft_reply == null ? `<button data-mail="draft" data-id="${id}" ${info.claude ? "" : "disabled"}>Draft a reply</button>` : ""}<button class="quiet" data-mail="analyse" data-id="${id}" ${info.claude ? "" : "disabled"}>${analysed ? "Analyse again" : "Analyse with Claude"}</button><button class="quiet" data-mail="${m.status === "completed" ? "reopen" : "done"}" data-id="${id}">${m.status === "completed" ? "Move back to open" : "Mark done"}</button></div>${draft}</details>`;
}
async function loadInbox() {
  const info = await api(`/api/inbox?show=${mailFilter === "done" ? "done" : "open"}`);
  const shown = mailFilter === "action" ? info.emails.filter((m) => m.analysis.action_required || m.urgent) : info.emails;
  const waiting = info.emails.filter((m) => m.analysis.action_required || m.urgent).length;
  if (mailFilter !== "done") $("#inbox-count").textContent = waiting || "";
  $("#inbox-note").textContent = !info.connected ? "Google is not connected. Connect it from the classic dashboard's Settings page, then come back." : info.minutes_since_sync == null ? "Not checked yet. Checking is free: rules sort the mail and Claude is not called." : `Last checked ${info.minutes_since_sync} minute${info.minutes_since_sync === 1 ? "" : "s"} ago. Checking is free. Claude reads an email only when you ask.`;
  $("#inbox-pending").innerHTML = info.pending && mailFilter !== "done" ? `<div class="row"><span class="grow">${info.pending} email${info.pending === 1 ? " has" : "s have"} not been read by Claude.</span><button class="quiet" id="inbox-analyse-all" ${info.claude ? "" : "disabled"}>Analyse up to ${info.analyse_cap} now</button></div>` : "";
  const empty = { action: "Nothing needs action. Look under All open for the rest.", open: "No open emails stored. Press Check for new mail.", done: "Nothing marked done yet." }[mailFilter];
  $("#inbox-list").innerHTML = shown.map((m) => mailCard(m, info)).join("") || `<p class="hint">${empty}</p>`;
}
tabLoaders.inbox = () => loadInbox().catch((e) => toast(e.message));
$("#inbox-filter").addEventListener("click", (e) => { if (!e.target.dataset.filter) return; mailFilter = e.target.dataset.filter; document.querySelectorAll("#inbox-filter button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.filter === mailFilter)); tabLoaders.inbox(); });
$("#inbox-sync").addEventListener("click", (e) => busy(e.target, async () => { const s = await api("/api/inbox/sync", { analyse: false }); toast(`${s.new} new, ${s.by_rules} filed by rules, ${s.pending} not yet analysed${s.errors.length ? ". " + s.errors[0] : ""}`); await loadInbox(); }));
$("#tab-inbox").addEventListener("toggle", (e) => { const id = e.target.dataset?.mailId; if (id) e.target.open ? openMail.add(id) : openMail.delete(id); }, true);
$("#tab-inbox").addEventListener("click", (e) => {
  const t = e.target;
  if (t.id === "inbox-analyse-all") return busy(t, async () => { const s = await api("/api/inbox/sync", { analyse: true }); toast(`Claude analysed ${s.by_claude} email${s.by_claude === 1 ? "" : "s"}`); await loadInbox(); });
  const action = t.dataset.mail, id = t.dataset.id;
  if (!action) return;
  const text = () => document.querySelector(`textarea[data-draft-text="${CSS.escape(id)}"]`)?.value || "";
  const calls = { draft: ["/api/inbox/draft", { id }], analyse: ["/api/inbox/analyse", { id }], done: ["/api/inbox/done", { id, done: true }], reopen: ["/api/inbox/done", { id, done: false }],
                  save: ["/api/inbox/save-draft", { id, text: text() }], gmail: ["/api/inbox/save-draft", { id, text: text(), to_gmail: true }], discard: ["/api/inbox/discard-draft", { id }] };
  busy(t, async () => { await api(...calls[action]); if (action === "done") openMail.delete(id); await loadInbox(); toast({ draft: "Draft written", analyse: "Analysed", done: "Marked done", reopen: "Moved back to open", save: "Draft saved", gmail: "Saved to Gmail drafts", discard: "Draft discarded" }[action]); });
});

/* ---------- Triggers (shown in Control) ---------- */
async function loadTriggers() {
  const t = await api("/api/triggers");
  $("#triggers").innerHTML = t.kinds.map((k) => `<label class="row"><input type="checkbox" data-trigger="${k.kind}" ${k.on ? "checked" : ""}><span class="grow">${esc(k.about)}</span></label>`).join("")
    + `<p class="hint">Each thing is announced once, as a Mac notification and a text if texting is on. Nothing is sent between ${esc(t.quiet_hours[0])} and ${esc(t.quiet_hours[1])}.</p>`
    + t.recent.map((r) => `<div class="row"><span class="grow hint">${esc(r.message)}</span><span class="meta">${when(r.fired_ts)}</span></div>`).join("");
}
$("#triggers").addEventListener("change", (e) => { if (e.target.dataset.trigger) busy(null, async () => { await api("/api/triggers/set", { kind: e.target.dataset.trigger, on: e.target.checked }); }); });
$("#trigger-check").addEventListener("click", (e) => busy(e.target, async () => { const r = await api("/api/triggers/check", {}); toast(r.sent.length ? `Sent ${r.sent.length}: ${r.sent[0]}` : "Nothing new to announce (or it is quiet hours)"); loadTriggers(); }));
const loadControlBase = loaders.control;
loaders.control = async () => { await loadControlBase(); await loadTriggers(); };

/* ---------- Money ---------- */
const gbp = (x) => (x == null ? "not set" : `${x < 0 ? "-" : ""}£${Math.abs(Number(x)).toLocaleString("en-GB", { maximumFractionDigits: 0 })}`);
const formData = (form) => Object.fromEntries(new FormData(form).entries());
function sparkline(history) {
  if (history.length < 2) return `<p class="hint">Record balances on two different days to see the trend.</p>`;
  const values = history.map((h) => h.net_worth), low = Math.min(...values), span = Math.max(...values) - low || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 100},${58 - ((v - low) / span) * 52}`).join(" ");
  return `<svg class="spark" viewBox="0 0 100 60" preserveAspectRatio="none" role="img" aria-label="Net worth from ${esc(history[0].date)} to ${esc(history.at(-1).date)}"><polyline points="${points}"/></svg><p class="hint">${esc(history[0].date)} to ${esc(history.at(-1).date)}</p>`;
}
function renderMoney(m) {
  const options = (list) => list.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
  const isas = m.accounts.filter((a) => ["investment", "lisa"].includes(a.kind_key));
  const od = m.overdraft, b = m.budget;
  $("#tab-money").innerHTML = `
  <div class="split">
    <div>
      <div class="panel"><h2>Accounts</h2>
        <table><tr><th>Account</th><th>Kind</th><th class="num">Rate</th><th class="num">Balance</th><th class="num">As of</th></tr>
        ${m.accounts.map((a) => `<tr><td>${esc(a.name)}</td><td>${esc(a.kind)}</td><td class="num">${a.rate == null ? "" : a.rate + "%"}</td><td class="num">${a.balance == null ? `<span class="hint">not set</span>` : (a.is_liability ? "owed " : "") + gbp(Math.abs(a.balance))}</td><td class="num nowrap">${esc(a.balance_date || "")}</td></tr>`).join("")}</table>
        <form class="inline" data-money="balance"><select name="account_id" aria-label="Account">${options(m.accounts)}</select><input name="balance" type="number" step="0.01" placeholder="Balance in £" required><input name="date" type="date" aria-label="Date, blank for today"><button>Record balance</button></form>
        <p class="hint">For the overdraft, enter the amount owed as a positive number.</p></div>
      <div class="panel"><h2>Monthly budget</h2>
        <div class="row"><span class="grow">Regular income</span><span>${gbp(b.income)}</span></div>
        <div class="row"><span class="grow">Regular costs</span><span>${gbp(b.costs)}</span></div>
        <div class="row"><span class="grow"><strong>Left each month</strong></span><span class="${b.surplus >= 0 ? "up" : "down"}">${gbp(b.surplus)}</span></div>
        ${m.recurring.map((r) => `<div class="row"><span class="grow hint">${esc(r.name)} (${esc(r.kind)}, ${esc(r.frequency)})</span><input type="number" step="0.01" value="${r.amount}" aria-label="Amount for ${esc(r.name)}" data-amount-for="${r.id}" style="width:6.5rem"><button class="quiet" data-money-save="${r.id}">Save</button><button class="danger" data-money-remove="${r.id}">Remove</button></div>`).join("")}
        <form class="inline" data-money="recurring"><input name="name" placeholder="Name, e.g. Student loan" required><select name="kind" aria-label="Kind"><option value="income">Income</option><option value="expense">Expense</option></select><input name="amount" type="number" step="0.01" placeholder="£" required><select name="frequency" aria-label="How often"><option>monthly</option><option>weekly</option><option>yearly</option></select><button>Add</button></form></div>
    </div>
    <aside>
      <div class="panel"><h2>Net worth</h2>${m.worth.has_data ? `<div class="figure-big">${gbp(m.worth.net)}</div><p>${gbp(m.worth.assets)} held, ${gbp(m.worth.debts)} owed</p>${sparkline(m.history)}` : `<p class="hint">Not set. Record a balance for each account to see this.</p>`}</div>
      <div class="panel"><h2>ISA allowances since ${esc(m.tax_year_start)}</h2>
        ${m.allowances.map((a) => `<div>${esc(a.name)}<div class="bar"><i style="width:${Math.min(100, (a.used / a.limit) * 100)}%"></i></div><p class="hint">${gbp(a.used)} paid in, ${gbp(Math.max(0, a.limit - a.used))} left of ${gbp(a.limit)}${a.bonus != null ? `. Bonus earned: ${gbp(a.bonus)}` : ""}</p></div>`).join("")}
        ${isas.length ? `<form class="inline" data-money="contribution"><select name="account_id" aria-label="ISA account">${options(isas)}</select><input name="amount" type="number" step="0.01" placeholder="Paid in £" required><button>Record payment in</button></form>` : ""}
        <p class="hint">The Lifetime ISA limit counts towards the overall allowance. Limits come from config.py: check gov.uk each tax year.</p></div>
      <div class="panel"><h2>Clearing the overdraft</h2>
        ${od.plan ? `<div class="figure-big">${gbp(od.plan.per_month)}<span class="hint"> a month</span></div><p>${gbp(od.owed)} owed, ${od.plan.months} months until the target.</p>` : `<p class="hint">No overdraft balance entered. Record it under Accounts to see a plan.</p>`}
        <form class="inline" data-money="overdraft-target"><label class="hint">Clear it by <input name="date" type="date" value="${esc(od.target)}" required></label><button class="quiet">Set date</button></form></div>
      <p class="hint">${esc(m.note)}</p>
    </aside>
  </div>`;
}
tabLoaders.money = () => api("/api/money").then(renderMoney).catch((e) => toast(e.message));
$("#tab-money").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { renderMoney(await api("/api/money/update", { action: f.dataset.money, ...formData(f) })); toast("Saved"); }); });
$("#tab-money").addEventListener("click", (e) => {
  const remove = e.target.dataset.moneyRemove, save = e.target.dataset.moneySave;
  if (remove) busy(e.target, async () => renderMoney(await api("/api/money/update", { action: "remove-recurring", id: +remove })));
  if (save) busy(e.target, async () => { renderMoney(await api("/api/money/update", { action: "set-recurring", id: +save, amount: document.querySelector(`[data-amount-for="${save}"]`).value })); toast("Saved"); });
});

/* ---------- University ---------- */
function renderUniversity(u) {
  const modules = u.modules.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join("");
  const score = `<select name="understanding" aria-label="Understanding, 1 to 5"><option value="1">1 lost</option><option value="2">2</option><option value="3" selected>3</option><option value="4">4</option><option value="5">5 solid</option></select>`;
  const needed = (m) => m.needed == null ? (m.total_weight ? `<span class="up">all marked</span>` : `<span class="hint">no weights yet</span>`) : m.needed > 100 ? `<span class="down">${m.needed.toFixed(0)}%, out of reach</span>` : `<span class="${m.needed <= u.target ? "up" : ""}">${Math.max(0, m.needed).toFixed(0)}%</span>`;
  $("#tab-university").innerHTML = `
  <div class="panel"><h2>Modules against a ${u.target}% target</h2>
    <table><tr><th>Module</th><th class="num">Average so far</th><th class="num">Weight marked</th><th class="num">Needed on the rest</th><th class="num">Study, last 28 days</th></tr>
    ${u.modules.map((m) => `<tr><td>${esc(m.name)}${m.code ? ` <span class="hint">${esc(m.code)}</span>` : ""}</td><td class="num">${m.average == null ? `<span class="hint">not set</span>` : m.average.toFixed(1) + "%"}</td><td class="num">${m.done_weight} of ${m.total_weight}%</td><td class="num">${needed(m)}</td><td class="num">${(m.study_minutes / 60).toFixed(1)} h</td></tr>`).join("")}</table>
    <p class="hint">"Needed on the rest" is the average you need on unmarked work in that module to finish on target. It only counts assessments that have a weight.</p></div>
  <div class="split even">
    <div>
      <div class="panel"><h2>Open assessments</h2>
        ${u.open.length ? `<table><tr><th>Assessment</th><th>Due</th><th class="num">Weight</th><th></th></tr>${u.open.map((a) => `<tr><td>${esc(a.title)}<br><span class="hint">${esc(a.module || "")}</span></td><td class="nowrap">${esc(a.due || "")}</td><td class="num">${a.weight == null ? "" : a.weight + "%"}</td><td class="num"><input type="number" min="0" max="100" step="0.1" placeholder="Mark" aria-label="Mark for ${esc(a.title)}" data-mark-for="${a.id}"> <button data-uni="mark" data-id="${a.id}">Save mark</button> <button class="quiet" data-uni="done" data-id="${a.id}">Done</button></td></tr>`).join("")}</table>` : `<p class="hint">Nothing open. Add your next assessment below.</p>`}
        <form class="inline" data-uni-form="assessment"><select name="module_id" aria-label="Module">${modules}</select><input name="title" placeholder="Title" required><input name="due" type="date" aria-label="Due date"><input name="weight" type="number" min="0" max="100" step="0.5" placeholder="Weight %"><button>Add assessment</button></form></div>
      <div class="panel"><h2>Log study time</h2>
        <form class="inline" data-uni-form="study"><select name="module_id" aria-label="Module">${modules}</select><input name="minutes" type="number" min="5" step="5" placeholder="Minutes" required><input name="note" placeholder="What you did (optional)"><button>Log</button></form>
        <p class="hint">${(u.study_total / 60).toFixed(1)} hours logged in the last 28 days.</p></div>
    </div>
    <div>
      <div class="panel"><h2>Lectures to review today</h2>
        ${u.reviews.map((l) => `<div class="row"><span class="grow">${esc(l.topic)}<br><span class="hint">${esc(l.module || "")}, last rated ${l.understanding} of 5</span></span><select data-review-for="${l.id}" aria-label="Understanding now"><option>1</option><option>2</option><option>3</option><option selected>4</option><option>5</option></select><button data-uni="review" data-id="${l.id}">Reviewed</button></div>`).join("") || `<p class="hint">Nothing is due. Log a lecture and it comes back for review on a spaced schedule.</p>`}</div>
      <div class="panel"><h2>Log a lecture</h2>
        <form class="inline" data-uni-form="lecture"><select name="module_id" aria-label="Module">${modules}</select><input name="topic" placeholder="Topic" required>${score}<button>Log lecture</button></form>
        <p class="hint">Rated 3 or below, it returns tomorrow. Otherwise in three days, then at longer gaps.</p>
        ${u.recent_lectures.map((l) => `<div class="row"><span class="grow hint">${esc(l.topic)}</span><span class="meta">${esc(l.date)}, ${l.understanding} of 5</span></div>`).join("")}</div>
    </div>
  </div>`;
}
tabLoaders.university = () => api("/api/university").then(renderUniversity).catch((e) => toast(e.message));
$("#tab-university").addEventListener("submit", (e) => { e.preventDefault(); const f = e.target; busy(f.querySelector("button"), async () => { renderUniversity(await api("/api/university/update", { action: f.dataset.uniForm, ...formData(f) })); toast("Saved"); }); });
$("#tab-university").addEventListener("click", (e) => {
  const action = e.target.dataset.uni, id = e.target.dataset.id;
  if (!action) return;
  const body = { action, id: +id };
  if (action === "mark") body.mark = document.querySelector(`[data-mark-for="${id}"]`).value;
  if (action === "review") body.understanding = document.querySelector(`[data-review-for="${id}"]`).value;
  busy(e.target, async () => { renderUniversity(await api("/api/university/update", body)); toast("Saved"); });
});

/* ---------- Start ---------- */
loadState().catch(() => {});
show(["today", "talk", "vault", "lab", "control"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "today");
setInterval(() => { if (!$("#today").hidden) loadState(); }, 120000);   // keep Today fresh
