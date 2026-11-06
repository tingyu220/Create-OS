/* 战斗专家结果面板：只显示当前作品与章节的结果，采用仍需作者编辑并确认。 */
class CombatPanel {
  constructor({ projectId, chapter, submit, onStatus = () => {} }) {
    this.projectId = projectId;
    this.chapter = chapter;
    this.submit = submit;
    this.onStatus = onStatus;
    this.$ = id => document.getElementById(id);
    this.requests = new Map();
  }

  render(results = []) {
    const target = this.$("combat-results");
    if (!target) return;
    const chapter = typeof this.chapter === "function" ? this.chapter() : this.chapter;
    const visible = (results || []).filter(result => {
      if (result.project_id !== this.projectId) return false;
      const numbers = result.scope?.chapter_numbers;
      return Array.isArray(numbers) && numbers.includes(chapter);
    });
    target.replaceChildren(...visible.map(result => this.card(result)));
  }

  card(result) {
    const wrapper = document.createElement("article");
    wrapper.className = "combat-result";
    wrapper.dataset.resultId = result.result_id;
    const text = document.createElement("p");
    text.textContent = `建议：${result.reply || result.verdict || "战斗专家未提供说明"}`;
    wrapper.append(text);
    const section = (label, values) => {
      if (!Array.isArray(values) || !values.length) return;
      const item = document.createElement("p");
      item.textContent = `${label}：${values.join("；")}`;
      wrapper.append(item);
    };
    section("可选方案", result.alternatives);
    section("来源", result.evidence_refs);
    section("未知范围", result.unknowns);
    section("后续伏笔", result.foreshadowing);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "采用为本章场景候选";
    button.addEventListener("click", () => this.adopt(result));
    wrapper.append(button);
    return wrapper;
  }

  async request(instruction) {
    if (!this.submit) return;
    return this.submit(instruction, "analyze", { requested_expert: "combat" });
  }

  async adopt(result) {
    try {
      const sessionResponse = await fetch(`/api/story/session?project_id=${encodeURIComponent(this.projectId)}&scope=story`);
      const session = await sessionResponse.json();
      if (!sessionResponse.ok || !session.session_id) throw new Error(session.error?.message || "故事状态暂不可用");
      const viewResponse = await fetch(`/api/story?project_id=${encodeURIComponent(this.projectId)}&scope=story&session_id=${encodeURIComponent(session.session_id)}`);
      const view = await viewResponse.json();
      if (!viewResponse.ok) throw new Error(view.error?.message || "故事候选状态暂不可用");
      const target = { project_id: this.projectId, scope: "story", session_id: session.session_id };
      const payload = { result_id: result.result_id, expected_revision: view.candidate?.revision || 0 };
      const identity = JSON.stringify({ target, payload });
      if (!this.requests.has(identity)) {
        const key = `adopt-combat-${result.result_id}-${Date.now()}`;
        this.requests.set(identity, { command_id: "adopt_combat_candidate", request_id: key, actor: "作者", target, payload, expected_version: null, idempotency_key: key });
      }
      const response = await fetch("/api/commands/adopt-combat-candidate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.requests.get(identity)) });
      const value = await response.json();
      if (!response.ok || value.status !== "accepted") throw new Error(value.error?.message || "采用战斗建议失败");
      this.onStatus("已采用战斗建议，请编辑并确认故事候选后再用于写作。");
      return value;
    } catch (error) {
      this.onStatus(error.message);
      return undefined;
    }
  }
}
globalThis.CombatPanel = CombatPanel;
