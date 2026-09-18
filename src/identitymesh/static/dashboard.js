(() => {
  "use strict";

  let token = "";
  const byId = (id) => document.getElementById(id);
  const notice = byId("notice");
  const collectButton = byId("collect-button");

  function setNotice(message, isError = false) {
    notice.textContent = message;
    notice.classList.toggle("error", isError);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, ...(options.headers || {}) },
    });
    const body = await response.json();
    if (!response.ok) {
      const error = new Error(body?.error?.message || "The request could not be completed.");
      error.code = body?.error?.code;
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function formatTime(value) {
    if (!value) return "—";
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" })
      .format(new Date(value));
  }

  function clear(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
  }

  function record(title, identifier, meta, failed = false) {
    const item = document.createElement("article");
    item.className = "record";
    const heading = document.createElement("strong");
    heading.textContent = title;
    const code = document.createElement("code");
    code.textContent = identifier;
    const details = document.createElement("div");
    details.className = "record-meta";
    meta.forEach((value, index) => {
      const pill = document.createElement("span");
      pill.className = `pill${failed && index === 0 ? " failed" : ""}`;
      pill.textContent = value;
      details.appendChild(pill);
    });
    item.append(heading, code, details);
    return item;
  }

  function renderPrincipals(items) {
    const list = byId("principal-list");
    clear(list);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "The active collection contains no AWS roles.";
      list.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      list.appendChild(record(item.display_name, item.external_id, [item.principal_type, item.provider]));
    });
  }

  function renderSnapshots(items) {
    const list = byId("snapshot-list");
    clear(list);
    items.forEach((item) => {
      const failed = item.status === "failed";
      const details = [item.status, formatTime(item.ready_at || item.failed_at || item.created_at)];
      if (item.failure_code) details.push(item.failure_code);
      list.appendChild(record(`Snapshot ${item.sequence_id}`, item.snapshot_id, details, failed));
    });
  }

  async function loadSnapshots() {
    const snapshots = await api("/api/v1/snapshots?limit=20");
    renderSnapshots(snapshots.items);
  }

  function renderGraph(nodes) {
    const svg = byId("graph");
    const empty = byId("graph-empty");
    clear(svg);
    empty.hidden = nodes.length > 0;
    if (!nodes.length) return;
    const width = 960;
    const height = 360;
    const radius = Math.min(132, 42 + nodes.length * 7);
    nodes.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / nodes.length - Math.PI / 2;
      const x = width / 2 + Math.cos(angle) * radius;
      const y = height / 2 + Math.sin(angle) * radius;
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", String(x));
      circle.setAttribute("cy", String(y));
      circle.setAttribute("r", "32");
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", String(x));
      label.setAttribute("y", String(y + 50));
      label.setAttribute("text-anchor", "middle");
      label.textContent = node.display_name.length > 24
        ? `${node.display_name.slice(0, 21)}…`
        : node.display_name;
      group.append(circle, label);
      svg.appendChild(group);
    });
  }

  async function refresh() {
    await loadSnapshots();
    let active;
    let principals;
    let graph;
    try {
      [active, principals, graph] = await Promise.all([
        api("/api/v1/snapshots/active"),
        api("/api/v1/principals?limit=100"),
        api("/api/v1/graph?limit=100"),
      ]);
    } catch (error) {
      if (error.code === "ACTIVE_SNAPSHOT_NOT_FOUND") {
        byId("metric-status").textContent = "No ready snapshot";
        byId("metric-version").textContent = "—";
        byId("metric-count").textContent = "0";
        byId("metric-ready").textContent = "—";
        renderPrincipals([]);
        renderGraph([]);
        setNotice("No verified active snapshot exists yet. Run a collection to create one.");
        return;
      }
      throw error;
    }
    byId("metric-status").textContent = active.status;
    byId("metric-version").textContent = active.projection_version;
    byId("metric-count").textContent = String(principals.total_count);
    byId("metric-ready").textContent = formatTime(active.ready_at);
    renderPrincipals(principals.items);
    renderGraph(graph.nodes);
    setNotice(`Showing verified snapshot ${active.snapshot_id}.`);
  }

  byId("access-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const tokenInput = byId("api-token");
    token = tokenInput.value;
    tokenInput.value = "";
    collectButton.disabled = false;
    try {
      await refresh();
    } catch (error) {
      collectButton.disabled = true;
      setNotice(error.message, true);
    }
  });

  collectButton.addEventListener("click", async () => {
    collectButton.disabled = true;
    setNotice("Collecting AWS roles and verifying the graph projection…");
    try {
      const run = await api("/api/v1/collections/aws/iam/roles", { method: "POST" });
      if (run.snapshot_status !== "ready") {
        await loadSnapshots();
        setNotice(`Collection ended safely: ${run.failure_code || run.snapshot_status}.`, true);
      } else {
        await refresh();
      }
    } catch (error) {
      setNotice(error.message, true);
    } finally {
      collectButton.disabled = false;
    }
  });
})();
