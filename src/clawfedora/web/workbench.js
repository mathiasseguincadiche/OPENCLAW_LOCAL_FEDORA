"use strict";

/* Shared local UI shell. Presentation only: no API calls, secret storage or
 * mutations of approval forms. All safety-critical actions stay in page scripts. */
(() => {
  const main = document.querySelector("body > main");
  if (!main) return;
  // Keyboard users can bypass the navigation before reaching any forms.
  if (!main.id) main.id = "main-content";
  main.tabIndex = -1;
  const skip = document.createElement("a");
  skip.href = "#" + main.id;
  skip.className = "workspace-skip";
  skip.textContent = "Aller au contenu principal";
  document.body.insertBefore(skip, main);

  const view = location.pathname === "/github.html" ? "github" :
    location.pathname === "/notion.html" ? "notion" : "projects";
  const names = {
    projects: "Vue d’ensemble", github: "GitHub", notion: "Notion",
  };
  document.body.classList.add("workbench", "workbench--" + view);

  const create = (tag, cls, value) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (value !== undefined) node.textContent = value;
    return node;
  };
  const icons = {
    grid: ["M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h7v7h-7z"],
    git: ["M7 3v11a5 5 0 0 0 5 5h5", "M7 7a3 3 0 1 0 0-6a3 3 0 0 0 0 6",
      "M17 22a3 3 0 1 0 0-6a3 3 0 0 0 0 6"],
    book: ["M12 7v14", "M3 18V4c3-1 6-1 9 1v14c-3-2-6-2-9-1z",
      "M21 18V4c-3-1-6-1-9 1v14c3-2 6-2 9-1z"],
    shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
      "m9 12 2 2 4-4"],
    moon: ["M20.9 13a9 9 0 0 1-9.9-9.9A9 9 0 1 0 20.9 13z"],
    sun: ["M12 3v2", "M12 19v2", "M3 12h2", "M19 12h2",
      "M5.6 5.6 7 7", "m17 17 1.4 1.4", "M5.6 18.4 7 17",
      "m17 7 1.4-1.4", "M12 16a4 4 0 1 0 0-8a4 4 0 0 0 0 8"],
    arrow: ["M7 17 17 7", "M8 7h9v9"],
  };
  const icon = (name) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    element.setAttribute("viewBox", "0 0 24 24");
    element.setAttribute("aria-hidden", "true");
    element.setAttribute("fill", "none");
    element.setAttribute("stroke", "currentColor");
    element.setAttribute("stroke-width", "1.8");
    element.setAttribute("stroke-linecap", "round");
    element.setAttribute("stroke-linejoin", "round");
    for (const d of icons[name]) {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      element.append(path);
    }
    return element;
  };

  const rail = create("aside", "workspace-rail");
  rail.setAttribute("aria-label", "Navigation principale");
  const brand = create("a", "workspace-brand");
  brand.href = "/";
  const logo = create("span", "workspace-logo", "◈");
  logo.setAttribute("aria-hidden", "true");
  brand.append(logo);
  const brandText = create("span", "workspace-brand-copy");
  brandText.append(
    create("strong", "", "OpenClaw"),
    create("small", "", "INFRAOPS STUDIO"),
  );
  brand.append(brandText);
  rail.append(brand);

  const railNav = create("nav", "workspace-rail-nav");
  railNav.setAttribute("aria-label", "Espaces de l’atelier");
  railNav.append(create("p", "rail-caption", "ESPACES DE TRAVAIL"));
  for (const item of [
    {key: "projects", label: "Tableau de bord", href: "/", symbol: "grid"},
    {key: "github", label: "Dépôts & CI", href: "/github.html", symbol: "git"},
    {key: "notion", label: "Documentation", href: "/notion.html", symbol: "book"},
  ]) {
    const link = create("a", "workspace-rail-link");
    link.href = item.href;
    // On mobile the visual labels are hidden; keep explicit accessible names.
    link.setAttribute("aria-label", item.label);
    link.title = item.label;
    if (item.key === view) {
      link.classList.add("is-active");
      link.setAttribute("aria-current", "page");
    }
    link.append(icon(item.symbol), create("span", "rail-link-label", item.label));
    railNav.append(link);
  }
  rail.append(railNav);

  const railNote = create("div", "rail-note");
  railNote.append(icon("shield"));
  const note = create("div");
  note.append(
    create("strong", "", "Atelier local"),
    create("span", "", "Actions sensibles sous validation"),
  );
  railNote.append(note);
  rail.append(railNote);
  document.body.insertBefore(rail, main);

  const top = create("div", "workspace-topbar");
  const breadcrumb = create("div", "workspace-breadcrumb");
  breadcrumb.append(create("span", "", "Espace de travail"));
  breadcrumb.append(create("span", "breadcrumb-divider", "/"));
  breadcrumb.append(create("strong", "", names[view]));
  top.append(breadcrumb);

  const controls = create("div", "workspace-top-actions");
  const local = create("span", "workspace-local", "Sur cet appareil");
  controls.append(local);
  const themeButton = create("button", "theme-toggle");
  themeButton.type = "button";
  let preference = "light";
  try {
    const saved = localStorage.getItem("openclaw-workbench-theme");
    if (saved === "light" || saved === "dark") preference = saved;
    else if (window.matchMedia("(prefers-color-scheme: dark)").matches) preference = "dark";
  } catch (_error) {
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) preference = "dark";
  }
  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeButton.replaceChildren(icon(theme === "dark" ? "sun" : "moon"));
    const label = theme === "dark" ? "Mode clair" : "Mode sombre";
    themeButton.append(create("span", "", label));
    themeButton.setAttribute("aria-label", "Activer le " + label.toLowerCase());
    themeButton.setAttribute("aria-pressed", String(theme === "dark"));
    preference = theme;
  }
  setTheme(preference);
  themeButton.addEventListener("click", () => {
    setTheme(preference === "dark" ? "light" : "dark");
    try {
      localStorage.setItem("openclaw-workbench-theme", preference);
    } catch (_error) {
      /* No persistence is necessary for using the panel. */
    }
  });
  controls.append(themeButton);
  top.append(controls);
  main.prepend(top);

  const hero = main.querySelector(":scope > header");
  if (hero) hero.classList.add("workspace-hero");

  /* Group direct label/control pairs without changing IDs, names, types or
   * form ownership. The existing page controllers continue to own all data. */
  for (const form of main.querySelectorAll("form")) {
    for (const label of [...form.children]) {
      if (label.tagName !== "LABEL" || !label.htmlFor) continue;
      const field = label.nextElementSibling;
      if (!field || !["INPUT", "SELECT", "TEXTAREA"].includes(field.tagName)) continue;
      if (field.parentElement !== form) continue;
      const group = create("div", "field-group");
      if (field.tagName === "TEXTAREA" || field.type === "file") {
        group.classList.add("field-group--wide");
      }
      form.insertBefore(group, label);
      group.append(label, field);
    }
    if ([
      "create-form", "repo-plan-form", "policy-plan-form", "draft-plan-form",
    ].includes(form.id)) form.classList.add("workbench-form-grid");
  }

  const setups = {
    github: [
      ["create", "Créer un dépôt", "01"],
      ["governance", "Protections", "02"],
      ["propose", "Proposer une PR", "03"],
      ["visual", "Recette graphique", "04"],
    ],
    notion: [
      ["inspect", "Examiner", "01"],
      ["changes", "Modifier", "02"],
      ["approve", "Approuver", "03"],
      ["rich", "Texte enrichi", "04"],
      ["media", "Images & tableaux", "05"],
      ["verify", "Réception", "06"],
    ],
  };
  const definitions = setups[view];
  if (definitions) {
    const panels = definitions.map(([id]) => document.getElementById(id));
    if (panels.every(Boolean)) {
      const tabBar = create("div", "workspace-tabs");
      tabBar.setAttribute("role", "tablist");
      tabBar.setAttribute("aria-label", "Étapes de l’espace " + names[view]);
      const tabs = new Map();
      const stepNavigation = create("div", "workspace-step-navigation");
      stepNavigation.setAttribute("role", "group");
      stepNavigation.setAttribute("aria-label", "Changer d’étape");
      const previous = create("button", "workspace-step-action", "Précédent");
      const stepCount = create("span", "workspace-step-count");
      const next = create("button", "workspace-step-action", "Suivant");
      previous.type = "button";
      next.type = "button";
      stepCount.setAttribute("aria-live", "polite");
      stepNavigation.append(previous, stepCount, next);
      let active = "";
      function activate(id, focus = false) {
        if (!tabs.has(id)) return;
        active = id;
        const current = [...tabs.keys()].indexOf(id);
        for (const [key, button] of tabs) {
          const selected = key === id;
          document.getElementById(key).hidden = !selected;
          button.setAttribute("aria-selected", String(selected));
          button.tabIndex = selected ? 0 : -1;
          button.classList.toggle("is-selected", selected);
        }
        stepCount.textContent = "Étape " + (current + 1) + " sur " + tabs.size;
        previous.disabled = current === 0;
        next.disabled = current === tabs.size - 1;
        const button = tabs.get(id);
        const barRect = tabBar.getBoundingClientRect();
        const tabRect = button.getBoundingClientRect();
        if (tabRect.left < barRect.left + 8) {
          tabBar.scrollLeft += tabRect.left - barRect.left - 8;
        } else if (tabRect.right > barRect.right - 8) {
          tabBar.scrollLeft += tabRect.right - barRect.right + 8;
        }
        if (focus) button.focus();
      }
      function go(relative) {
        const keys = [...tabs.keys()];
        const position = keys.indexOf(active) + relative;
        if (position < 0 || position >= keys.length) return;
        activate(keys[position]);
        history.replaceState(null, "", "#" + keys[position]);
      }
      previous.addEventListener("click", () => go(-1));
      next.addEventListener("click", () => go(1));
      definitions.forEach(([id, label, number]) => {
        const section = document.getElementById(id);
        const tab = create("button", "workspace-tab");
        tab.type = "button";
        tab.id = "workspace-tab-" + id;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-controls", id);
        tab.append(create("span", "tab-number", number), create("span", "", label));
        section.setAttribute("role", "tabpanel");
        section.setAttribute("aria-labelledby", tab.id);
        section.tabIndex = -1;
        tab.addEventListener("click", () => {
          activate(id, true);
          history.replaceState(null, "", "#" + id);
        });
        tab.addEventListener("keydown", (event) => {
          const keys = [...tabs.keys()];
          const index = keys.indexOf(active);
          let next = index;
          if (event.key === "ArrowRight") next = (index + 1) % keys.length;
          else if (event.key === "ArrowLeft") next = (index - 1 + keys.length) % keys.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = keys.length - 1;
          else return;
          event.preventDefault();
          const target = keys[next];
          activate(target, true);
          history.replaceState(null, "", "#" + target);
        });
        tabs.set(id, tab);
        tabBar.append(tab);
      });
      panels[0].before(tabBar);
      tabBar.after(stepNavigation);
      const hashed = location.hash.slice(1);
      activate(tabs.has(hashed) ? hashed : definitions[0][0]);
      window.addEventListener("hashchange", () => {
        const hash = location.hash.slice(1);
        if (tabs.has(hash)) activate(hash);
      });
      // When a Notion preview is valid, show a small review-ready indicator;
      // this never triggers approval or auto-submits a form.
      if (view === "notion") {
        const approval = document.getElementById("apply-form");
        if (approval) {
          const update = () => {
            const tab = tabs.get("approve");
            tab.classList.toggle("is-ready", !approval.hidden);
            tab.title = approval.hidden ? "" : "Un plan attend votre revue et approbation";
          };
          new MutationObserver(update).observe(approval, {
            attributes: true, attributeFilter: ["hidden"],
          });
          update();
        }
      }
    }
  }
})();
