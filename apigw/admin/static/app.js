const adminKeyInput = document.getElementById("admin-key");
const refreshButton = document.getElementById("refresh-button");
const reloadButton = document.getElementById("reload-button");
const newRouteButton = document.getElementById("new-route-button");
const formatRouteButton = document.getElementById("format-route-button");
const syncFormButton = document.getElementById("sync-form-button");
const applyFormButton = document.getElementById("apply-form-button");
const validateRouteButton = document.getElementById("validate-route-button");
const saveRouteButton = document.getElementById("save-route-button");
const deleteRouteButton = document.getElementById("delete-route-button");
const refreshHistoryButton = document.getElementById("refresh-history-button");
const refreshKeysButton = document.getElementById("refresh-keys-button");
const rotateKeyButton = document.getElementById("rotate-key-button");
const statusLine = document.getElementById("status-line");
const routeCount = document.getElementById("route-count");
const upstreamCount = document.getElementById("upstream-count");
const globalPluginCount = document.getElementById("global-plugin-count");
const configuredPluginCount = document.getElementById("configured-plugin-count");
const protocolPills = document.getElementById("protocol-pills");
const pluginUsage = document.getElementById("plugin-usage");
const routesTable = document.getElementById("routes-table");
const historyTable = document.getElementById("history-table");
const keysTable = document.getElementById("keys-table");
const routeSearch = document.getElementById("route-search");
const protocolFilter = document.getElementById("protocol-filter");
const routeMeta = document.getElementById("route-meta");
const routeEditor = document.getElementById("route-editor");
const routeDiffMeta = document.getElementById("route-diff-meta");
const routeDiff = document.getElementById("route-diff");
const newKeyBox = document.getElementById("new-key-box");
const newKeyValue = document.getElementById("new-key-value");

const formRouteId = document.getElementById("form-route-id");
const formRouteDescription = document.getElementById("form-route-description");
const formRouteProtocol = document.getElementById("form-route-protocol");
const formUpstreamType = document.getElementById("form-upstream-type");
const formRoutePath = document.getElementById("form-route-path");
const formRouteMethods = document.getElementById("form-route-methods");
const formTargetUrl = document.getElementById("form-target-url");
const formTargetWeight = document.getElementById("form-target-weight");
const formLoadBalance = document.getElementById("form-load-balance");
const formPlugins = document.getElementById("form-plugins");

const rotateKeyRole = document.getElementById("rotate-key-role");
const rotateKeyLabel = document.getElementById("rotate-key-label");

const state = {
  adminKey: sessionStorage.getItem("oag-admin-key") || "",
  routes: [],
  filteredRoutes: [],
  selectedRouteId: "",
  editorSourceId: "",
  historyEntries: [],
  keys: [],
};

adminKeyInput.value = state.adminKey;

adminKeyInput.addEventListener("input", (event) => {
  state.adminKey = event.target.value.trim();
  sessionStorage.setItem("oag-admin-key", state.adminKey);
});

routeSearch.addEventListener("input", () => {
  filterRoutes();
  renderRoutes();
});

protocolFilter.addEventListener("change", () => {
  filterRoutes();
  renderRoutes();
});

refreshButton.addEventListener("click", async () => {
  await loadDashboard();
});

reloadButton.addEventListener("click", async () => {
  await reloadConfig();
});

newRouteButton.addEventListener("click", () => {
  createNewRoute();
});

formatRouteButton.addEventListener("click", () => {
  try {
    const route = parseEditorRoute();
    setEditorRoute(route, state.editorSourceId);
    setStatus("라우트 JSON을 정렬해 두었습니다.", "success");
  } catch (error) {
    setStatus(`포맷 실패: ${messageFromError(error)}`, "error");
  }
});

syncFormButton.addEventListener("click", () => {
  try {
    populateForm(parseEditorRoute());
    setStatus("에디터 내용을 폼에 반영했습니다.", "success");
  } catch (error) {
    setStatus(`폼 동기화 실패: ${messageFromError(error)}`, "error");
  }
});

applyFormButton.addEventListener("click", () => {
  applyFormToEditor();
});

validateRouteButton.addEventListener("click", async () => {
  await validateRoute();
});

saveRouteButton.addEventListener("click", async () => {
  await saveRoute();
});

deleteRouteButton.addEventListener("click", async () => {
  await deleteRoute();
});

refreshHistoryButton.addEventListener("click", async () => {
  await loadHistory();
});

refreshKeysButton.addEventListener("click", async () => {
  await loadKeys();
});

rotateKeyButton.addEventListener("click", async () => {
  await rotateKey();
});

function headers() {
  return state.adminKey ? { "X-Admin-Key": state.adminKey } : {};
}

function messageFromError(error) {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...headers(),
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = payload.detail || text || `Request failed: ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function setStatus(message, tone = "") {
  statusLine.textContent = message;
  statusLine.className = `status-line ${tone}`.trim();
}

function setDiff(diff, meta) {
  routeDiff.textContent = diff;
  routeDiffMeta.textContent = meta;
}

function applySummary(summary) {
  routeCount.textContent = summary.route_count;
  upstreamCount.textContent = summary.upstream_count;
  globalPluginCount.textContent = summary.global_plugin_count;
  configuredPluginCount.textContent = summary.configured_plugin_count;
}

function renderProtocolFilter(protocols) {
  const currentValue = protocolFilter.value || "ALL";
  protocolFilter.innerHTML = '<option value="ALL">전체 프로토콜</option>';

  Object.keys(protocols).forEach((protocol) => {
    const option = document.createElement("option");
    option.value = protocol;
    option.textContent = protocol;
    protocolFilter.appendChild(option);
  });

  protocolFilter.value = Object.keys(protocols).includes(currentValue) ? currentValue : "ALL";
}

function renderProtocolPills(protocols) {
  protocolPills.innerHTML = "";

  Object.entries(protocols).forEach(([protocol, count]) => {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = `${protocol} ${count}`;
    protocolPills.appendChild(pill);
  });
}

function renderPluginUsage(items) {
  pluginUsage.innerHTML = "";

  if (!items.length) {
    const empty = document.createElement("li");
    empty.textContent = "적용된 플러그인이 없습니다.";
    pluginUsage.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("li");
    row.innerHTML = `<span>${item.name}</span><strong>${item.count}</strong>`;
    pluginUsage.appendChild(row);
  });
}

function filterRoutes() {
  const keyword = routeSearch.value.trim().toLowerCase();
  const protocol = protocolFilter.value;

  state.filteredRoutes = state.routes.filter((route) => {
    const matchesProtocol = protocol === "ALL" || route.protocol === protocol;
    const haystack = [
      route.id,
      route.description,
      route.path,
      route.upstream_type,
      route.plugins.join(" "),
    ]
      .join(" ")
      .toLowerCase();
    const matchesKeyword = !keyword || haystack.includes(keyword);
    return matchesProtocol && matchesKeyword;
  });
}

function renderRoutes() {
  routesTable.innerHTML = "";

  if (!state.filteredRoutes.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5">조건에 맞는 라우트가 없습니다.</td>';
    routesTable.appendChild(row);
    return;
  }

  state.filteredRoutes.forEach((route) => {
    const row = document.createElement("tr");
    if (route.id === state.selectedRouteId) {
      row.classList.add("active");
    }
    row.innerHTML = `
      <td>
        <div class="route-name">
          <strong>${route.id}</strong>
          <span class="subtle">${route.description || "설명 없음"}</span>
        </div>
      </td>
      <td><span class="pill">${route.protocol}</span></td>
      <td>
        <div class="route-name">
          <strong>${route.path}</strong>
          <span class="subtle">${route.methods.join(", ")}</span>
        </div>
      </td>
      <td>${route.target_count}</td>
      <td>${
        route.plugins.length
          ? route.plugins.map((name) => `<span class="tag">${name}</span>`).join(" ")
          : '<span class="subtle">없음</span>'
      }</td>
    `;
    row.addEventListener("click", () => {
      void selectRoute(route.id);
    });
    routesTable.appendChild(row);
  });
}

function defaultRouteTemplate() {
  return {
    id: "new-route",
    description: "",
    match: {
      protocol: "HTTP",
      path: "/api/new/**",
      methods: ["GET"],
      headers: {},
    },
    upstream: {
      type: "REST",
      targets: [{ url: "http://service:8000", weight: 100 }],
      timeout: 30.0,
      retry: {
        count: 3,
        backoff_factor: 0.3,
        status_codes: [502, 503, 504],
      },
      load_balance: "round_robin",
      hash_on: "client_ip",
      hash_key: null,
    },
    grpc: {
      cardinality: "unary_unary",
      timeout: null,
      wait_for_ready: true,
      secure: null,
      root_cert_file: null,
      inject_request_id: true,
      drop_metadata: ["host", ":authority"],
    },
    websocket: {
      connect_timeout: 10.0,
      inject_request_id: true,
      forward_headers: [],
      extra_headers: {},
    },
    plugins: [],
    strip_prefix: false,
    preserve_host: false,
  };
}

function populateForm(route) {
  formRouteId.value = route.id || "";
  formRouteDescription.value = route.description || "";
  formRouteProtocol.value = (route.match?.protocol || "HTTP").toUpperCase();
  formUpstreamType.value = (route.upstream?.type || "REST").toUpperCase();
  formRoutePath.value = route.match?.path || "/";
  formRouteMethods.value = Array.isArray(route.match?.methods)
    ? route.match.methods.join(",")
    : "GET";
  formTargetUrl.value = route.upstream?.targets?.[0]?.url || "";
  formTargetWeight.value = String(route.upstream?.targets?.[0]?.weight || 100);
  formLoadBalance.value = route.upstream?.load_balance || "round_robin";
  formPlugins.value = Array.isArray(route.plugins)
    ? route.plugins.map((plugin) => plugin.name).join(",")
    : "";
}

function setEditorRoute(route, sourceId = "") {
  routeEditor.value = JSON.stringify(route, null, 2);
  state.editorSourceId = sourceId;
  state.selectedRouteId = sourceId;
  populateForm(route);
  routeMeta.textContent = sourceId ? `${sourceId} 편집 중` : "새 라우트 생성 모드";
  renderRoutes();
}

function parseEditorRoute() {
  return JSON.parse(routeEditor.value);
}

function buildRouteFromForm(baseRoute) {
  const route = structuredClone(baseRoute);
  route.id = formRouteId.value.trim() || route.id;
  route.description = formRouteDescription.value.trim();
  route.match = route.match || {};
  route.upstream = route.upstream || {};
  route.match.protocol = formRouteProtocol.value.toUpperCase();
  route.match.path = formRoutePath.value.trim() || "/";
  route.match.methods = formRouteMethods.value
    .split(",")
    .map((token) => token.trim().toUpperCase())
    .filter(Boolean);
  route.match.headers = route.match.headers || {};

  route.upstream.type = formUpstreamType.value.toUpperCase();
  route.upstream.targets = [
    {
      url: formTargetUrl.value.trim() || "http://service:8000",
      weight: Number.parseInt(formTargetWeight.value, 10) || 100,
    },
  ];
  route.upstream.load_balance = formLoadBalance.value;
  route.upstream.timeout = route.upstream.timeout || 30.0;
  route.upstream.retry = route.upstream.retry || {
    count: 3,
    backoff_factor: 0.3,
    status_codes: [502, 503, 504],
  };
  route.upstream.hash_on = route.upstream.hash_on || "client_ip";

  const pluginNames = formPlugins.value
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);
  route.plugins = pluginNames.map((name) => ({
    name,
    enabled: true,
    config: {},
  }));

  return route;
}

function applyFormToEditor() {
  try {
    const baseRoute = routeEditor.value.trim() ? parseEditorRoute() : defaultRouteTemplate();
    const route = buildRouteFromForm(baseRoute);
    setEditorRoute(route, state.editorSourceId);
    setStatus("폼 값을 에디터에 반영했습니다.", "success");
  } catch (error) {
    setStatus(`폼 적용 실패: ${messageFromError(error)}`, "error");
  }
}

function createNewRoute() {
  state.selectedRouteId = "";
  setEditorRoute(defaultRouteTemplate(), "");
  setDiff("No changes", "신규 라우트는 검증 후 저장하면 config/routes.yaml에 추가됩니다.");
  setStatus("신규 라우트 템플릿을 준비했습니다.", "success");
}

async function selectRoute(routeId) {
  state.selectedRouteId = routeId;
  renderRoutes();

  try {
    const route = await fetchJson(`/api/v1/routes/${encodeURIComponent(routeId)}`);
    setEditorRoute(route, routeId);
    setDiff(
      "No changes",
      `${route.id} 라우트가 편집기에 로드되었습니다. 검증을 실행하면 현재 설정과의 diff가 표시됩니다.`,
    );
    setStatus(`${routeId} 상세 구성을 불러왔습니다.`, "success");
  } catch (error) {
    routeMeta.textContent = "라우트 상세를 불러오지 못했습니다.";
    routeEditor.value = "";
    setStatus("라우트 상세 조회에 실패했습니다.", "error");
  }
}

async function validateRoute() {
  try {
    const route = parseEditorRoute();
    const params = state.editorSourceId
      ? `?current_route_id=${encodeURIComponent(state.editorSourceId)}`
      : "";
    const payload = await fetchJson(`/api/v1/routes/preview${params}`, {
      method: "POST",
      body: JSON.stringify(route),
    });
    routeEditor.value = JSON.stringify(payload.normalized_route, null, 2);
    populateForm(payload.normalized_route);
    setDiff(
      payload.diff,
      payload.mode === "create"
        ? "신규 생성으로 저장됩니다."
        : `${state.editorSourceId} 기준 변경 diff입니다.`,
    );
    setStatus("라우트 검증이 완료되었습니다.", "success");
  } catch (error) {
    setStatus(`검증 실패: ${messageFromError(error)}`, "error");
  }
}

async function saveRoute() {
  try {
    const route = parseEditorRoute();
    const isUpdate = Boolean(state.editorSourceId);
    const url = isUpdate
      ? `/api/v1/routes/${encodeURIComponent(state.editorSourceId)}`
      : "/api/v1/routes";
    const method = isUpdate ? "PUT" : "POST";
    const payload = await fetchJson(url, {
      method,
      body: JSON.stringify(route),
    });

    state.selectedRouteId = payload.route.id;
    state.editorSourceId = payload.route.id;
    await loadDashboard();
    await loadHistory();
    await selectRoute(payload.route.id);
    setStatus(
      isUpdate
        ? `${payload.route.id} 라우트를 저장했습니다.`
        : `${payload.route.id} 라우트를 생성했습니다.`,
      "success",
    );
  } catch (error) {
    setStatus(`저장 실패: ${messageFromError(error)}`, "error");
  }
}

async function deleteRoute() {
  const targetId = state.editorSourceId;
  if (!targetId) {
    setStatus("삭제할 기존 라우트를 먼저 선택해 주세요.", "error");
    return;
  }

  if (!window.confirm(`${targetId} 라우트를 삭제할까요?`)) {
    return;
  }

  try {
    await fetchJson(`/api/v1/routes/${encodeURIComponent(targetId)}`, {
      method: "DELETE",
    });
    await loadDashboard();
    await loadHistory();
    createNewRoute();
    setStatus(`${targetId} 라우트를 삭제했습니다.`, "success");
  } catch (error) {
    setStatus(`삭제 실패: ${messageFromError(error)}`, "error");
  }
}

async function reloadConfig() {
  try {
    setStatus("설정을 다시 불러오는 중입니다.");
    await fetchJson("/api/v1/reload", { method: "POST" });
    await loadDashboard();
    setStatus("설정 리로드가 완료되었습니다.", "success");
  } catch (error) {
    setStatus(`리로드 실패: ${messageFromError(error)}`, "error");
  }
}

function renderHistory() {
  historyTable.innerHTML = "";
  if (!state.historyEntries.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5">변경 이력이 없습니다.</td>';
    historyTable.appendChild(row);
    return;
  }

  state.historyEntries.forEach((entry) => {
    const row = document.createElement("tr");
    const time = new Date(entry.timestamp).toLocaleString();
    row.innerHTML = `
      <td>${time}</td>
      <td>${entry.action}</td>
      <td>${entry.route_id}</td>
      <td>${entry.actor_key_id || "-"}</td>
      <td><button class="rollback-btn">복구</button></td>
    `;
    const rollbackButton = row.querySelector(".rollback-btn");
    rollbackButton.addEventListener("click", async () => {
      await rollbackEntry(entry.id);
    });
    historyTable.appendChild(row);
  });
}

async function loadHistory() {
  try {
    const payload = await fetchJson("/api/v1/routes/history?limit=30");
    state.historyEntries = payload.entries || [];
    renderHistory();
  } catch (error) {
    setStatus(`이력 조회 실패: ${messageFromError(error)}`, "error");
  }
}

async function rollbackEntry(entryId) {
  if (!window.confirm(`이력 ${entryId} 기준으로 롤백할까요?`)) {
    return;
  }
  try {
    await fetchJson(`/api/v1/routes/history/${encodeURIComponent(entryId)}/rollback`, {
      method: "POST",
    });
    await loadDashboard();
    await loadHistory();
    setStatus(`롤백이 완료되었습니다. (${entryId})`, "success");
  } catch (error) {
    setStatus(`롤백 실패: ${messageFromError(error)}`, "error");
  }
}

function renderKeys() {
  keysTable.innerHTML = "";
  if (!state.keys.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5">등록된 키가 없습니다.</td>';
    keysTable.appendChild(row);
    return;
  }

  state.keys.forEach((keyRecord) => {
    const row = document.createElement("tr");
    const createdAt = keyRecord.created_at ? new Date(keyRecord.created_at).toLocaleString() : "-";
    row.innerHTML = `
      <td>${keyRecord.id}</td>
      <td>${keyRecord.role}</td>
      <td>${keyRecord.active ? "active" : "inactive"}</td>
      <td>${createdAt}</td>
      <td><button class="rollback-btn" ${keyRecord.active ? "" : "disabled"}>비활성화</button></td>
    `;
    const deactivateButton = row.querySelector(".rollback-btn");
    deactivateButton.addEventListener("click", async () => {
      if (!keyRecord.active) {
        return;
      }
      await deactivateKey(keyRecord.id);
    });
    keysTable.appendChild(row);
  });
}

async function loadKeys() {
  try {
    const payload = await fetchJson("/api/v1/admin/keys");
    state.keys = payload.keys || [];
    renderKeys();
  } catch (error) {
    setStatus(`키 조회 실패: ${messageFromError(error)}`, "error");
  }
}

async function rotateKey() {
  try {
    const payload = await fetchJson("/api/v1/admin/keys/rotate", {
      method: "POST",
      body: JSON.stringify({
        role: rotateKeyRole.value,
        label: rotateKeyLabel.value.trim(),
      }),
    });
    newKeyBox.classList.remove("hidden");
    newKeyValue.textContent = JSON.stringify(payload.new_key, null, 2);
    await loadKeys();
    setStatus("키 회전이 완료되었습니다. 새 키를 안전하게 보관해 주세요.", "success");
  } catch (error) {
    setStatus(`키 회전 실패: ${messageFromError(error)}`, "error");
  }
}

async function deactivateKey(keyId) {
  if (!window.confirm(`${keyId} 키를 비활성화할까요?`)) {
    return;
  }
  try {
    await fetchJson(`/api/v1/admin/keys/${encodeURIComponent(keyId)}/deactivate`, {
      method: "POST",
    });
    await loadKeys();
    setStatus(`${keyId} 키를 비활성화했습니다.`, "success");
  } catch (error) {
    setStatus(`키 비활성화 실패: ${messageFromError(error)}`, "error");
  }
}

async function loadDashboard() {
  if (!state.adminKey) {
    setStatus("Admin Key를 입력해 주세요.", "error");
    return;
  }

  try {
    const pendingRouteId = state.selectedRouteId || state.editorSourceId;
    setStatus("대시보드를 불러오는 중입니다.");
    const payload = await fetchJson("/api/v1/dashboard");
    state.routes = payload.routes;
    renderProtocolFilter(payload.protocols);
    filterRoutes();
    applySummary(payload.summary);
    renderProtocolPills(payload.protocols);
    renderPluginUsage(payload.plugin_usage);
    renderRoutes();

    const nextRouteId = payload.routes.some((route) => route.id === pendingRouteId)
      ? pendingRouteId
      : state.filteredRoutes[0]?.id;

    if (nextRouteId) {
      await selectRoute(nextRouteId);
    } else if (!routeEditor.value.trim()) {
      createNewRoute();
    }

    await loadHistory();
    await loadKeys();
    setStatus(
      `${payload.gateway.name} ${payload.gateway.version} · ${payload.gateway.environment}`,
      "success",
    );
  } catch (error) {
    setStatus(`대시보드 로드 실패: ${messageFromError(error)}`, "error");
  }
}

createNewRoute();

if (state.adminKey) {
  void loadDashboard();
}
