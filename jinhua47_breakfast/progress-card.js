// Lovelace card "custom:jinhua47-progress-card": today's steps as bars (grey until reached, then green),
// in the style of iding's 訂單狀態.
// Registered by the Jinhua47 Snídaně add-on (as a data: URL resource); reads the `steps` attribute of the sensor:
// [{label, done, date: "MM/DD", time: "HH:MM"}], plus `cancelled_at` for a cancelled order.
class Jinhua47ProgressCard extends HTMLElement {
  setConfig(config) {
    this.config = { entity: "sensor.jinhua47_breakfast", title: "Stav objednávky", ...config };
  }

  set hass(hass) {
    const state = hass.states[this.config.entity];
    const attrs = state ? state.attributes : {};
    const key = JSON.stringify([state && state.state, attrs.steps, attrs.cancelled_at]);
    if (key === this._key) return;
    this._key = key;
    this.render(state ? state.state : "", attrs.steps || [], attrs.cancelled_at || "");
  }

  render(state, steps, cancelledAt) {
    if (!this.card) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `
        <style>
          ha-card { padding: 20px 24px 24px; }
          h2 { margin: 0 0 24px; font-size: 1.6em; font-weight: 700; }
          .steps { display: grid; gap: 14px; }
          .bar { height: 8px; border-radius: 4px; background: var(--divider-color, #ddd); }
          .done .bar { background: var(--success-color, #43a047); }
          .label, .time { text-align: center; color: var(--secondary-text-color); font-size: 1.15em; }
          .label { margin-top: 12px; }
          .done .label { color: var(--primary-text-color); }
          .cancelled { color: #e05a4f; font-size: 1.3em; text-align: center; }
        </style>
        <ha-card><h2></h2><div class="body"></div></ha-card>`;
      this.card = this.shadowRoot.querySelector("ha-card");
    }
    this.shadowRoot.querySelector("h2").textContent = this.config.title;
    const body = this.shadowRoot.querySelector(".body");
    body.replaceChildren();
    if (state === "cancelled") {
      const line = document.createElement("div");
      line.className = "cancelled";
      line.textContent = "❌ Zrušeno" + (cancelledAt ? " " + cancelledAt : "");
      body.append(line);
      return;
    }
    const row = document.createElement("div");
    row.className = "steps";
    row.style.gridTemplateColumns = `repeat(${steps.length || 1}, 1fr)`;
    for (const step of steps) {
      const cell = document.createElement("div");
      cell.className = step.done ? "done" : "";
      const bar = document.createElement("div");
      bar.className = "bar";
      const label = document.createElement("div");
      label.className = "label";
      label.textContent = step.label;
      const time = document.createElement("div");
      time.className = "time";
      time.textContent = step.time ? `${step.date} ${step.time}` : " ";
      cell.append(bar, label, time);
      row.append(cell);
    }
    body.append(row);
  }

  getCardSize() {
    return 3;
  }
}

if (!customElements.get("jinhua47-progress-card")) {
  customElements.define("jinhua47-progress-card", Jinhua47ProgressCard);
}
window.customCards = window.customCards || [];
window.customCards.push({ type: "jinhua47-progress-card", name: "Jinhua47 stav objednávky" });
