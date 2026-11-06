// A real-window walk driven one step at a time: `start` launches the ONE window (realapp.mjs) and keeps it open,
// listening on 127.0.0.1 for steps; `send` runs one step there (an async JS body with `app` and the helpers in scope)
// and prints what it returns. For walks whose next step depends on what the AI just said.
//
//   node scripts/realapp/drive.mjs start '<launch options as JSON>'      (stays in the foreground: run it in the background)
//   node scripts/realapp/drive.mjs send <run folder> 'return await app.state()'
//   node scripts/realapp/drive.mjs send <run folder> --file step.js
//   node scripts/realapp/drive.mjs send <run folder> 'await stop()'
//
// Helpers in a step: app, sleep(ms), snap(name) (a shot named exactly `<name>.png` in the shots folder), chat() (the
// chat's text), api(path) (the core's JSON through Vite), state (an object kept between steps), stop().
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { launch } from "./realapp.mjs";

const [, , command, ...rest] = process.argv;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

if (command === "start") {
  const opts = JSON.parse(rest[0] ?? "{}");
  const app = await launch(opts);
  const state = {};
  const helpers = {
    app,
    sleep,
    state,
    async snap(name, { screen = false } = {}) {
      await app.settle(150);
      const file = path.join(app.shotsDir, `${name}.png`);
      execFileSync("import", ["-window", screen ? "root" : app.window, file], { env: app.env, stdio: "ignore" });
      return file;
    },
    chat: () => app.text({ css: "[data-region='chat']" }),
    async api(p, init) {
      const r = await fetch(`http://127.0.0.1:${app.port}/api${p}`, init);
      const body = await r.text();
      try {
        return { status: r.status, body: JSON.parse(body) };
      } catch {
        return { status: r.status, body };
      }
    },
    stop: async () => {
      await app.stop();
      setTimeout(() => process.exit(0), 200);
      return "stopped";
    },
  };
  const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", async () => {
      let out;
      try {
        const fn = new AsyncFunction(...Object.keys(helpers), body);
        out = { ok: true, value: await fn(...Object.values(helpers)) };
      } catch (error) {
        out = { ok: false, error: String(error?.stack ?? error) };
      }
      res.end(JSON.stringify(out, null, 1));
    });
  });
  server.listen(0, "127.0.0.1", () => {
    writeFileSync(path.join(app.dir, "drive.port"), String(server.address().port));
    console.log(`drive: ready, run folder ${app.dir}, page port ${app.port}`);
  });
} else if (command === "send") {
  const [dir, ...code] = rest;
  const body = code[0] === "--file" ? readFileSync(code[1], "utf8") : code.join(" ");
  const port = readFileSync(path.join(dir, "drive.port"), "utf8").trim();
  const r = await fetch(`http://127.0.0.1:${port}/`, { method: "POST", body });
  const out = JSON.parse(await r.text());
  if (out.ok) console.log(typeof out.value === "string" ? out.value : JSON.stringify(out.value, null, 1));
  else {
    console.error(out.error);
    process.exit(1);
  }
} else {
  console.error("usage: drive.mjs start '<options>' | send <run folder> '<step>'");
  process.exit(2);
}
