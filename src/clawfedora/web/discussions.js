"use strict";
/* Browser-only view. The backend owns history, agents, project claims and bridge auth. */
(() => {
  const $ = (id) => document.getElementById(id);
  const labels = {
    "chef-operations": "Mentor / chef d'opérations",
    "expert-recherche": "Expert recherche",
    "architecte-solutions": "Architecte solutions",
    "ingenieur-devops": "Ingénieur DevOps",
    "ingenieur-securite": "Ingénieur sécurité",
    "redacteur-pedagogique": "Rédacteur pédagogique",
    "auditeur-qualite": "Auditeur qualité",
  };
  let selected = null;
  let busy = false;
  let list = [];

  async function api(path, payload) {
    const response = await fetch(path, payload === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const value = await response.json().catch(() => ({error: "Réponse du serveur invalide"}));
    if (!response.ok) throw new Error(typeof value.error === "string"
      ? value.error : "Opération refusée");
    return value;
  }
  function messageError(text) {
    $("chat-warning").textContent = text || "";
  }
  function option(value, label) {
    const el = document.createElement("option");
    el.value = value;
    el.textContent = label;
    return el;
  }
  function renderHistory() {
    const wrap = $("chat-list");
    wrap.replaceChildren();
    if (!list.length) {
      const p = document.createElement("p");
      p.textContent = "Aucune discussion enregistrée.";
      wrap.append(p);
    }
    for (const item of list) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chat-item";
      button.setAttribute("aria-current", String(item.id === selected));
      const title = document.createElement("strong");
      title.textContent = item.title;
      const info = document.createElement("small");
      info.textContent = (item.project || "Sans projet") + " · " + (labels[item.agent] || item.agent)
        + (item.pending ? " · Réponse incertaine" : "");
      button.append(title, info);
      button.addEventListener("click", () => openChat(item.id));
      wrap.append(button);
    }
  }
  function renderChat(chat) {
    selected = chat.id;
    $("chat-title").textContent = chat.title;
    $("chat-context").textContent = (chat.project || "Sans projet") + " · " +
      (labels[chat.agent] || chat.agent) + " · Contexte verrouillé";
    const feed = $("chat-messages");
    feed.replaceChildren();
    for (const entry of chat.messages) {
      const bubble = document.createElement("article");
      bubble.className = "chat-message " + entry.role;
      const who = document.createElement("strong");
      who.textContent = entry.role === "user" ? "Vous" : "OpenClaw";
      const text = document.createElement("p");
      text.textContent = entry.content;
      bubble.append(who, text);
      feed.append(bubble);
    }
    feed.scrollTop = feed.scrollHeight;
    const blocked = Boolean(chat.pending);
    $("chat-input").disabled = blocked || busy;
    $("chat-send").disabled = blocked || busy;
    messageError(blocked
      ? "Tour interrompu ou incertain : vérifier l'état du projet. Aucune relance automatique."
      : "");
    renderHistory();
  }
  async function openChat(id) {
    if (busy) return;
    try { renderChat(await api("/api/chat?id=" + encodeURIComponent(id))); }
    catch (error) { messageError(error.message); }
  }
  async function load() {
    try {
      const [status, threads] = await Promise.all([
        api("/api/status"), api("/api/chats"),
      ]);
      list = threads.chats;
      $("new-agent").replaceChildren(...threads.agents.map(id =>
        option(id, labels[id] || id)));
      $("new-project").replaceChildren(option("", "Sans projet"),
        ...status.projects.map(item => option(item.project_id, item.title)));
      renderHistory();
      if (list.length) await openChat(list[0].id);
    } catch (error) { messageError(error.message); }
  }
  $("new-chat").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    try {
      const created = await api("/api/chat/new", {
        project: $("new-project").value || null, agent: $("new-agent").value,
      });
      list.unshift({
        id: created.id, title: created.title, project: created.project,
        agent: created.agent, updated: created.updated, pending: false,
      });
      renderChat(created);
      $("chat-input").focus();
    } catch (error) { messageError(error.message); }
  });
  $("chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selected || busy) return;
    const content = $("chat-input").value;
    if (!content.trim()) return;
    busy = true;
    $("chat-send").disabled = true;
    $("chat-input").disabled = true;
    messageError("OpenClaw traite votre message. Ne pas renvoyer une confirmation.");
    try {
      const updated = await api("/api/chat/send", {id: selected, message: content});
      $("chat-input").value = "";
      const index = list.findIndex(item => item.id === updated.id);
      if (index >= 0) {
        list[index].title = updated.title;
        list[index].updated = updated.updated;
        list[index].pending = false;
      }
      busy = false;
      renderChat(updated);
    } catch (error) {
      busy = false;
      messageError(error.message + " Vérifiez l'état du fil avant toute relance.");
      $("chat-input").disabled = false;
      $("chat-send").disabled = false;
      // The server may have persisted a pending action: reload the actual state.
      await openChat(selected);
    }
  });
  load();
})();
