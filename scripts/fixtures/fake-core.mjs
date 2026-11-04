// Stands in for `python -m qsone` in scripts/core-dev.test.ts: same arguments, same secret check, and one child
// process of its own, so the test can see that stopping the dev server stops the whole tree.
import { spawn } from "node:child_process";
import { createServer } from "node:http";

const args = process.argv.slice(2);
const port = Number(args[args.indexOf("--port") + 1]);
const secret = process.env.QSONE_SECRET;
if (!secret || !port) process.exit(2);

if (args.includes("--fail")) {
  console.log("fake core: failing on purpose");
  process.exit(1);
}

const grandchild = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
console.log(`pids ${process.pid} ${grandchild.pid}`);

createServer((req, res) => {
  const ok = req.headers.authorization === `Bearer ${secret}`;
  res.writeHead(ok ? 200 : 401, { "content-type": "application/json" });
  res.end(JSON.stringify(ok ? { ok: true, path: req.url } : { detail: "unauthorised" }));
}).listen(port, "127.0.0.1");
