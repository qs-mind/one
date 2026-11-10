import { readFileSync } from "node:fs";
import { join } from "node:path";
import openapiTS from "openapi-typescript";
import { expect, it } from "vitest";

// `npm run contract` writes openapi.json from the core's models and contract.ts from openapi.json. When the contract
// changes and the script is not run, this fails. (core/tests/contract/test_phase1_contract.py keeps openapi.json equal
// to what the core declares.)
it("contract.ts is what openapi-typescript makes of openapi.json", async () => {
  const document = JSON.parse(readFileSync(join(__dirname, "openapi.json"), "utf8"));
  const written = readFileSync(join(__dirname, "contract.ts"), "utf8");
  expect(await openapiTS(document), "contract.ts is stale: run `npm run contract`").toBe(written);
});
