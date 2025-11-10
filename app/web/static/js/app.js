const state = {
  locales: {},
  language: "fr",
  currentView: "player",
  statusTimer: null,
  logsTimer: null,
  lastStatus: null,
  schedule: null,
  syncSchedule: null
};

const PASSWORD = "12341234";

document.addEventListener("DOMContentLoaded", () => {
  initialise().catch((error) => console.error("Initialisation failed", error));
});

async function initialise() {
  await loadLocales();
  bindEvents();
  await loadSettings();
  applyLocalization();
  await refreshStatus();
  scheduleStatusRefresh();
}

async function loadLocales() {
  const languages = ["fr", "en"];
  await Promise.all(
    languages.map(async (lang) => {
      const response = await fetch(`/locales/${lang}.json`).catch(() => null);
      if (response && response.ok) {
        state.locales[lang] = await response.json();
      }
    })
  );
}

function bindEvents() {
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  document.getElementById("btnQuickLanguage").addEventListener("click", async () => {
    const next = state.language === "fr" ? "en" : "fr";
    await updateLanguage(next);
  });

  document.getElementById("languageSelect").addEventListener("change", async (event) => {
    await updateLanguage(event.target.value);
  });

  document.getElementById("btnPlayPause").addEventListener("click", async () => {
    await postJSON("/api/control/play-pause");
    await refreshStatus();
  });

  document.getElementById("btnPrevious").addEventListener("click", async () => {
    await postJSON("/api/control/previous");
    await refreshStatus();
  });

  document.getElementById("btnNext").addEventListener("click", async () => {
    await postJSON("/api/control/next");
    await refreshStatus();
  });

  document.getElementById("btnRefreshPlaylist").addEventListener("click", refreshPlaylist);

  document.getElementById("volumeSlider").addEventListener("input", (event) => {
    document.getElementById("volumeValue").textContent = `${event.target.value}%`;
  });

  document.getElementById("volumeSlider").addEventListener("change", async (event) => {
    await postJSON("/api/control/volume", { level: Number(event.target.value) });
  });

  document.getElementById("btnUpdateVideos").addEventListener("click", async () => {
    await runSync();
  });

  document.getElementById("btnOpenRclone").addEventListener("click", () => {
    const password = prompt(t("dialogs.passwordPrompt", "Password"));
    if (password === PASSWORD) {
      switchView("rclone");
    } else if (password !== null) {
      showToast(t("dialogs.invalidPassword", "Invalid password"), true);
    }
  });

  document.getElementById("btnRestart").addEventListener("click", async () => {
    const confirmed = confirm("Redémarrer la machine ?");
    if (!confirmed) {
      return;
    }
    try {
      await postJSON("/api/system/restart");
      showToast("Restart command sent");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  document.getElementById("btnCreateLink").addEventListener("click", async () => {
    const token = document.getElementById("rcloneToken").value.trim();
    const remotePath = document.getElementById("rcloneRemotePath").value.trim();
    if (!token) {
      showToast("Token required", true);
      return;
    }
    try {
      await postJSON("/api/rclone/config", { token, remote_path: remotePath || null });
      showToast("Configuration saved");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  document.getElementById("btnTestConnection").addEventListener("click", async () => {
    await runRcloneAction("/api/rclone/test");
  });

  document.getElementById("btnSyncNow").addEventListener("click", async () => {
    await runSync();
  });

  document.getElementById("scheduleEnabled").addEventListener("change", async () => {
    handleScheduleToggle();
    try {
      await saveSchedule({ silent: true });
    } catch (error) {
      console.error("Failed to auto-save schedule", error);
    }
  });
  document.querySelectorAll(".day-pill").forEach((button) => {
    button.addEventListener("click", () => {
      button.classList.toggle("active");
    });
  });
  document.getElementById("btnSaveSchedule").addEventListener("click", async () => {
    await saveSchedule();
  });

  document.getElementById("syncEnabled").addEventListener("change", async () => {
    handleSyncToggle();
    try {
      await saveSyncSchedule({ silent: true });
    } catch (error) {
      console.error("Failed to auto-save sync schedule", error);
    }
  });

  document.getElementById("btnSaveSync").addEventListener("click", async () => {
    await saveSyncSchedule();
  });
}

async function loadSettings() {
  const summary = await getJSON("/api/settings/summary");
  state.language = summary.language || "fr";
  document.getElementById("languageSelect").value = state.language;
  document.getElementById("localFolder").value = summary.local_directory || "";
  document.getElementById("remoteName").value = summary.remote_name || "";
  document.getElementById("remotePath").value = summary.remote_path || "";
  document.getElementById("rcloneConfigPath").value = summary.rclone_config_path || "";
  document.getElementById("rcloneRemotePath").value = summary.remote_path || "";
  document.getElementById("rcloneRemoteName").value = summary.remote_name || "";
  document.getElementById("rcloneLocalFolder").value = summary.local_directory || "";
  state.schedule = summary.schedule || null;
  state.syncSchedule = summary.sync_schedule || null;
  updateScheduleForm(state.schedule);
  updateSyncForm(state.syncSchedule);
  updateLanguageToggle();
}

function applyLocalization() {
  const elements = {
    appTitle: "appTitle",
    navPlayer: "nav.player",
    navSettings: "nav.settings",
    navRclone: "nav.rclone",
    playerNowPlaying: "player.nowPlaying",
    playerStateLabel: "player.stateLabel",
    playerCurrentLabel: "player.currentLabel",
    volumeLabel: "player.volume",
    playlistTitle: "player.playlist",
    playlistEmpty: "player.empty",
    btnPlayPause: "buttons.playPause",
    btnPrevious: "buttons.previous",
    btnNext: "buttons.next",
    btnRefreshPlaylist: "buttons.refresh",
    settingsTitle: "settings.title",
    languageLabel: "settings.language",
    localFolderLabel: "settings.localFolder",
    remoteNameLabel: "settings.remoteName",
    remotePathLabel: "settings.remotePath",
    rcloneConfigLabel: "settings.rcloneConfig",
    btnUpdateVideos: "buttons.updateVideos",
    btnOpenRclone: "buttons.openRclone",
    btnRestart: "buttons.restart",
    rcloneTitle: "rclone.title",
    rcloneTokenLabel: "rclone.tokenLabel",
    rcloneRemotePathLabel: "rclone.remoteFolderLabel",
    rcloneRemoteNameLabel: "rclone.remoteNameLabel",
    rcloneLocalFolderLabel: "rclone.localFolderLabel",
    btnCreateLink: "buttons.createLink",
      btnTestConnection: "buttons.testConnection",
      btnSyncNow: "rclone.syncButton",
      rcloneLogsTitle: "rclone.logs",
      btnQuickLanguage: "buttons.changeLanguage",
      scheduleTitle: "schedule.title",
      scheduleEnableLabel: "schedule.enable",
      scheduleStartLabel: "schedule.start",
      scheduleEndLabel: "schedule.end",
      scheduleDaysLabel: "schedule.days",
      scheduleHelp: "schedule.help",
      btnSaveSchedule: "buttons.saveSchedule",
      syncTitle: "sync.title",
      syncEnableLabel: "sync.enable",
      syncTimeLabel: "sync.time",
      syncHelp: "sync.help",
      btnSaveSync: "buttons.saveSyncSchedule"
    };

  Object.entries(elements).forEach(([id, key]) => {
    const element = document.getElementById(id);
    if (element) {
      element.textContent = t(key, element.textContent);
    }
  });
  ["playerStateLabel", "playerCurrentLabel"].forEach((id) => {
    const element = document.getElementById(id);
    if (element && !element.textContent.endsWith(":")) {
      element.textContent = `${element.textContent}:`;
    }
  });
  updateDayLabels();
}

function t(path, fallback = "") {
  const locale = state.locales[state.language] || {};
  const value = path.split(".").reduce((acc, key) => (acc ? acc[key] : undefined), locale);
  return value ?? fallback;
}

function updateLanguageToggle() {
  const button = document.getElementById("btnQuickLanguage");
  button.textContent = state.language.toUpperCase();
}

async function updateLanguage(language) {
  if (!state.locales[language]) {
    return;
  }
  await postJSON("/api/settings/language", { language });
  state.language = language;
  document.getElementById("languageSelect").value = language;
  updateLanguageToggle();
  applyLocalization();
}

async function refreshStatus() {
  try {
    const status = await getJSON("/api/status");
    state.lastStatus = status;
    const volume = Number(status.vlc?.volume_percent ?? 0);
    const slider = document.getElementById("volumeSlider");
    slider.value = volume;
    document.getElementById("volumeValue").textContent = `${volume}%`;
    document.getElementById("playerStateValue").textContent = formatPlayerState(status.vlc?.state);
    const track = status.vlc?.current_track ? extractTrackName(status.vlc.current_track) : "";
    document.getElementById("playerCurrentValue").textContent = track || t("player.noVideo", "None");
    updatePlaylist(status.videos || []);
  } catch (error) {
    console.error("Failed to refresh status", error);
    document.getElementById("playerStateValue").textContent = formatPlayerState(null);
    document.getElementById("playerCurrentValue").textContent = t("player.noVideo", "None");
  }
}

function formatPlayerState(value) {
  if (!value) {
    return t("playerStates.unknown", "Not initialised");
  }
  const key = String(value).toLowerCase().trim();
  return t(`playerStates.${key}`, capitalizeFirst(key));
}

function capitalizeFirst(text) {
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function extractTrackName(raw) {
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return decodeURIComponent(url.pathname.split("/").pop());
  } catch {
    return raw.split("/").pop();
  }
}

function updatePlaylist(videos) {
  const list = document.getElementById("playlist");
  const emptyMessage = document.getElementById("playlistEmpty");
  list.innerHTML = "";
  if (!videos.length) {
    emptyMessage.classList.remove("hidden");
    return;
  }
  emptyMessage.classList.add("hidden");
  videos.forEach((video) => {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = video.name;
    const action = document.createElement("button");
    action.textContent = t("buttons.insert", "Insert");
    action.addEventListener("click", async (event) => {
      event.stopPropagation();
      await postJSON("/api/playlist/insert", { filename: video.name });
      showToast(t("messages.commandSent", "Command sent"));
    });
    item.appendChild(name);
    item.appendChild(action);
    list.appendChild(item);
  });
}

async function refreshPlaylist() {
  const media = await getJSON("/api/media");
  updatePlaylist(media.videos || []);
}

function updateScheduleForm(schedule) {
  const data = schedule || {};
  const enabled = Boolean(data.enabled);
  document.getElementById("scheduleEnabled").checked = enabled;
  document.getElementById("scheduleStart").value = data.start || "08:00";
  document.getElementById("scheduleEnd").value = data.end || "20:00";
  const activeDays = new Set((data.days || []).map((day) => Number(day)));
  document.querySelectorAll(".day-pill").forEach((button) => {
    const day = Number(button.dataset.day);
    button.classList.toggle("active", activeDays.has(day));
  });
  handleScheduleToggle();
}

function handleScheduleToggle() {
  const enabled = document.getElementById("scheduleEnabled").checked;
  const container = document.getElementById("scheduleFields");
  container.classList.toggle("disabled", !enabled);
}

function collectScheduleForm() {
  const enabled = document.getElementById("scheduleEnabled").checked;
  const start = document.getElementById("scheduleStart").value || "00:00";
  const end = document.getElementById("scheduleEnd").value || "00:00";
  const days = Array.from(document.querySelectorAll(".day-pill.active")).map((button) =>
    Number(button.dataset.day)
  );
  return { enabled, start, end, days };
}

async function saveSchedule(options = {}) {
  const silent = Boolean(options.silent);
  const payload = collectScheduleForm();
  try {
    await postJSON("/api/settings/schedule", payload);
    await loadSettings();
    if (!silent) {
      showToast(t("messages.scheduleSaved", "Schedule saved"));
    }
  } catch (error) {
    showToast(error.message, true);
    throw error;
  }
}

function updateDayLabels() {
  const locale = state.locales[state.language] || {};
  const labels = Array.isArray(locale.weekdays?.short)
    ? locale.weekdays.short
    : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  document.querySelectorAll(".day-pill").forEach((button) => {
    const day = Number(button.dataset.day);
    button.textContent = labels[day] || button.textContent;
  });
}

function updateSyncForm(syncSchedule) {
  const data = syncSchedule || {};
  const enabled = Boolean(data.enabled ?? true);
  document.getElementById("syncEnabled").checked = enabled;
  document.getElementById("syncTime").value = data.time || "06:00";
  handleSyncToggle();
}

function handleSyncToggle() {
  const enabled = document.getElementById("syncEnabled").checked;
  const container = document.getElementById("syncFields");
  container.classList.toggle("disabled", !enabled);
}

function collectSyncScheduleForm() {
  const enabled = document.getElementById("syncEnabled").checked;
  const time = document.getElementById("syncTime").value || "06:00";
  return { enabled, time };
}

async function saveSyncSchedule(options = {}) {
  const silent = Boolean(options.silent);
  const payload = collectSyncScheduleForm();
  try {
    await postJSON("/api/settings/sync-schedule", payload);
    await loadSettings();
    if (!silent) {
      showToast(t("messages.syncScheduleSaved", "Sync schedule saved"));
    }
  } catch (error) {
    showToast(error.message, true);
    throw error;
  }
}

async function runSync() {
  showToast(t("messages.syncStarted", "Sync started"));
  const result = await runRcloneAction("/api/rclone/sync");
  if (result) {
    await refreshStatus();
  }
}

async function runRcloneAction(endpoint) {
  try {
    const response = await postJSON(endpoint);
    showToast(t("messages.syncCompleted", "Completed"));
    await refreshLogs();
    return response;
  } catch (error) {
    showToast(error.message, true);
    throw error;
  }
}

async function refreshLogs() {
  const logs = await getJSON("/api/rclone/logs");
  const output = document.getElementById("rcloneLogs");
  output.textContent = (logs.logs || []).join("\n");
  output.scrollTop = output.scrollHeight;
}

function switchView(view) {
  if (state.currentView === view) {
    return;
  }
  document.querySelectorAll(".view").forEach((section) => section.classList.remove("active"));
  document.querySelectorAll(".nav-button").forEach((button) => button.classList.remove("active"));
  document.getElementById(`view-${view}`).classList.add("active");
  const navButton = document.querySelector(`.nav-button[data-view="${view}"]`);
  if (navButton) {
    navButton.classList.add("active");
  }
  state.currentView = view;
  if (view === "rclone") {
    refreshLogs();
    if (!state.logsTimer) {
      state.logsTimer = setInterval(refreshLogs, 5000);
    }
  } else if (state.logsTimer) {
    clearInterval(state.logsTimer);
    state.logsTimer = null;
  }
}

function scheduleStatusRefresh() {
  if (state.statusTimer) {
    clearInterval(state.statusTimer);
  }
  state.statusTimer = setInterval(refreshStatus, 10000);
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}"
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.headers.get("content-type")?.includes("application/json")) {
    return response.json();
  }
  return {};
}

let toastTimeout;
function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.style.background = isError ? "rgba(239, 68, 68, 0.9)" : "rgba(59, 130, 246, 0.9)";
  toast.classList.remove("hidden");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.add("hidden");
  }, 4000);
}
