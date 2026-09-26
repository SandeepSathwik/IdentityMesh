(() => {
  "use strict";

  let token = "";
  const byId = (id) => document.getElementById(id);
  const notice = byId("notice");
  const collectButton = byId("collect-button");
  let userGeneration = 0;
  let userCursor = null;

  function resetUsers() {
    userGeneration += 1;
    userCursor = null;
    clear(byId("user-list"));
    byId("user-more").hidden = true;
  }

  function userChoices(items, preferred = byId("user-snapshot").value) {
    resetUsers();
    const select = byId("user-snapshot");
    clear(select);
    const snapshots = items.filter((item) => item.collector_version === "aws-iam-user/0.1");
    snapshots.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.snapshot_id;
      option.textContent = `#${item.sequence_id} · ${item.status} · ${formatTime(item.created_at)}`;
      select.appendChild(option);
    });
    select.disabled = snapshots.length === 0;
    if (snapshots.some((item) => item.snapshot_id === preferred)) select.value = preferred;
    byId("user-status").textContent = snapshots.length
      ? "Select a collection to inspect its observed users."
      : "No user collections in the latest 100 attempts. Collect users to create one.";
    if (snapshots.length) loadUsers();
  }

  async function loadUsers(append = false) {
    const snapshotId = byId("user-snapshot").value;
    if (!snapshotId) return;
    const generation = userGeneration;
    const query = new URLSearchParams({ limit: "50" });
    if (append && userCursor) query.set("cursor", userCursor);
    byId("user-more").disabled = true;
    byId("user-status").textContent = "Loading user observations…";
    try {
      const page = await api(`/api/v1/snapshots/${encodeURIComponent(snapshotId)}/users?${query}`);
      if (generation !== userGeneration) return;
      const list = byId("user-list");
      page.items.forEach((item) => list.appendChild(record(
        item.display_name, item.provenance.source_object_id, [item.external_id, item.principal_type]
      )));
      userCursor = page.next_cursor;
      byId("user-more").hidden = !userCursor;
      const gaps = page.gaps.map((gap) => `${gap.operation}: ${gap.reason_code}`).join("; ");
      byId("user-status").textContent =
        `${page.collection_status} · ${list.children.length} of ${page.total_count} observed users · ` +
        `${formatTime(page.collected_at)}. ` +
        (page.collection_status === "complete"
          ? "Complete user listing; access is not evaluated."
          : "Incomplete evidence cannot establish user absence.") + (gaps ? ` ${gaps}` : "");
    } catch (error) {
      if (generation !== userGeneration) return;
      resetUsers();
      byId("user-status").textContent = `${error.code || "REQUEST_FAILED"}: ${error.message}`;
    } finally {
      if (generation === userGeneration) byId("user-more").disabled = false;
    }
  }

  byId("user-snapshot").addEventListener("change", () => {
    resetUsers();
    loadUsers();
  });
  byId("user-more").addEventListener("click", () => loadUsers(true));
  byId("collect-users").addEventListener("click", async () => {
    byId("collect-users").disabled = true;
    collectButton.disabled = true;
    resetUsers();
    byId("user-status").textContent = "Collecting and retaining AWS user observations…";
    try {
      const run = await api("/api/v1/collections/aws/iam/users", { method: "POST" });
      await loadSnapshots(run.snapshot_id);
    } catch (error) {
      byId("user-status").textContent = `${error.code || "REQUEST_FAILED"}: ${error.message}`;
    } finally {
      byId("collect-users").disabled = false;
      collectButton.disabled = false;
    }
  });

  function createComparisonPanel({ prefix, endpoint, collectorVersion, snapshotStatus, entityId, help }) {
    let comparisonQuery = null;
    let comparisonCursor = null;
    let comparisonGeneration = 0;
    const element = (suffix) => byId(`${prefix}-${suffix}`);

    function resetComparison() {
      comparisonGeneration += 1;
      comparisonQuery = null;
      comparisonCursor = null;
      clear(element("list"));
      element("more").hidden = true;
    }

    function comparisonChoices(items) {
      resetComparison();
      const ready = items.filter((item) => item.status === snapshotStatus
        && item.collector_version === collectorVersion);
      for (const id of ["base", "target"]) {
        const select = element(id);
        clear(select);
        ready.forEach((item) => {
          const option = document.createElement("option");
          option.value = item.snapshot_id;
          option.textContent = `#${item.sequence_id} · ${formatTime(item.collected_at)}`;
          select.appendChild(option);
        });
        select.disabled = ready.length < 2;
      }
      if (ready.length >= 2) element("base").value = ready[1].snapshot_id;
      element("button").disabled = ready.length < 2;
      element("status").textContent = ready.length < 2
        ? "Two complete observations are needed. Incomplete collections cannot establish absence."
        : help;
    }

    async function loadComparison(append = false) {
      if (!comparisonQuery) return;
      const generation = comparisonGeneration;
      const query = new URLSearchParams(comparisonQuery);
      if (append && comparisonCursor) query.set("cursor", comparisonCursor);
      element("button").disabled = true;
      element("more").disabled = true;
      element("status").textContent = "Comparing complete observations…";
      try {
        const result = await api(`${endpoint}?${query}`);
        if (generation !== comparisonGeneration) return;
        const list = element("list");
        result.items.forEach((change) => {
          const identity = change.after || change.before;
          const names = change.before && change.after && change.before.display_name !== change.after.display_name
            ? `${change.before.display_name} → ${change.after.display_name}` : identity.display_name;
          list.appendChild(record(`${change.kind}: ${names}`, identity.source_id,
            [identity[entityId], ...change.changed_fields]));
        });
        comparisonCursor = result.next_cursor;
        element("more").hidden = !comparisonCursor;
        element("status").textContent =
          `${result.added_count} added · ${result.removed_count} removed · ` +
          `${result.changed_count} changed · ${result.unchanged_count} unchanged. ` +
          `Showing ${list.children.length} of ${result.total_count} changes. ` +
          `Account ${result.account_id}${result.partition ? ` (${result.partition})` : ""}; ${formatTime(result.base_collected_at)} → ` +
          `${formatTime(result.target_collected_at)}. Metadata differences do not establish access.`;
      } catch (error) {
        if (generation !== comparisonGeneration) return;
        // Never leave a successful-looking partial comparison after an error.
        clear(element("list"));
        comparisonCursor = null;
        element("more").hidden = true;
        element("status").textContent = `${error.code || "REQUEST_FAILED"}: ${error.message}`;
      } finally {
        if (generation === comparisonGeneration) {
          element("button").disabled = false;
          element("more").disabled = false;
        }
      }
    }

    element("form").addEventListener("submit", (event) => {
      event.preventDefault();
      resetComparison();
      comparisonQuery = {
        base_snapshot_id: element("base").value,
        target_snapshot_id: element("target").value,
        limit: "50",
      };
      loadComparison();
    });
    element("more").addEventListener("click", () => loadComparison(true));
    for (const id of ["base", "target"]) {
      element(id).addEventListener("change", () => {
        resetComparison();
        element("button").disabled = false;
        element("status").textContent = "Selection changed. Compare to load these observations.";
      });
    }

    return comparisonChoices;
  }

  const comparisonChoices = createComparisonPanel({
    prefix: "comparison", endpoint: "/api/v1/snapshots/compare",
    collectorVersion: "aws-iam-role/0.1", snapshotStatus: "ready", entityId: "role_id",
    help: "Choose from the latest 100 collection attempts. Raw policy and tag values stay private.",
  });
  const userComparisonChoices = createComparisonPanel({
    prefix: "user-comparison", endpoint: "/api/v1/snapshots/users/compare",
    collectorVersion: "aws-iam-user/0.1", snapshotStatus: "collected", entityId: "user_id",
    help: "Choose complete user observations from the latest 100 attempts. Password usage is excluded.",
  });

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
      const details = [item.status, item.collector_version,
        formatTime(item.ready_at || item.failed_at || item.created_at)];
      if (item.failure_code) details.push(item.failure_code);
      list.appendChild(record(`Snapshot ${item.sequence_id}`, item.snapshot_id, details, failed));
    });
  }

  async function loadSnapshots(preferredUser) {
    const snapshots = await api("/api/v1/snapshots?limit=100");
    renderSnapshots(snapshots.items.slice(0, 20));
    comparisonChoices(snapshots.items);
    userComparisonChoices(snapshots.items);
    userChoices(snapshots.items, preferredUser);
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
    comparisonChoices([]);
    userComparisonChoices([]);
    userChoices([]);
    collectButton.disabled = false;
    byId("collect-users").disabled = true;
    try {
      await refresh();
      byId("collect-users").disabled = false;
    } catch (error) {
      collectButton.disabled = true;
      setNotice(error.message, true);
    }
  });

  collectButton.addEventListener("click", async () => {
    collectButton.disabled = true;
    byId("collect-users").disabled = true;
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
      byId("collect-users").disabled = false;
    }
  });
})();
