const $ = (id) => document.getElementById(id);
const esc = (s) => (s || "").replace(/</g, "&lt;");

function rows(list) {
  return (list || []).map(r =>
    `<div class="row ${r.severity}">
       <b>${r.severity.toUpperCase()}</b> ${esc(r.what)} ${r.detail ? "(" + esc(r.detail) + ")" : ""}
       <div>${esc(r.why)}</div><div><i>Fix:</i> ${esc(r.fix)}</div>
     </div>`).join("");
}

$("run").onclick = async () => {
  $("out").innerHTML = "Running… (a real fix can take 10-60s)";
  const body = { url: $("url").value, repo: $("repo").value, model: $("model").value };
  let data;
  try {
    const res = await fetch("/scan", { method: "POST", body: JSON.stringify(body) });
    data = await res.json();
  } catch (e) {
    $("out").innerHTML = "Request failed: " + e;
    return;
  }
  if (data.error) { $("out").innerHTML = "<pre>" + esc(data.error) + "</pre>"; return; }

  const a = data.audit;
  let html = `<div class="score">Score ${a.score}/100</div>
    <h2>SEO</h2>${rows(a.seo)}
    <h2>AEO (AI answer engines)</h2>${rows(a.aeo)}
    <h2>Performance</h2>${rows(a.perf)}`;

  if (data.cycle) {
    const c = data.cycle;
    if (c.model === "B") {
      html += `<h2>Fix (Model B)</h2>
        <p>Decision: <b>${esc(c.decision.action)}</b> — ${esc(c.decision.reason)}</p>
        <pre>${esc(c.diff)}</pre>`;
    } else {
      html += `<h2>Brief (Model A)</h2><pre>${esc(c.brief)}</pre>`;
    }
  }
  if (data.log && data.log.length) {
    html += `<h2>Log</h2><pre style="background:#111;color:#0f0">${esc(data.log.join("\n"))}</pre>`;
  }
  $("out").innerHTML = html;
};
