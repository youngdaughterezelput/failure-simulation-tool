class ApiClient {
  constructor(controlPrefix = "/_simulator") {
    this.controlPrefix = controlPrefix;
  }

  async request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      cache: "no-store",
      headers: { "content-type": "application/json", ...(options.headers || {}) },
    });
    const text = response.status === 204 ? "" : await response.text();
    let body = null;
    if (text) {
      try { body = JSON.parse(text); }
      catch { body = text; }
    }
    if (!response.ok) {
      throw new Error(this.errorMessage(body, response.status));
    }
    return body;
  }

  controlPath(path) { return `${this.controlPrefix}${path}`; }
  get(path) { return this.request(this.controlPath(path)); }
  post(path, body) { return this.request(this.controlPath(path), { method: "POST", body: JSON.stringify(body) }); }
  delete(path) { return this.request(this.controlPath(path), { method: "DELETE" }); }

  errorMessage(body, status) {
    const detail = body?.detail || body;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => String(item.msg || item).replace(/^Value error, /, ""))
        .join("; ");
    }
    if (typeof detail === "string" && detail) return detail;
    return `Request failed with HTTP ${status}`;
  }

  async send(method, path) {
    const options = { method, headers: { "content-type": "application/json" } };
    if (!['GET', 'HEAD'].includes(method)) options.body = JSON.stringify({ demo: true });
    const response = await fetch(path, options);
    return { status: response.status };
  }
}

class Dashboard {
  constructor(api) {
    this.api = api;
    this.projects = [];
    this.rules = [];
    this.templates = [];
    this.states = [];
    this.selectedProjectId = null;
  }

  async start() {
    this.bindEvents();
    await this.refreshAll();
    document.querySelector("#health").textContent = "● Service online";
    document.querySelector("#health").classList.add("ok");
  }

  bindEvents() {
    document.querySelector("#refresh-all").addEventListener("click", (event) => {
      this.runRefresh(event.currentTarget, () => this.refreshAll(), "Refresh data");
    });
    document.querySelector("#refresh-history").addEventListener("click", (event) => {
      this.runRefresh(event.currentTarget, () => this.loadHistory(), "↻");
    });
    document.querySelector("#project-form").addEventListener("submit", (event) => this.createProject(event));
    document.querySelector("#rule-form").addEventListener("submit", (event) => this.createRule(event));
    document.querySelector("#rule-form [name=path]").addEventListener("input", (event) => {
      event.currentTarget.setCustomValidity("");
    });
  }

  async refreshAll() {
    try {
      [this.projects, this.rules, this.templates, this.states] = await Promise.all([
        this.api.get("/api/projects"),
        this.api.get("/api/rules"),
        this.api.get("/api/templates"),
        this.api.get("/api/rules/states"),
      ]);
      if (!this.projects.some((item) => item.id === this.selectedProjectId)) {
        this.selectedProjectId = this.projects[0]?.id || null;
      }
      this.renderProjects();
      this.renderRuleForm();
      this.renderRules();
      await this.loadHistory();
      this.showMessage("");
    } catch (error) {
      this.showMessage(error.message);
    }
  }

  async loadHistory() {
    try {
      const history = await this.api.get("/api/history?limit=50");
      const container = document.querySelector("#history");
      container.replaceChildren();
      document.querySelector("#history-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
      if (!history.length) return container.append(this.empty("No proxy traffic recorded yet."));
      history.forEach((entry) => {
        const card = this.element("article", "card");
        const title = this.element("div", "card-title");
        title.append(this.element("strong", "", `${entry.method} ${entry.path}`));
        title.append(this.element("span", `badge ${entry.outcome}`, entry.outcome));
        const reason = entry.decision_reason.replaceAll("_", " ");
        card.append(title, this.element("p", "", `HTTP ${entry.status_code} · ${reason} · ${entry.duration_ms} ms · ${new Date(entry.timestamp).toLocaleString()}`));
        container.append(card);
      });
    } catch (error) {
      this.showMessage(error.message);
    }
  }

  renderProjects() {
    const container = document.querySelector("#projects");
    container.replaceChildren();
    this.projects.forEach((project) => {
      const card = this.element("article", `card project-card${project.id === this.selectedProjectId ? " selected" : ""}`);
      const title = this.element("div", "card-title");
      title.append(this.element("strong", "", project.name));
      const remove = this.element("button", "text-button danger", "Delete");
      remove.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.deleteProject(project.id);
      });
      title.append(remove);
      card.append(title, this.element("p", "", project.description || "No description"));
      card.addEventListener("click", () => {
        this.selectedProjectId = project.id;
        this.renderProjects();
        this.renderRuleForm();
        this.renderRules();
      });
      container.append(card);
    });
    if (!this.projects.length) container.append(this.empty("Create a project to group rules."));
  }

  renderRuleForm() {
    const projectSelect = document.querySelector("#rule-form [name=project_id]");
    projectSelect.replaceChildren(...this.projects.map((project) => new Option(project.name, project.id)));
    if (this.selectedProjectId) projectSelect.value = this.selectedProjectId;
    const templateSelect = document.querySelector("#rule-form [name=template_id]");
    templateSelect.replaceChildren(...this.templates.map((template) => new Option(`${template.response.status} · ${template.name}`, template.id)));
  }

  renderRules() {
    const visible = this.rules.filter((rule) => rule.project_id === this.selectedProjectId);
    document.querySelector("#rule-count").textContent = visible.length;
    const container = document.querySelector("#rules");
    container.replaceChildren();
    if (!visible.length) return container.append(this.empty("No rules in this project."));
    visible.forEach((rule) => {
      const reserved = this.isReservedPath(rule.match.path);
      const state = this.states.find((item) => item.rule_id === rule.id) || { matched_count: 0, simulated_count: 0 };
      const card = this.element("article", "card");
      const title = this.element("div", "card-title");
      const identity = this.element("div", "");
      identity.append(this.element("span", "method", rule.match.method), document.createTextNode(" "), this.element("strong", "", rule.match.path));
      const actions = this.element("div", "actions");
      const send = this.element("button", "text-button send-button", "Send");
      send.addEventListener("click", () => this.sendRule(rule));
      send.disabled = reserved;
      if (reserved) send.title = "Reserved local path; delete and recreate this rule";
      const toggle = this.element("button", "text-button", rule.enabled ? "Disable" : "Enable");
      toggle.addEventListener("click", () => this.toggleRule(rule));
      toggle.disabled = reserved && !rule.enabled;
      const remove = this.element("button", "text-button danger", "Delete");
      remove.addEventListener("click", () => this.deleteRule(rule.id));
      const reset = this.element("button", "text-button", "Reset");
      reset.addEventListener("click", () => this.resetRule(rule.id));
      actions.append(send, toggle, reset, remove);
      title.append(identity, actions);
      const status = reserved ? "reserved local path · delete and recreate" : (rule.enabled ? "enabled" : "disabled");
      const limit = rule.behavior.max_simulations ?? "∞";
      const behavior = `${Math.round(rule.behavior.probability * 100)}% · matched ${state.matched_count} · simulated ${state.simulated_count}/${limit}`;
      card.append(title, this.element("p", "", `${rule.name} · HTTP ${rule.response.status} · ${status}`), this.element("p", "", behavior));
      container.append(card);
    });
  }

  async createProject(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const project = await this.api.post("/api/projects", { name: form.get("name"), description: form.get("description") });
      formElement.reset();
      this.selectedProjectId = project.id;
      await this.refreshAll();
    } catch (error) { this.showMessage(error.message); }
  }

  async deleteProject(id) {
    try {
      await this.api.delete(`/api/projects/${id}`);
      await this.refreshAll();
    } catch (error) { this.showMessage(error.message); }
  }

  async createRule(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const pathInput = formElement.querySelector("[name=path]");
    if (this.isReservedPath(form.get("path"))) {
      const message = "This path is reserved by the simulator control plane. Use a target API path such as /api/rules or /api/orders.";
      pathInput.setCustomValidity(message);
      pathInput.reportValidity();
      this.showMessage(message);
      return;
    }
    const payload = {
      project_id: form.get("project_id"),
      match: { method: form.get("method"), path: form.get("path") },
      behavior: {
        probability: Number(form.get("probability")) / 100,
        skip_matches: Number(form.get("skip_matches")),
        max_simulations: form.get("max_simulations") ? Number(form.get("max_simulations")) : null,
        seed: form.get("seed") ? Number(form.get("seed")) : null,
      },
    };
    if (form.get("name")) payload.name = form.get("name");
    try {
      await this.api.post(`/api/rules/from-template/${form.get("template_id")}`, payload);
      formElement.querySelector("[name=name]").value = "";
      this.rules = await this.api.get("/api/rules");
      this.states = await this.api.get("/api/rules/states");
      this.renderRules();
    } catch (error) { this.showMessage(error.message); }
  }

  async toggleRule(rule) {
    try {
      await this.api.post(`/api/rules/${rule.id}/${rule.enabled ? "disable" : "enable"}`);
      this.rules = await this.api.get("/api/rules");
      this.renderRules();
    } catch (error) { this.showMessage(error.message); }
  }

  async sendRule(rule) {
    try {
      const response = await this.api.send(rule.match.method, rule.match.path);
      this.showMessage(`${rule.match.method} ${rule.match.path} → HTTP ${response.status}`, "success");
      [this.states] = await Promise.all([
        this.api.get("/api/rules/states"),
        this.loadHistory(),
      ]);
      this.renderRules();
    } catch (error) { this.showMessage(error.message); }
  }

  async resetRule(id) {
    try {
      await this.api.post(`/api/rules/${id}/reset`);
      this.states = await this.api.get("/api/rules/states");
      this.renderRules();
      this.showMessage("Rule counters reset", "success");
    } catch (error) { this.showMessage(error.message); }
  }

  async deleteRule(id) {
    try {
      await this.api.delete(`/api/rules/${id}`);
      this.rules = await this.api.get("/api/rules");
      this.renderRules();
    } catch (error) { this.showMessage(error.message); }
  }

  async runRefresh(button, action, idleLabel) {
    if (button.disabled) return;
    button.disabled = true;
    button.classList.add("refreshing");
    button.textContent = idleLabel === "↻" ? "↻" : "Refreshing…";
    try {
      await action();
      if (idleLabel !== "↻") button.textContent = "Refreshed ✓";
    } finally {
      button.classList.remove("refreshing");
      window.setTimeout(() => {
        button.textContent = idleLabel;
        button.disabled = false;
      }, 700);
    }
  }

  showMessage(text, type = "error") {
    const message = document.querySelector("#message");
    message.textContent = text;
    message.hidden = !text;
    message.classList.toggle("success", type === "success");
  }

  empty(text) { return this.element("div", "empty", text); }
  isReservedPath(path) {
    return path === "/_simulator" || path.startsWith("/_simulator/");
  }
  element(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }
}

new Dashboard(new ApiClient()).start().catch((error) => {
  document.querySelector("#message").textContent = error.message;
  document.querySelector("#message").hidden = false;
});
