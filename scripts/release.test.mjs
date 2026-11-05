import { createHash, generateKeyPairSync, randomBytes, sign } from "node:crypto";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, test } from "vitest";
import { ASSETS, notesFile, notesOf, preflight, publicKey, release, root, verifySignature } from "./release.mjs";

const made = [];
afterEach(() => made.splice(0).forEach((dir) => rmSync(dir, { recursive: true, force: true })));
const scratch = () => {
  const dir = mkdtempSync(path.join(tmpdir(), "qsone-release-"));
  made.push(dir);
  return dir;
};
const b64 = (bytes) => Buffer.from(bytes).toString("base64");

/** A throwaway key pair made in the test, in Tauri's formats; nothing is kept. */
function keyPair() {
  const { publicKey: pub, privateKey } = generateKeyPairSync("ed25519");
  const raw = pub.export({ format: "der", type: "spki" }).subarray(12);
  const id = randomBytes(8);
  const configured = b64(`untrusted comment: minisign public key: TEST\n${b64(Buffer.concat([Buffer.from("Ed"), id, raw]))}\n`);
  /** What `tauri signer sign --app-version <version> <file>` writes into <file>.sig. */
  const signFile = (file, version) => {
    const signature = sign(null, createHash("blake2b512").update(readFileSync(file)).digest(), privateKey);
    const trusted = `timestamp:1793850000\tfile:${path.basename(file)}\tversion:${version}`;
    const global = sign(null, Buffer.concat([signature, Buffer.from(trusted)]), privateKey);
    const text = [
      "untrusted comment: signature from tauri secret key",
      b64(Buffer.concat([Buffer.from("ED"), id, signature])),
      `trusted comment: ${trusted}`,
      b64(global),
    ].join("\n");
    writeFileSync(file + ".sig", b64(text + "\n"));
  };
  return { configured, signFile };
}

const NOTES = "# 0.1.1\n\n<!-- en -->\nFixes for the import.\n\n<!-- ar -->\nإصلاحات في الاستيراد.\n";

// What the four build jobs upload, as the signing job downloads them (one folder per job).
const BUILT = {
  "bundle-x86_64-pc-windows-msvc/nsis/QS Mind ONE_{v}_x64-setup.exe": "windows installer",
  "bundle-x86_64-unknown-linux-gnu/appimage/QS Mind ONE_{v}_amd64.AppImage": "linux appimage",
  "bundle-aarch64-apple-darwin/QS Mind ONE_{v}_aarch64.app.tar.gz": "mac arm app",
  "bundle-aarch64-apple-darwin/dmg/QS Mind ONE_{v}_aarch64.dmg": "mac arm dmg",
  "bundle-x86_64-apple-darwin/QS Mind ONE_{v}_x64.app.tar.gz": "mac intel app",
  "bundle-x86_64-apple-darwin/dmg/QS Mind ONE_{v}_x64.dmg": "mac intel dmg",
};
const UPDATES = Object.keys(BUILT).filter((name) => !name.endsWith(".dmg"));

function built(version = "0.1.1", keys = keyPair(), signed = version) {
  const bundle = scratch();
  for (const [name, bytes] of Object.entries(BUILT)) {
    const file = path.join(bundle, name.replace("{v}", version));
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, bytes);
    if (UPDATES.includes(name) && signed) keys.signFile(file, signed);
  }
  const file = (name) => path.join(bundle, name.replace("{v}", version));
  return { bundle, keys, file, run: (more = {}) => release({ bundle, version, notes: NOTES, key: keys.configured, ...more }) };
}

describe("signatures", () => {
  // Made by the real `tauri signer sign --app-version 2.0.0` over the bytes `test`, with a throwaway key: the
  // vectors tauri-plugin-updater 2.14.1 tests itself with (src/updater.rs, offline_tests).
  const TAURI_KEY = b64(
    "untrusted comment: minisign public key: A49EF4746FA6E6D7\nRWTX5qZvdPSepDGWg2bz8n6ArQnBMwgQK1geVosorcbLzcunD+KJ+cYe",
  );
  const TAURI_SIGNATURE =
    "untrusted comment: signature from tauri secret key\nRUTX5qZvdPSepPF2zsjvP/L/TQtBLRnWRvaq+4omK1UEugtQp/USrGiI1v762sDy3id3aor7bRC9ETyeot6lMHHrWoZ5hjUM1Qc=\ntrusted comment: timestamp:1791649051\tfile:payload\tversion:2.0.0\nDDq2CLOEl5cQmC2eJRHlnZPVViOZsu1CjpPKQoei4A/XBfkDqGO0B+QMrcrHgEQ5qV3mne75tdFWhJpqUXh9AA==";

  test("a signature from the Tauri CLI checks out, and only for its bytes, comment and version", async () => {
    const file = path.join(scratch(), "payload");
    writeFileSync(file, "test");
    await verifySignature(file, b64(TAURI_SIGNATURE), TAURI_KEY, "2.0.0");
    await expect(verifySignature(file, b64(TAURI_SIGNATURE), TAURI_KEY, "2.0.1")).rejects.toThrow(
      /signed for version 2\.0\.0, not 2\.0\.1/,
    );
    const changed = b64(TAURI_SIGNATURE.replace("file:payload", "file:other"));
    await expect(verifySignature(file, changed, TAURI_KEY, "2.0.0")).rejects.toThrow(/changed comment/);
    writeFileSync(file, "tesT");
    await expect(verifySignature(file, b64(TAURI_SIGNATURE), TAURI_KEY, "2.0.0")).rejects.toThrow(/does not match/);
  });
});

describe("release.mjs", () => {
  test("latest.json needs all four signed files, signed for this version", async () => {
    const good = built();
    const { latest } = await good.run();
    expect(Object.keys(latest.platforms).sort()).toEqual(["darwin-aarch64", "darwin-x86_64", "linux-x86_64", "windows-x86_64"]);
    expect(latest.version).toBe("0.1.1");
    expect(latest.pub_date).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
    expect(latest.platforms["windows-x86_64"].url).toBe(
      "https://github.com/qs-mind/one/releases/download/v0.1.1/QS-Mind-ONE_x64-setup.exe",
    );
    expect(latest.platforms["darwin-x86_64"].signature).toBe(
      readFileSync(good.file(UPDATES[3]) + ".sig", "utf8").trim(),
    );

    const partial = built();
    rmSync(partial.file(UPDATES[1]) + ".sig");
    await expect(partial.run()).rejects.toThrow(/Not signed yet.*_amd64\.AppImage/);

    const old = built("0.1.1", keyPair(), "0.0.9");
    await expect(old.run()).rejects.toThrow(/signed for version 0\.0\.9, not 0\.1\.1/);

    const other = built();
    keyPair().signFile(other.file(UPDATES[2]), "0.1.1"); // a key the app does not have
    await expect(other.run()).rejects.toThrow(/aarch64\.app\.tar\.gz was signed by another key/);

    const tampered = built();
    writeFileSync(tampered.file(UPDATES[1]), "linux appimagE");
    await expect(tampered.run()).rejects.toThrow(/AppImage does not match its signature/);
    expect(readdirSync(tampered.bundle)).not.toContain("upload"); // nothing is written

    const missing = built();
    rmSync(missing.file("bundle-x86_64-apple-darwin/dmg/QS Mind ONE_{v}_x64.dmg"));
    await expect(missing.run()).rejects.toThrow(/QS-Mind-ONE_x64\.dmg: no build file/);
  });

  test("a build of another version is refused", async () => {
    const good = built();
    const wrong = path.join(good.bundle, "bundle-x86_64-pc-windows-msvc/nsis");
    rmSync(wrong, { recursive: true });
    mkdirSync(wrong);
    writeFileSync(path.join(wrong, "QS Mind ONE_0.1.0_x64-setup.exe"), "old");
    await expect(good.run()).rejects.toThrow(/QS Mind ONE_0\.1\.0_x64-setup\.exe was built for another version/);
  });

  test("assets get versionless names and checksums match the bytes", async () => {
    const good = built();
    const { out, assets } = await good.run();
    expect(assets).toEqual(ASSETS.map((a) => a.name));
    expect(readdirSync(out).sort()).toEqual([...assets, "SHA256SUMS.txt", "latest.json"].sort());
    const sums = readFileSync(path.join(out, "SHA256SUMS.txt"), "utf8").trim().split("\n");
    expect(sums).toHaveLength(6);
    for (const line of sums) {
      const [hex, name] = line.split("  ");
      expect(createHash("sha256").update(readFileSync(path.join(out, name))).digest("hex")).toBe(hex);
    }
    expect(readFileSync(path.join(out, "QS-Mind-ONE_aarch64.dmg"), "utf8")).toBe("mac arm dmg");
    await good.run(); // a second run starts the upload folder afresh and never reads it as a build
    expect(readdirSync(out)).toHaveLength(8);
  });

  test("notes keep both language sections", async () => {
    const { latest } = await built().run();
    expect(latest.notes).toContain("<!-- en -->\nFixes for the import.");
    expect(latest.notes).toContain("<!-- ar -->\nإصلاحات في الاستيراد.");
    expect(() => notesOf("<!-- en -->\nFixes\n")).toThrow(/no <!-- ar --> section/);
    expect(() => notesOf("<!-- ar -->\nإصلاحات\n<!-- en -->\n")).toThrow(/<!-- en --> section is empty/);
    await expect(built().run({ notes: "Fixes" })).rejects.toThrow(/no <!-- en --> section/);
    // this repository's own notes for its version
    const version = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8")).version;
    expect(notesOf(readFileSync(notesFile(version), "utf8"))).toMatch(/<!-- ar -->/);
  });

  test("without the founder's public key, a release stops at the start and says why", () => {
    const base = scratch();
    mkdirSync(path.join(base, "desktop"));
    const config = (key) =>
      writeFileSync(path.join(base, "desktop/tauri.release.conf.json"), JSON.stringify({ plugins: { updater: { pubkey: key } } }));
    config("");
    expect(() => publicKey(base)).toThrow(/public key is not in desktop\/tauri\.release\.conf\.json.*O3/);
    config("bm90IGEga2V5");
    expect(() => publicKey(base)).toThrow(/Not a minisign public key/);
    const { configured } = keyPair();
    config(configured);
    expect(publicKey(base)).toBe(configured);
    expect(() => preflight("0.1.0; echo", base)).toThrow(/Not a version/);
  });
});
