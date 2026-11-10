// The real-window walks' bridge (scripts/realapp): in a dev server started with VITE_QSONE_TEST_BRIDGE=1 only, the page
// opens a WebSocket to the walk's driver (VITE_QSONE_TEST_BRIDGE_URL, 127.0.0.1 with a one-run token) and tells it where
// things are on the screen and what they say. It never clicks, types or changes anything the engineer could: every
// input is the X server's (xdotool). main.tsx imports it behind import.meta.env, so a production build has none of it
// (scripts/realapp/bridge.test.mjs checks the built files).
import { language } from "./i18n";


/** What to find: by role and accessible name, by text, by test id or by CSS; `within` narrows, `nth` picks. */
export type Pattern = string | { re: string; flags?: string };
export interface Query {
  role?: string;
  name?: Pattern;
  exact?: boolean;
  text?: Pattern;
  testId?: string;
  css?: string;
  within?: Query;
  nth?: number;
  /** Hidden elements count too (for `visible`, which says whether the first match shows). */
  hidden?: boolean;
}

const norm = (s: string | null | undefined) => (s ?? "").replace(/\s+/g, " ").trim();

function matches(value: string, pattern: Pattern, exact = false): boolean {
  if (typeof pattern !== "string") return new RegExp(pattern.re, pattern.flags).test(value);
  return exact ? value === norm(pattern) : value.toLowerCase().includes(norm(pattern).toLowerCase());
}

const INPUT_ROLES: Record<string, string> = {
  button: "button",
  submit: "button",
  reset: "button",
  image: "button",
  checkbox: "checkbox",
  radio: "radio",
  range: "slider",
  number: "spinbutton",
  search: "searchbox",
};

/** The element's role: its own `role`, else the one its tag implies. */
export function roleOf(el: Element): string | undefined {
  const own = el.getAttribute("role")?.trim().split(/\s+/)[0];
  if (own) return own;
  const tag = el.tagName.toLowerCase();
  if (tag === "input") {
    const type = (el.getAttribute("type") ?? "text").toLowerCase();
    return type === "hidden" || type === "file" ? undefined : (INPUT_ROLES[type] ?? "textbox");
  }
  if (/^h[1-6]$/.test(tag)) return "heading";
  const implied: Record<string, string> = {
    button: "button",
    textarea: "textbox",
    select: (el as HTMLSelectElement).multiple ? "listbox" : "combobox",
    option: "option",
    dialog: "dialog",
    nav: "navigation",
    main: "main",
    ul: "list",
    ol: "list",
    li: "listitem",
    table: "table",
    tr: "row",
    td: "cell",
    th: "columnheader",
    img: "img",
    fieldset: "group",
    form: "form",
    progress: "progressbar",
  };
  if (tag === "a") return el.hasAttribute("href") ? "link" : undefined;
  if (tag === "section") return el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby") ? "region" : undefined;
  if ((el as HTMLElement).isContentEditable && el.getAttribute("contenteditable") !== null) return "textbox";
  return implied[tag];
}

const NAME_FROM_CONTENT = new Set(["button", "link", "heading", "menuitem", "menuitemradio", "menuitemcheckbox", "tab", "option", "cell", "columnheader", "rowheader", "radio", "checkbox", "switch", "treeitem", "tooltip", "listitem"]);

function textOf(el: Element): string {
  // the text a reader hears: aria-hidden parts left out
  let out = "";
  for (const node of Array.from(el.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) out += node.textContent ?? "";
    else if (node instanceof Element && node.getAttribute("aria-hidden") !== "true") {
      const label = node.getAttribute("aria-label");
      out += ` ${label ?? (node.tagName === "IMG" ? (node.getAttribute("alt") ?? "") : textOf(node))} `;
    }
  }
  return out;
}

/** A simplified accessible name: aria-labelledby, aria-label, a label, alt, the content (for roles that take it), title, placeholder. */
export function nameOf(el: Element): string {
  const by = el.getAttribute("aria-labelledby");
  if (by) return norm(by.split(/\s+/).map((id) => textOf(document.getElementById(id) ?? document.createElement("i"))).join(" "));
  const label = el.getAttribute("aria-label");
  if (label) return norm(label);
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) {
    const labels = Array.from(el.labels ?? []).map((l) => textOf(l));
    if (labels.length) return norm(labels.join(" "));
  }
  if (el instanceof HTMLImageElement) return norm(el.alt);
  const role = roleOf(el);
  if (role && NAME_FROM_CONTENT.has(role)) {
    const content = norm(textOf(el));
    if (content) return content;
  }
  return norm(el.getAttribute("title") ?? el.getAttribute("placeholder"));
}

/** Shown: laid out, not hidden by style, not under aria-hidden or inert. */
export function shown(el: Element): boolean {
  if (el.closest("[aria-hidden='true'], [inert], [hidden]")) return false;
  const style = getComputedStyle(el);
  if (style.visibility === "hidden" || style.display === "none") return false;
  const box = el.getBoundingClientRect();
  return box.width > 0 && box.height > 0;
}

/** Every element the query matches, in document order. */
export function findAll(query: Query, scope: ParentNode = document): Element[] {
  const scopes = query.within ? findAll(query.within, scope) : [scope];
  const found: Element[] = [];
  for (const root of scopes) {
    let candidates: Element[];
    if (query.css) candidates = Array.from(root.querySelectorAll(query.css));
    else if (query.testId) candidates = Array.from(root.querySelectorAll(`[data-testid="${CSS.escape(query.testId)}"]`));
    else candidates = Array.from(root.querySelectorAll("*"));
    if (query.role) candidates = candidates.filter((el) => roleOf(el) === query.role);
    if (query.name !== undefined) candidates = candidates.filter((el) => matches(nameOf(el), query.name!, query.exact));
    if (query.text !== undefined) {
      const text = query.text;
      const hit = (el: Element) => matches(norm(el.textContent), text, query.exact);
      // the innermost element that holds the text, not every ancestor of it
      candidates = candidates.filter((el) => hit(el) && !Array.from(el.children).some(hit));
    }
    if (!query.hidden) candidates = candidates.filter(shown);
    found.push(...candidates.filter((el) => !found.includes(el)));
  }
  return found;
}

export function find(query: Query): Element | undefined {
  return findAll(query)[query.nth ?? 0];
}

function describe(query: Query): string {
  return JSON.stringify(query);
}

/** The page's answers, by operation. Rectangles are CSS pixels in the viewport; `dpr` turns them into screen pixels. */
export function answer(op: string, query: Query | undefined): unknown {
  if (op === "state") {
    const doc = document.querySelector("[data-region='document']");
    return {
      url: `${location.pathname}${location.search}${location.hash}`,
      lang: document.documentElement.lang || language(),
      dir: document.documentElement.dir,
      document: doc?.getAttribute("aria-label") ?? null,
      zoom: parseFloat(getComputedStyle(document.documentElement).fontSize) / 16,
      rootFontSize: parseFloat(getComputedStyle(document.documentElement).fontSize),
      inner: { width: window.innerWidth, height: window.innerHeight },
      dpr: window.devicePixelRatio,
      focused: document.activeElement ? `${document.activeElement.tagName.toLowerCase()} ${nameOf(document.activeElement)}`.trim() : null,
      // animations that will end (a view transition, a panel sliding in); while one runs, a click may miss
      moving: document.getAnimations().filter((a) => a.playState === "running" && a.effect?.getComputedTiming().endTime !== Infinity).length,
      userAgent: navigator.userAgent,
    };
  }
  if (op === "fonts") {
    // the web fonts the page declared and whether the engine loaded them
    return Array.from(document.fonts)
      .filter((font) => font.status === "loaded")
      .map((font) => `${font.family.replace(/"/g, "")} ${font.weight}`);
  }
  if (!query) throw new Error(`${op} needs a query`);
  if (op === "count") return findAll(query).length;
  const el = find(query);
  if (op === "visible") return Boolean(el && (query.hidden ? shown(el) : true));
  if (!el) throw new Error(`nothing matches ${describe(query)}`);
  if (op === "rect") {
    const box = el.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height, dpr: window.devicePixelRatio, inner: { width: window.innerWidth, height: window.innerHeight } };
  }
  if (op === "text") {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return el.value;
    return (el as HTMLElement).innerText ?? el.textContent ?? "";
  }
  if (op === "hasFocus") return el === document.activeElement || el.contains(document.activeElement);
  if (op === "scrollIntoView") {
    el.scrollIntoView({ block: "center", inline: "center" });
    return true;
  }
  if (op === "style") {
    const style = getComputedStyle(el);
    return { fontFamily: style.fontFamily, fontSize: style.fontSize, fontWeight: style.fontWeight, lineHeight: style.lineHeight, direction: style.direction };
  }
  throw new Error(`unknown operation ${op}`);
}

/** Connects to the driver and answers it; reconnects when the socket closes (the driver may start after the page). */
export function install(url: string) {
  const connect = () => {
    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      setTimeout(connect, 500);
      return;
    }
    socket.onopen = () => socket.send(JSON.stringify({ hello: true, state: answer("state", undefined) }));
    socket.onmessage = (event) => {
      let id: unknown;
      try {
        const message = JSON.parse(String(event.data)) as { id: number; op: string; query?: Query };
        id = message.id;
        if (message.op === "frames") {
          // answered after two painted frames: what the screen shows has caught up with the page
          requestAnimationFrame(() => requestAnimationFrame(() => socket.send(JSON.stringify({ id, ok: true, value: true }))));
          return;
        }
        socket.send(JSON.stringify({ id, ok: true, value: answer(message.op, message.query) }));
      } catch (error) {
        socket.send(JSON.stringify({ id, ok: false, error: error instanceof Error ? error.message : String(error) }));
      }
    };
    socket.onclose = () => setTimeout(connect, 500);
  };
  connect();
}
