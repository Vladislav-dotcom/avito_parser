const uploadForm = document.getElementById("uploadForm");
const uploadBtn = document.getElementById("uploadBtn");
const statusBox = document.getElementById("statusBox");
const progressBar = document.getElementById("progressBar");
const downloadBtn = document.getElementById("downloadBtn");
const fileInput = document.getElementById("fileInput");
const STORAGE_KEY = "avito_parser_current_job_id";
const JOB_ID_QUERY_PARAM = "job_id";

let pollingTimer = null;
let currentJobId = null;
let completionNotifiedForJobId = null;

function setStatus(text, type = "light") {
  statusBox.className = `alert alert-${type} mt-4 mb-3`;
  statusBox.textContent = `Статус: ${text}`;
}

function setProgress(value) {
  const progress = Math.max(0, Math.min(100, Number(value || 0)));
  progressBar.style.width = `${progress}%`;
  progressBar.textContent = `${progress}%`;
}

function updateUploadButtonState() {
  if (pollingTimer) {
    return;
  }
  const hasFile = Boolean(fileInput && fileInput.files && fileInput.files.length > 0);
  uploadBtn.disabled = !hasFile;
}

function getJobIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get(JOB_ID_QUERY_PARAM);
  return jobId ? jobId.trim() : "";
}

function setJobIdInUrl(jobId) {
  const url = new URL(window.location.href);
  if (jobId) {
    url.searchParams.set(JOB_ID_QUERY_PARAM, jobId);
  } else {
    url.searchParams.delete(JOB_ID_QUERY_PARAM);
  }
  window.history.replaceState({}, "", url);
}

function resetDownloadButton() {
  downloadBtn.classList.add("disabled");
  downloadBtn.setAttribute("aria-disabled", "true");
  downloadBtn.href = "#";
}

function enableDownloadButton(jobId) {
  downloadBtn.classList.remove("disabled");
  downloadBtn.setAttribute("aria-disabled", "false");
  downloadBtn.href = `/api/download/${jobId}`;
}

function saveCurrentJobId(jobId) {
  currentJobId = jobId;
  localStorage.setItem(STORAGE_KEY, jobId);
  setJobIdInUrl(jobId);
}

function clearCurrentJobId() {
  currentJobId = null;
  localStorage.removeItem(STORAGE_KEY);
  setJobIdInUrl("");
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

function playCompletionSound() {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gainNode.gain.value = 0.06;

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.start();
    setTimeout(() => {
      oscillator.stop();
      audioContext.close();
    }, 220);
  } catch (error) {
    // В некоторых браузерах звук без user interaction может блокироваться.
  }
}

async function fetchStatus(jobId) {
  const response = await fetch(`/api/status/${jobId}`);
  if (response.status === 401) {
    clearCurrentJobId();
    throw new Error("Сессия истекла. Выполни вход снова.");
  }
  if (response.status === 404) {
    clearCurrentJobId();
    throw new Error("Задача не найдена. Возможно, данные уже очищены.");
  }
  if (!response.ok) {
    throw new Error("Не удалось получить статус задачи.");
  }
  return response.json();
}

function formatEta(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds)) || Number(seconds) < 0) {
    return "";
  }
  const totalMinutes = Math.max(1, Math.round(Number(seconds) / 60));
  if (totalMinutes < 60) {
    return `~${totalMinutes} мин`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `~${hours} ч ${minutes} мин` : `~${hours} ч`;
}

function applyStatusToUI(jobId, status) {
  const processed = status.processed_rows || 0;
  const total = status.total_rows || 0;
  const percent = status.progress_percent || 0;
  const progressText = total > 0 ? `${processed}/${total} (${percent}%)` : "подготовка...";
  const etaText = formatEta(status.eta_seconds);
  const state = status.state || "queued";

  if (state === "queued") {
    setStatus("Задача в очереди...");
    setProgress(0);
    resetDownloadButton();
    uploadBtn.disabled = true;
    return;
  }

  if (state === "processing") {
    if (status.stale_warning) {
      setStatus(`Обработка приостановлена (${progressText}). Ожидаем автоматическое восстановление...`, "warning");
    } else if (etaText) {
      setStatus(`Анализ... ${progressText}. Осталось ${etaText}`);
    } else {
      setStatus(`Анализ... ${progressText}`);
    }
    setProgress(percent);
    resetDownloadButton();
    uploadBtn.disabled = true;
    return;
  }

  if (state === "finalizing") {
    setStatus("Обновление Excel...");
    setProgress(100);
    resetDownloadButton();
    uploadBtn.disabled = true;
    return;
  }

  if (state === "failed") {
    setStatus(`Ошибка: ${status.error || "неизвестно"}`, "danger");
    resetDownloadButton();
    clearCurrentJobId();
    stopPolling();
    updateUploadButtonState();
    return;
  }

  if (status.result_ready) {
    setStatus("Анализ завершен. Можно скачать файл.", "success");
    setProgress(100);
    enableDownloadButton(jobId);
    updateUploadButtonState();
    if (completionNotifiedForJobId !== jobId) {
      playCompletionSound();
      completionNotifiedForJobId = jobId;
    }
    stopPolling();
    return;
  }

  setStatus(`Анализ... ${progressText}`);
  setProgress(status.progress_percent || 0);
}

async function pollOnce(jobId) {
  try {
    const status = await fetchStatus(jobId);
    applyStatusToUI(jobId, status);
  } catch (error) {
    setStatus(error.message, "danger");
    updateUploadButtonState();
    stopPolling();
  }
}

function startPolling(jobId) {
  stopPolling();
  pollOnce(jobId);

  pollingTimer = setInterval(() => {
    pollOnce(jobId);
  }, 2000);
}

function restoreJobStateOnLoad() {
  const jobIdFromUrl = getJobIdFromUrl();
  const savedJobId = jobIdFromUrl || localStorage.getItem(STORAGE_KEY);
  if (!savedJobId) {
    return;
  }
  saveCurrentJobId(savedJobId);
  setStatus("Восстановление состояния задачи...");
  uploadBtn.disabled = true;
  startPolling(savedJobId);
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  uploadBtn.disabled = true;
  completionNotifiedForJobId = null;
  resetDownloadButton();
  setProgress(0);
  setStatus("Загрузка файла...");

  const formData = new FormData(uploadForm);
  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Не удалось загрузить файл.");
    }

    saveCurrentJobId(payload.job_id);
    setStatus("Файл загружен. Задача поставлена в очередь.");
    startPolling(payload.job_id);
  } catch (error) {
    setStatus(error.message, "danger");
    updateUploadButtonState();
  }
});

downloadBtn.addEventListener("click", () => {
  if (!downloadBtn.classList.contains("disabled")) {
    setTimeout(() => {
      clearCurrentJobId();
      updateUploadButtonState();
      setStatus("Файл скачивается. Можно загрузить новый файл.", "success");
      completionNotifiedForJobId = null;
      resetDownloadButton();
      setProgress(0);
    }, 500);
  }
});

if (fileInput) {
  fileInput.addEventListener("change", updateUploadButtonState);
}

restoreJobStateOnLoad();
