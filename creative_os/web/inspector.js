const statusLabel = document.getElementById("inspector-status");
const output = document.getElementById("projection-json");
const refreshButton = document.getElementById("inspector-refresh");

async function loadProjection() {
  refreshButton.disabled = true;
  statusLabel.textContent = "正在读取完整投影…";
  try {
    const response = await fetch("/api/workspace", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    output.textContent = JSON.stringify(payload, null, 2);
    statusLabel.textContent = `读取完成 · ${payload.overall || "状态未提供"} · refresh ${payload.refresh_id || "未提供"}`;
  } catch (error) {
    output.textContent = "完整投影读取失败。请检查工作区查询服务后重试。";
    statusLabel.textContent = `读取失败 · ${error.message}`;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadProjection);
loadProjection();
