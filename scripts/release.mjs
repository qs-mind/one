// The release's files, from what the four build jobs made and the signing job signed (.github/workflows/release.yml).
//
//   node scripts/release.mjs check <version>
//       before anything builds: every version file says <version>, releases/<version>.md has an English and an
//       Arabic section, and the updater's public key is in desktop/tauri.release.conf.json.
//   node scripts/release.mjs <bundle folder> <version>
//       copies the six installers to names without the version (stable links), writes SHA256SUMS.txt, and, with
//       every update file signed for <version> by the key the app checks, writes latest.json; all into
//       <bundle folder>/upload/. A signature for another version, by another key, or a missing one stops it.
//
// The signatures are Tauri's (minisign, Ed25519): checked here with Node's own crypto, the way the app checks them,
// so a release can never carry an update the installed apps would refuse.
import { createHash, createPublicKey, verify as ed25519 } from "node:crypto";
import { copyFileSync, createReadStream, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { check as checkVersions, VERSION } from "./version.mjs";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const REPO = "qs-mind/one";
const OUT = "upload";

/** The six installers: what each build makes (with the version in its name), the asset it becomes, and, for the
 * four the updater installs, the updater's platform. */
export const ASSETS = [
  { name: "QS-Mind-One_x64-setup.exe", end: "_x64-setup.exe", platform: "windows-x86_64" },
  { name: "QS-Mind-One_amd64.AppImage", end: "_amd64.AppImage", platform: "linux-x86_64" },
  { name: "QS-Mind-One_aarch64.app.tar.gz", end: "_aarch64.app.tar.gz", platform: "darwin-aarch64" },
  { name: "QS-Mind-One_x64.app.tar.gz", end: "_x64.app.tar.gz", platform: "darwin-x86_64" },
  { name: "QS-Mind-One_aarch64.dmg", end: "_aarch64.dmg" },
  { name: "QS-Mind-One_x64.dmg", end: "_x64.dmg" },
];

// Release notes -------------------------------------------------------------------------------------------------

const SECTION = { en: "<!-- en -->", ar: "<!-- ar -->" };

/** The notes, checked: an English and an Arabic section, each with text (the app shows one or the other). */
export function notesOf(text) {
  const at = { en: text.indexOf(SECTION.en), ar: text.indexOf(SECTION.ar) };
  for (const lang of ["en", "ar"]) {
    if (at[lang] < 0) throw new Error(`The release notes have no ${SECTION[lang]} section.`);
    const start = at[lang] + SECTION[lang].length;
    const other = at[lang === "en" ? "ar" : "en"];
    const body = text.slice(start, other > start ? other : undefined).trim();
    if (!body) throw new Error(`The release notes' ${SECTION[lang]} section is empty.`);
  }
  return text.trim() + "\n";
}

export function notesFile(version, base = root) {
  return path.join(base, "releases", `${version}.md`);
}

// Signatures ----------------------------------------------------------------------------------------------------

const SPKI_ED25519 = Buffer.from("302a300506032b6570032100", "hex");

function unbase64(text, what) {
  const bytes = Buffer.from(String(text).trim(), "base64");
  if (!bytes.length) throw new Error(`${what} is not base64.`);
  return bytes;
}

/** Tauri's public key, as tauri.release.conf.json holds it: base64 of minisign's two-line public key file. */
export function parsePublicKey(configured) {
  const lines = unbase64(configured, "The public key").toString("utf8").trim().split("\n");
  const key = Buffer.from((lines[1] ?? "").trim(), "base64");
  if (key.length !== 42 || key.subarray(0, 2).toString() !== "Ed") throw new Error("Not a minisign public key.");
  return { keyId: key.subarray(2, 10), key: createPublicKey({ key: Buffer.concat([SPKI_ED25519, key.subarray(10)]), format: "der", type: "spki" }) };
}

/** A `.sig` file as `tauri signer sign` writes it: base64 of minisign's four-line signature file. */
export function parseSignature(text) {
  const lines = unbase64(text, "The signature").toString("utf8").trim().split("\n");
  const signature = unbase64(lines[1] ?? "", "The signature");
  const comment = lines[2] ?? "";
  if (signature.length !== 74 || !comment.startsWith("trusted comment: ")) throw new Error("Not a minisign signature.");
  return {
    algorithm: signature.subarray(0, 2).toString(), // "ED": the file's BLAKE2b-512 is signed; "Ed": the file itself
    keyId: signature.subarray(2, 10),
    signature: signature.subarray(10),
    trusted: comment.slice("trusted comment: ".length),
    global: unbase64(lines[3] ?? "", "The signature"),
  };
}

/** The version a signature was made for (`tauri signer sign --app-version`), from its trusted comment. */
export function signedVersion(trusted) {
  return trusted
    .split("\t")
    .find((field) => field.startsWith("version:"))
    ?.slice("version:".length);
}

async function blake2b(file) {
  const hash = createHash("blake2b512");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest();
}

/** Throws unless `signatureText` is a good signature of `file` by `publicKey`, made for `version`. */
export async function verifySignature(file, signatureText, publicKey, version) {
  const name = path.basename(file);
  const sig = parseSignature(signatureText);
  const pub = parsePublicKey(publicKey);
  if (!sig.keyId.equals(pub.keyId)) throw new Error(`${name} was signed by another key than the one the app checks.`);
  const signed = sig.algorithm === "ED" ? await blake2b(file) : readFileSync(file);
  if (!["ED", "Ed"].includes(sig.algorithm) || !ed25519(null, signed, pub.key, sig.signature)) {
    throw new Error(`${name} does not match its signature.`);
  }
  if (!ed25519(null, Buffer.concat([sig.signature, Buffer.from(sig.trusted)]), pub.key, sig.global)) {
    throw new Error(`${name}'s signature has a changed comment.`);
  }
  const made = signedVersion(sig.trusted);
  if (made !== version) {
    throw new Error(`${name} was signed for version ${made ?? "(none)"}, not ${version}.`);
  }
}

/** The updater's public key in desktop/tauri.release.conf.json, or a plain error while it is not there yet. */
export function publicKey(base = root) {
  const config = JSON.parse(readFileSync(path.join(base, "desktop", "tauri.release.conf.json"), "utf8"));
  const key = config.plugins?.updater?.pubkey?.trim();
  if (!key) {
    throw new Error(
      "The updater's public key is not in desktop/tauri.release.conf.json (plugins.updater.pubkey) yet. " +
        "The founder makes the key pair once (ops step O3), keeps the private key offline and in the GitHub " +
        "environment `release`, and the public key goes into that file. Without it no installed One could check an update.",
    );
  }
  parsePublicKey(key); // a key that is not one fails here, not on every engineer's computer
  return key;
}

// The release ----------------------------------------------------------------------------------------------------

function filesIn(dir) {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.join(entry.parentPath, entry.name))
    .filter((file) => !path.relative(dir, file).split(path.sep).includes(OUT));
}

async function sha256(file) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

/** Builds `<bundle>/upload/`: the six assets, SHA256SUMS.txt and latest.json. Returns what it wrote. */
export async function release({ bundle, version, notes, key, now = new Date() }) {
  if (!VERSION.test(version ?? "")) throw new Error(`Not a version: ${version}`);
  const text = notesOf(notes);
  const files = filesIn(bundle);
  const found = ASSETS.map((asset) => {
    const matches = files.filter((file) => path.basename(file).endsWith(asset.end) && !file.endsWith(".sig"));
    if (matches.length !== 1) {
      throw new Error(`${asset.name}: ${matches.length ? "more than one build file" : "no build file"} (…${asset.end}).`);
    }
    const [file] = matches;
    if (!path.basename(file).includes(`_${version}_`)) {
      throw new Error(`${path.basename(file)} was built for another version than ${version}.`);
    }
    return { ...asset, file };
  });

  const missing = found.filter((a) => a.platform && !files.includes(a.file + ".sig"));
  if (missing.length) {
    throw new Error(`Not signed yet, so no latest.json: ${missing.map((a) => path.basename(a.file)).join(", ")}.`);
  }
  const platforms = {};
  for (const asset of found.filter((a) => a.platform)) {
    const signature = readFileSync(asset.file + ".sig", "utf8").trim();
    await verifySignature(asset.file, signature, key, version);
    platforms[asset.platform] = {
      signature,
      url: `https://github.com/${REPO}/releases/download/v${version}/${asset.name}`,
    };
  }

  const out = path.join(bundle, OUT);
  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });
  const sums = [];
  for (const asset of found) {
    copyFileSync(asset.file, path.join(out, asset.name));
    sums.push(`${await sha256(path.join(out, asset.name))}  ${asset.name}`);
  }
  writeFileSync(path.join(out, "SHA256SUMS.txt"), sums.join("\n") + "\n");
  const latest = {
    version,
    notes: text,
    pub_date: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
    platforms,
  };
  writeFileSync(path.join(out, "latest.json"), JSON.stringify(latest, null, 2) + "\n");
  return { out, assets: found.map((a) => a.name), latest };
}

/** Before a release builds: versions, notes and the public key. */
export function preflight(version, base = root) {
  if (!VERSION.test(version ?? "")) throw new Error(`Not a version: ${version}`);
  checkVersions(version, base);
  let notes;
  try {
    notes = readFileSync(notesFile(version, base), "utf8");
  } catch {
    throw new Error(`There are no release notes at releases/${version}.md.`);
  }
  notesOf(notes);
  publicKey(base);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [first, version] = process.argv.slice(2);
  try {
    if (first === "check") {
      preflight(version);
      console.log(`Version ${version}: every file agrees, the notes have both languages, and the public key is set.`);
    } else if (first && version) {
      const notes = readFileSync(notesFile(version), "utf8");
      const done = await release({ bundle: first, version, notes, key: publicKey() });
      console.log(`Wrote ${done.assets.length} installers, SHA256SUMS.txt and latest.json to ${done.out}.`);
    } else {
      throw new Error("Use: node scripts/release.mjs check <version> | <bundle folder> <version>");
    }
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
}
