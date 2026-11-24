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
  let selectedChat = null;
  let streamingEnabled = false;
  let expandedStreaming = false;
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
    selectedChat = chat;
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
      if (entry.role === "assistant" && Array.isArray(entry.artifacts)) {
        const files = document.createElement("div");
        files.className = "chat-files";
        for (const file of entry.artifacts) {
          const link = document.createElement("a");
          const query = new URLSearchParams({
            id: chat.id, receipt: file.receipt, format: file.format,
          });
          link.href = "/api/chat/artifact?" + query.toString();
          link.textContent = "Télécharger " + file.name;
          link.download = file.name;
          files.append(link);
        }
        if (files.childElementCount) bubble.append(files);
      }
      feed.append(bubble);
    }
    feed.scrollTop = feed.scrollHeight;
    const blocked = Boolean(chat.pending);
    $("chat-recovery").hidden = !blocked;
    $("recover-intent").textContent = blocked ? chat.pending.message : "";
    $("recover-confirm").checked = false;
    $("recover-confirm").disabled = busy;
    $("recover-submit").disabled = true;
    const recoveryLog = $("recovery-log");
    recoveryLog.replaceChildren();
    for (const entry of chat.recoveries || []) {
      const item = document.createElement("details");
      const title = document.createElement("summary");
      title.textContent = "Tour abandonné — effet inconnu · " +
        new Date(entry.recorded_at * 1000).toLocaleString("fr-FR");
      const content = document.createElement("p");
      content.textContent = entry.intent.message;
      item.append(title, content);
      recoveryLog.append(item);
    }
    $("chat-input").disabled = blocked || busy;
    $("chat-send").disabled = blocked || busy;
    messageError(blocked
      ? "Tour interrompu ou incertain : vérifier les effets avant de reprendre. Aucune relance automatique."
      : "");
    renderHistory();
  }
  async function openChat(id) {
    if (busy) return;
    try {
      const chat = await api("/api/chat?id=" + encodeURIComponent(id));
      const entry = list.find(item => item.id === chat.id);
      if (entry) {
        entry.pending = Boolean(chat.pending);
        entry.updated = chat.updated;
      }
      renderChat(chat);
    } catch (error) { messageError(error.message); }
  }
  async function streamChat(id, content) {
    // Only the server owns the OpenClaw bearer and the upstream Gateway stream.
    const response = await fetch("/api/chat/send-stream", {
      method: "POST",
      headers: {"Content-Type": "application/json", "Accept": "text/event-stream"},
      body: JSON.stringify({id, message: content}),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "Streaming local refusé");
    }
    if (!response.body) throw new Error("Flux SSE indisponible");

    const feed = $("chat-messages");
    let answerNode = null;
    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let buffer = "";
    let complete = false;
    try {
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
        if (buffer.length > 256000) throw new Error("Réponse SSE démesurée");
        let separator;
        while ((separator = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, separator);
          buffer = buffer.slice(separator + 2);
          if (!frame.startsWith("data: ")) throw new Error("Trame SSE invalide");
          const item = JSON.parse(frame.slice(6));
          if (item.type === "delta" && typeof item.text === "string") {
            if (!answerNode) {
              const user = document.createElement("article");
              user.className = "chat-message user";
              const userLabel = document.createElement("strong");
              userLabel.textContent = "Vous";
              const userText = document.createElement("p");
              userText.textContent = content;
              user.append(userLabel, userText);
              feed.append(user);
              const assistant = document.createElement("article");
              assistant.className = "chat-message assistant";
              const name = document.createElement("strong");
              name.textContent = "OpenClaw";
              answerNode = document.createElement("p");
              assistant.append(name, answerNode);
              feed.append(assistant);
            }
            answerNode.textContent += item.text;
            feed.scrollTop = feed.scrollHeight;
          } else if (item.type === "complete" && item.id === id) {
            complete = true;
          } else if (item.type === "error") {
            throw new Error(item.message || "Génération interrompue");
          } else {
            throw new Error("Événement SSE inconnu");
          }
        }
        if (done) break;
      }
      if (!complete || buffer.trim()) {
        throw new Error("Flux terminé sans confirmation de la réponse");
      }
      // The persisted server transcript, not the temporary preview, is authoritative.
      return await api("/api/chat?id=" + encodeURIComponent(id));
    } finally {
      await reader.cancel().catch(() => {});
    }
  }

  async function load() {
    try {
      const [status, threads, stream] = await Promise.all([
        api("/api/status"), api("/api/chats"),
        api("/api/chat/stream-capability").catch(() => ({enabled: false})),
      ]);
      streamingEnabled = stream.enabled === true;
      expandedStreaming = stream.scope === "local_seven_roles_and_projects";
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
  $("recover-confirm").addEventListener("change", () => {
    $("recover-submit").disabled = busy || !$("recover-confirm").checked;
  });
  $("chat-recovery").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !selectedChat?.pending || !$("recover-confirm").checked) return;
    busy = true;
    $("recover-submit").disabled = true;
    $("recover-confirm").disabled = true;
    try {
      const updated = await api("/api/chat/recover", {
        id: selectedChat.id, pending: selectedChat.pending, human_approved: true,
      });
      const entry = list.find(item => item.id === updated.id);
      if (entry) {
        entry.pending = false;
        entry.updated = updated.updated;
      }
      // Never restore the uncertain request in the input or send it again.
      $("chat-input").value = "";
      busy = false;
      renderChat(updated);
      messageError("Tour archivé comme incertain. Vous pouvez poser une nouvelle question.");
      $("chat-input").focus();
    } catch (error) {
      busy = false;
      await openChat(selected);
      messageError(error.message + " Vérifiez de nouveau l'état du fil.");
    }
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
      const useStream = streamingEnabled && selectedChat
        && (expandedStreaming ||
          (selectedChat.agent === "chef-operations" && selectedChat.project === null))
        && !/^[!/]/.test(content.trim())
        && !/^approuver\s/i.test(content.trim());
      const updated = useStream
        ? await streamChat(selected, content)
        : await api("/api/chat/send", {id: selected, message: content});
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
