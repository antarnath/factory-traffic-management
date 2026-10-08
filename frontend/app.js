/* Factory Traffic Dashboard — polling + DOM updates + form submissions.
 *
 * The dashboard never decides traffic sequencing on its own. It only:
 *   1. Polls /api/junctions/{id}/status every 1s and renders the result.
 *   2. Polls /api/junctions/{id}/history every 5s and renders the feed.
 *   3. Submits user actions (manual control, simulation events) to the API.
 *
 * Same-origin, so all paths are relative.
 */
(function () {
  "use strict";

  // ---- State -------------------------------------------------------------
  const state = {
    junctionId: "A",
    lastStatus: null,
    lastHistory: null,
    connected: false,
    seqCounter: 100, // sequence_no baseline; bumped per vehicle event
    pendingSince: null, // ms timestamp when pending_command_id first appeared
  };

  // ---- DOM lookups -------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const junctionIdInput = $("junction-id");
  const junctionLabel   = $("junction-label");
  const connPill        = $("connection-pill");
  const modeBadge       = $("mode-badge");
  const phaseValue      = $("phase-value");
  const controllerValue = $("controller-value");
  const manualFlag      = $("manual-flag");
  const emergencyFlag   = $("emergency-flag");
  const pendingCmd      = $("pending-cmd");
  const latestPending   = $("latest-pending");
  const historyList     = $("history-list");
  const toast           = $("toast");
  const alertsList      = $("alerts-list");
  const alertsSummary   = $("alerts-summary");
  const alertsCard      = $("alerts-card");

  // ---- Utilities ---------------------------------------------------------

  function toastMsg(msg, kind) {
    toast.textContent = msg;
    toast.className = "toast toast-" + (kind || "info");
    setTimeout(() => toast.classList.add("hidden"), 3500);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;",
      '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function signalClass(state) {
    if (state === "RED")    return "sig-red";
    if (state === "YELLOW") return "sig-yellow";
    if (state === "GREEN")  return "sig-green";
    return "sig-other";
  }

  function queueClass(n) {
    if (n >= 8) return "very-high";
    if (n >= 4) return "high";
    return "";
  }

  // ---- Network -----------------------------------------------------------

  async function api(path, opts) {
    opts = opts || {};
    const res = await fetch(path, {
      method: opts.method || "GET",
      headers: Object.assign(
        { "Content-Type": "application/json" },
        opts.headers || {}
      ),
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (body && body.error) {
          detail = body.error.message || detail;
          if (body.error.details) {
            detail += " — " + JSON.stringify(body.error.details);
          }
        }
      } catch (e) { /* ignore */ }
      throw new Error(`${res.status} ${detail}`);
    }
    return res.json();
  }

  // ---- Polling -----------------------------------------------------------

  async function pollStatus() {
    const path = `/api/junctions/${encodeURIComponent(state.junctionId)}/status`;
    try {
      const status = await api(path);
      state.lastStatus = status;
      // Wrap each render in its own try/catch so a bug in one panel
      // doesn't kill the connection pill or skip the others.
      safeRender("status",      () => renderStatus(status));
      safeRender("intersection",() => renderIntersection(status));
      safeRender("alerts",      () => renderAlerts(status));
      setConnected(true);
    } catch (err) {
      setConnected(false);
    }
  }

  function safeRender(name, fn) {
    try { fn(); } catch (e) { console.warn("render failed:", name, e); }
  }

  async function pollHistory() {
    const path = `/api/junctions/${encodeURIComponent(state.junctionId)}/history?limit=20`;
    try {
      const data = await api(path);
      state.lastHistory = data;
      renderHistory(data);
    } catch (err) {
      // History is nice-to-have; don't change the connection pill.
    }
  }

  async function pollLatestPending() {
    const path = `/api/junctions/${encodeURIComponent(state.junctionId)}/pending-command`;
    try {
      const data = await api(path);
      latestPending.textContent = data.command_id || "(none)";
      latestPending.title = data.command_id || "";
    } catch (err) {
      latestPending.textContent = "(unknown)";
    }
  }

  function setConnected(ok) {
    state.connected = ok;
    connPill.textContent = ok ? "online" : "disconnected";
    connPill.className = "pill " + (ok ? "pill-online" : "pill-offline");
  }

  // ---- Rendering ---------------------------------------------------------

  function renderStatus(s) {
    modeBadge.textContent = s.mode;
    modeBadge.className = "badge badge-" + (s.mode || "automatic").toLowerCase();
    phaseValue.textContent = s.phase || "—";
    controllerValue.textContent = s.controller_status || "—";
    manualFlag.textContent = s.manual_override_active ? "YES" : "no";
    manualFlag.className = "value" + (s.manual_override_active ? " sig-yellow" : "");
    emergencyFlag.textContent = s.emergency_active ? "YES" : "no";
    emergencyFlag.className = "value" + (s.emergency_active ? " sig-red" : "");
    pendingCmd.textContent = s.pending_command_id || "—";

    const dirs = ["N", "S", "E", "W"];
    const full = { N: "NORTH", S: "SOUTH", E: "EAST", W: "WEST" };
    dirs.forEach((d) => {
      const q = (s.queues && s.queues[full[d]]) || 0;
      const el = $("q-" + d);
      el.textContent = q;
      el.className = "q " + queueClass(q);

      const desired = (s.desired_signals || {})[full[d]] || "—";
      const actual  = (s.actual_signals  || {})[full[d]] || "—";
      const dEl = $("d-" + d);
      const aEl = $("a-" + d);
      dEl.textContent = desired;
      dEl.className = signalClass(desired);
      aEl.textContent = actual;
      aEl.className = signalClass(actual);
    });
  }

  function renderIntersection(s) {
    const dirs = ["NORTH", "SOUTH", "EAST", "WEST"];
    dirs.forEach((d) => {
      const actual = (s.actual_signals || {})[d] || "OFF";
      const group  = document.querySelector(".signal-" + d.toLowerCase());
      if (!group) return;
      const lights = group.querySelectorAll(".light");
      // The housing always has 3 lights in this order: red, yellow, green.
      const red    = lights[0];
      const yellow = lights[1];
      const green  = lights[2];
      red.className    = "light" + (actual === "RED"    ? " on-red"    : "");
      yellow.className = "light" + (actual === "YELLOW" ? " on-yellow" : "");
      green.className  = "light" + (actual === "GREEN"  ? " on-green"  : "");
    });
  }

  // ---- Alerts ------------------------------------------------------------
  //
  // The backend is the source of truth for everything in this panel.
  // The frontend only classifies what the status payload already exposes:
  //   * controller_status:  ONLINE / OFFLINE / DEGRADED / WARNING / UNKNOWN
  //   * mode:                AUTOMATIC / MANUAL / EMERGENCY / DEGRADED
  //   * desired_signals vs actual_signals:  mismatches per direction
  //   * pending_command_id:  if set and controller is online, indicates a
  //                          command that hasn't been ACKed yet
  //
  // Each alert is one of:  "error"  (red)   — must be fixed / acknowledged
  //                         "warn"   (yellow)— degraded state
  //                         "ok"     (green) — explicit "all clear" only
  function computeAlerts(s) {
    const alerts = [];

    // 1) Controller status
    const cs = (s.controller_status || "").toUpperCase();
    if (cs === "OFFLINE") {
      alerts.push({
        level: "error",
        title: "Controller offline",
        detail: "The signal controller is unreachable. Junction is in DEGRADED mode.",
        tag: "OFFLINE",
      });
    } else if (cs === "DEGRADED") {
      alerts.push({
        level: "warn",
        title: "Controller degraded",
        detail: "The controller reports DEGRADED — signals may be unreliable.",
        tag: "DEGRADED",
      });
    } else if (cs === "WARNING" || cs === "UNKNOWN") {
      alerts.push({
        level: "warn",
        title: "Controller state unclear",
        detail: `Controller status is ${cs}. The backend treats it as a soft failure.`,
        tag: cs,
      });
    }

    // 2) Mode mismatch — if mode says DEGRADED but controller says ONLINE,
    //    the user should know the backend is in a degraded operating mode.
    if (s.mode === "DEGRADED" && cs !== "OFFLINE" && cs !== "DEGRADED") {
      alerts.push({
        level: "warn",
        title: "Operating in DEGRADED mode",
        detail: "Backend forced degraded mode (e.g. repeated sensor failures).",
        tag: "DEGRADED",
      });
    }

    // 3) Desired vs actual mismatch — per direction.
    //    If the backend wants GREEN but the controller says RED, that's a
    //    signal-failure / hardware-lag condition worth flagging.
    const dirs = ["NORTH", "SOUTH", "EAST", "WEST"];
    const mismatches = [];
    dirs.forEach((d) => {
      const desired = (s.desired_signals || {})[d];
      const actual  = (s.actual_signals  || {})[d];
      if (
        desired && actual &&
        desired !== actual &&
        !(desired === "RED" && actual === "RED") // both red is fine
      ) {
        mismatches.push(`${d} (want ${desired}, got ${actual})`);
      }
    });
    if (mismatches.length) {
      alerts.push({
        level: "warn",
        title: `Signal mismatch (${mismatches.length})`,
        detail: mismatches.join("; "),
        tag: "MISMATCH",
      });
    }

    // 4) Pending command that's been waiting too long.
    //    Heuristic: if a pending_command_id exists and the controller is
    //    ONLINE, it's been at least 1s since the last status fetch that
    //    still showed it. The backend has its own timeout; this is the
    //    dashboard's "you should look at this" hint.
    if (s.pending_command_id && cs === "ONLINE") {
      const waitMs = state.pendingSince ? (Date.now() - state.pendingSince) : 0;
      if (waitMs > 5000) {
        alerts.push({
          level: "warn",
          title: "Command unacknowledged",
          detail: `Pending ${s.pending_command_id} for ${Math.round(waitMs/1000)}s — controller hasn't ACKed.`,
          tag: "TIMEOUT",
        });
      }
    }

    // Track when a pending command first appears, so we can show wait time.
    if (s.pending_command_id && !state.pendingSince) {
      state.pendingSince = Date.now();
    } else if (!s.pending_command_id) {
      state.pendingSince = null;
    }

    return alerts;
  }

  function renderAlerts(s) {
    const alerts = computeAlerts(s);
    if (!alerts.length) {
      alertsList.innerHTML =
        '<li class="alert alert-ok"><span class="alert-dot"></span>' +
        '<span class="alert-title">All clear</span>' +
        '<span class="alert-tag">OK</span></li>';
      alertsSummary.textContent = "no active alerts";
      alertsCard.classList.remove("card-alert-active");
      return;
    }
    const hasError = alerts.some((a) => a.level === "error");
    alertsCard.classList.toggle("card-alert-active", hasError);
    alertsSummary.textContent =
      alerts.length + " active — " +
      alerts.filter((a) => a.level === "error").length + " critical, " +
      alerts.filter((a) => a.level === "warn").length  + " warning";
    alertsList.innerHTML = alerts.map((a) => {
      const cls = a.level === "error" ? "alert-error"
                : a.level === "warn"  ? "alert-warn"
                : "alert-ok";
      return (
        '<li class="alert ' + cls + '">' +
          '<span class="alert-dot"></span>' +
          '<span>' +
            '<span class="alert-title">' + escapeHtml(a.title) + '</span>' +
            ' <span class="alert-detail">' + escapeHtml(a.detail) + '</span>' +
          '</span>' +
          '<span class="alert-tag">' + escapeHtml(a.tag) + '</span>' +
        '</li>'
      );
    }).join("");
  }

  function renderHistory(data) {
    if (!data || !data.events || !data.events.length) {
      historyList.innerHTML = '<li class="muted">No events yet.</li>';
      return;
    }
    historyList.innerHTML = data.events.map((e) => {
      const ts = e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : "—";
      const payload = e.payload ? JSON.stringify(e.payload) : "";
      return `<li>
        <span class="ts">${escapeHtml(ts)}</span>
        <span class="evt">${escapeHtml(e.event_type)}</span>
        <span class="dir">${escapeHtml(e.direction || "")}</span>
        <span class="payload" title="${escapeHtml(payload)}">${escapeHtml(payload)}</span>
      </li>`;
    }).join("");
  }

  // ---- Form actions ------------------------------------------------------

  async function sendManual(direction) {
    try {
      const res = await api(
        `/api/junctions/${encodeURIComponent(state.junctionId)}/commands`,
        {
          method: "POST",
          body: {
            command: "MANUAL_GREEN_REQUEST",
            direction: direction,
          },
        }
      );
      toastMsg(`Manual override → ${direction}`, "success");
      // Refresh quickly so the user sees the effect.
      setTimeout(pollStatus, 200);
    } catch (err) {
      toastMsg("Manual override failed: " + err.message, "error");
    }
  }

  async function returnToAuto() {
    try {
      await api(
        `/api/junctions/${encodeURIComponent(state.junctionId)}/commands`,
        {
          method: "POST",
          body: { command: "RETURN_TO_AUTOMATIC" },
        }
      );
      toastMsg("Returned to AUTOMATIC", "success");
      setTimeout(pollStatus, 200);
    } catch (err) {
      toastMsg("Failed: " + err.message, "error");
    }
  }

  async function sendVehicle() {
    const type   = $("veh-type").value;
    const dir    = $("veh-dir").value;
    const vtype  = $("veh-vtype").value;
    const vid    = $("veh-vid").value.trim() || "v";
    const seq    = parseInt($("veh-seq").value, 10) || 1;
    const now    = new Date().toISOString();
    const eid    = `dash-${type}-${dir}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    try {
      await api("/api/sensor-events", {
        method: "POST",
        body: {
          event_id: eid,
          junction_id: state.junctionId,
          direction: dir,
          event_type: type,
          vehicle_id: vid,
          vehicle_type: vtype,
          sequence_no: seq,
          timestamp: now,
        },
      });
      toastMsg(`${type} on ${dir} (${vtype})`, "success");
      // Bump the sequence number for the next manual send.
      $("veh-seq").value = seq + 1;
      setTimeout(pollStatus, 200);
    } catch (err) {
      toastMsg("Vehicle event failed: " + err.message, "error");
    }
  }

  async function sendDevice() {
    const devType = $("dev-type").value;
    const status  = $("dev-status").value;
    const now     = new Date().toISOString();
    const eid     = `dash-dev-${Date.now()}`;
    try {
      await api("/api/device-events", {
        method: "POST",
        body: {
          event_id: eid,
          junction_id: state.junctionId,
          device_type: devType,
          status: status,
          timestamp: now,
        },
      });
      toastMsg(`Device ${devType} → ${status}`, "success");
      setTimeout(pollStatus, 200);
    } catch (err) {
      toastMsg("Device event failed: " + err.message, "error");
    }
  }

  async function sendAck() {
    const status      = $("ctrl-status").value;
    const actualState = $("ctrl-actual").value;
    if (!latestPending.textContent || latestPending.textContent === "(none)"
        || latestPending.textContent === "(unknown)") {
      toastMsg("No pending command to ACK. Force a manual override first.", "error");
      return;
    }
    const cmdId = latestPending.textContent;
    const now   = new Date().toISOString();
    try {
      await api("/api/controller-events", {
        method: "POST",
        body: {
          command_id: cmdId,
          junction_id: state.junctionId,
          status: status,
          actual_state: actualState,
          timestamp: now,
        },
      });
      toastMsg(`Sent ${status} for ${cmdId.slice(0, 18)}…`, "success");
      setTimeout(() => { pollStatus(); pollLatestPending(); }, 200);
    } catch (err) {
      toastMsg("ACK failed: " + err.message, "error");
    }
  }

  // ---- Wire up -----------------------------------------------------------

  function setJunction(id) {
    const trimmed = (id || "").trim();
    if (!trimmed) return;
    state.junctionId = trimmed;
    junctionLabel.textContent = trimmed;
    state.lastStatus = null;
    state.lastHistory = null;
    state.pendingSince = null;
    historyList.innerHTML = '<li class="muted">Loading…</li>';
    pollStatus();
    pollHistory();
    pollLatestPending();
  }

  function bindEvents() {
    junctionIdInput.addEventListener("change", () => setJunction(junctionIdInput.value));
    $("refresh-now").addEventListener("click", () => {
      pollStatus(); pollHistory(); pollLatestPending();
    });

    document.querySelectorAll(".btn-dir").forEach((b) => {
      b.addEventListener("click", () => sendManual(b.dataset.dir));
    });
    $("btn-return-auto").addEventListener("click", returnToAuto);

    $("btn-send-vehicle").addEventListener("click", sendVehicle);
    $("btn-send-device").addEventListener("click", sendDevice);
    $("btn-send-ack").addEventListener("click", sendAck);

    // Also submit forms with Enter.
    document.querySelectorAll(".form-row input").forEach((inp) => {
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const block = inp.closest(".form-block");
          const btn = block && block.querySelector("button");
          if (btn) btn.click();
        }
      });
    });
  }

  // ---- Boot --------------------------------------------------------------

  function boot() {
    bindEvents();
    setConnected(false);
    setJunction(junctionIdInput.value);
    setInterval(pollStatus, 1000);
    setInterval(pollHistory, 5000);
    setInterval(pollLatestPending, 2000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();