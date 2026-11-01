import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const storeModulePath = process.env.QMD_STORE_MODULE
  ?? "/home/agents/.bun/install/global/node_modules/@tobilu/qmd/dist/store.js";
const qmd = await import(pathToFileURL(resolve(storeModulePath)).href);
const require = createRequire(pathToFileURL(resolve(storeModulePath)));
const Database = require("better-sqlite3");
const refreshScript = resolve("scripts/qmd-refresh-workspace.mjs");
const refreshWrapper = resolve("scripts/qmd-refresh-workspace.sh");

function gitInit(path) {
  execFileSync("git", ["-c", "init.defaultBranch=main", "init", "-q", path]);
}

function snapshot(dbPath) {
  const db = new Database(dbPath, { readonly: true, fileMustExist: true });
  try {
    return {
      collections: db.prepare("SELECT * FROM store_collections ORDER BY name").all(),
      documents: db.prepare("SELECT * FROM documents ORDER BY collection, path").all(),
      content: db.prepare("SELECT hash, doc, created_at FROM content ORDER BY hash").all(),
      vectors: db.prepare("SELECT * FROM content_vectors ORDER BY hash, seq").all(),
    };
  } finally {
    db.close();
  }
}

const root = mkdtempSync(join(tmpdir(), "qmd-refresh-e2e-"));
try {
  const dbPath = join(root, "index.sqlite");
  const repo = join(root, "repo");
  const archive = join(root, "archive");
  const unclassified = join(root, "unclassified");
  const memory = join(root, "agent-memory");
  const privateDir = join(root, "private");
  const badApi = join(root, "bad-api.mjs");
  mkdirSync(repo);
  mkdirSync(archive);
  mkdirSync(unclassified);
  mkdirSync(memory);
  mkdirSync(privateDir);
  gitInit(repo);
  gitInit(archive);
  gitInit(unclassified);
  writeFileSync(join(repo, "updated.md"), "# New version\ncurrent body\n");
  writeFileSync(join(repo, "added.md"), "# Added\nnew document\n");
  writeFileSync(join(privateDir, "private.md"), "# Outside\nmust not be indexed\n");
  writeFileSync(badApi, "export const incompatible = true;\n");

  const store = qmd.createStore(dbPath);
  const db = store.db;
  const putCollection = db.prepare(`
    INSERT INTO store_collections
      (name, path, pattern, ignore_patterns, include_by_default, context)
    VALUES (?, ?, ?, ?, ?, ?)
  `);
  putCollection.run("repo-fixture", repo, "**/*.md", "[]", 1, JSON.stringify({ keep: "repo context" }));
  putCollection.run("archive-fixture", archive, "**/*.md", "[]", 0, JSON.stringify({ keep: "archive context" }));
  putCollection.run("unclassified-fixture", unclassified, "**/*.md", "[]", null, JSON.stringify({ keep: "unclassified context" }));
  putCollection.run("agent-codex-private", memory, "**/*.md", "[]", 1, JSON.stringify({ keep: "memory context" }));

  const now = "2026-10-24T00:00:00.000Z";
  const putContent = db.prepare("INSERT INTO content (hash, doc, created_at) VALUES (?, ?, ?)");
  const putDocument = db.prepare(`
    INSERT INTO documents (collection, path, title, hash, created_at, modified_at, active)
    VALUES (?, ?, ?, ?, ?, ?, 1)
  `);
  putContent.run("old-updated-hash", "# Old version\nold body\n", now);
  putDocument.run("repo-fixture", "updated.md", "Old version", "old-updated-hash", now, now);
  db.prepare(`
    INSERT INTO content_vectors (hash, seq, pos, model, embed_fingerprint, total_chunks, embedded_at)
    VALUES (?, 0, 0, ?, ?, 1, ?)
  `).run("old-updated-hash", "fixture-model", "fixture-fingerprint", now);
  putContent.run("deleted-history-hash", "# Removed file\nhistorical body\n", now);
  putDocument.run("repo-fixture", "deleted.md", "Removed file", "deleted-history-hash", now, now);
  putContent.run("archive-hash", "# Archive\narchive body\n", now);
  putDocument.run("archive-fixture", "archive.md", "Archive", "archive-hash", now, now);
  putContent.run("unclassified-hash", "# Unclassified\nkeep unchanged\n", now);
  putDocument.run("unclassified-fixture", "unclassified.md", "Unclassified", "unclassified-hash", now, now);
  putContent.run("private-memory-hash", "# Private memory\nkeep this\n", now);
  putDocument.run("agent-codex-private", "memory.md", "Private memory", "private-memory-hash", now, now);
  store.close();

  const before = snapshot(dbPath);
  const commonArgs = ["--db", dbPath, "--store-module", storeModulePath];

  const setPattern = (pattern) => {
    const updateStore = qmd.createStore(dbPath);
    updateStore.db.prepare("UPDATE store_collections SET pattern = ? WHERE name = 'repo-fixture'").run(pattern);
    updateStore.close();
  };
  const assertRejectedPattern = (pattern, expectedError) => {
    setPattern(pattern);
    const baseline = snapshot(dbPath);
    const rejected = spawnSync("node", [refreshScript, ...commonArgs, "--repo", repo], { encoding: "utf8" });
    assert.notEqual(rejected.status, 0, `unsafe pattern should fail: ${pattern}`);
    assert.match(rejected.stderr, expectedError);
    assert.deepEqual(snapshot(dbPath), baseline, `unsafe pattern must not write the DB: ${pattern}`);
  };
  assertRejectedPattern(join(privateDir, "*.md"), /Absolute glob rejected/);
  assertRejectedPattern("../private/*.md", /Parent traversal glob rejected/);
  assertRejectedPattern("**/{*.md,../private/*.md}", /Parent traversal glob rejected/);
  assertRejectedPattern("..\\private\\*.md", /Backslashes are not allowed/);
  setPattern("**/*.md");

  const symlinkPath = join(repo, "linked.md");
  symlinkSync(join(privateDir, "private.md"), symlinkPath);
  const dry = spawnSync("node", [refreshScript, ...commonArgs, "--dry-run", "--repo", repo], { encoding: "utf8" });
  assert.equal(dry.status, 0, dry.stderr);
  assert.match(dry.stdout, /DRY-RUN eligible collections: 1/);
  assert.deepEqual(snapshot(dbPath), before, "dry-run must not write to the database");

  const incompatible = spawnSync("node", [refreshScript, "--db", dbPath, "--store-module", badApi, "--repo", repo], { encoding: "utf8" });
  assert.notEqual(incompatible.status, 0, "incompatible SDK must fail visibly");
  assert.match(incompatible.stderr, /Unsupported QMD store API/);
  assert.deepEqual(snapshot(dbPath), before, "API failure must happen before database writes");

  const run = spawnSync("node", [
    refreshScript, ...commonArgs,
    "--repo", repo,
    "--repo", archive,
  ], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr);
  assert.match(run.stdout, /REFRESH .*repo-fixture/);
  assert.match(run.stdout, /not explicitly default-included/);

  const after = snapshot(dbPath);
  const collectionsBefore = new Map(before.collections.map((row) => [row.name, row]));
  const collectionsAfter = new Map(after.collections.map((row) => [row.name, row]));
  assert.deepEqual(collectionsAfter, collectionsBefore, "collection metadata must remain unchanged");
  const docsByKey = (rows) => new Map(rows.map((row) => [`${row.collection}/${row.path}`, row]));
  const beforeDocs = docsByKey(before.documents);
  const afterDocs = docsByKey(after.documents);
  assert.equal(afterDocs.get("repo-fixture/updated.md").active, 1);
  assert.notEqual(afterDocs.get("repo-fixture/updated.md").hash, "old-updated-hash");
  assert.equal(afterDocs.get("repo-fixture/deleted.md").active, 0, "deleted file is deactivated, not erased");
  assert.equal(afterDocs.get("repo-fixture/added.md").active, 1);
  assert.deepEqual(afterDocs.get("archive-fixture/archive.md"), beforeDocs.get("archive-fixture/archive.md"));
  assert.deepEqual(afterDocs.get("unclassified-fixture/unclassified.md"), beforeDocs.get("unclassified-fixture/unclassified.md"));
  assert.deepEqual(afterDocs.get("agent-codex-private/memory.md"), beforeDocs.get("agent-codex-private/memory.md"));
  const contentByHash = new Map(after.content.map((row) => [row.hash, row]));
  assert.equal(contentByHash.get("old-updated-hash").doc, "# Old version\nold body\n");
  assert.equal(contentByHash.get("deleted-history-hash").doc, "# Removed file\nhistorical body\n");
  assert.equal(contentByHash.get("private-memory-hash").doc, "# Private memory\nkeep this\n");
  assert.equal(after.vectors.length, 1, "fixture must exercise a real indexed vector row");
  assert.equal(after.vectors[0].hash, "old-updated-hash");
  assert.deepEqual(after.vectors, before.vectors, "refresh must not embed or change vectors");

  const symlinkRun = spawnSync("node", [refreshScript, ...commonArgs, "--repo", repo], { encoding: "utf8" });
  assert.equal(symlinkRun.status, 0, symlinkRun.stderr);
  const afterSymlink = snapshot(dbPath);
  assert.ok(!afterSymlink.documents.some((row) => row.collection === "repo-fixture" && row.path === "linked.md"));
  assert.ok(!afterSymlink.content.some((row) => row.doc.includes("must not be indexed")));
  unlinkSync(symlinkPath);

  const commonHome = join(root, "common-home");
  const commonCache = join(commonHome, ".cache", "qmd");
  mkdirSync(commonCache, { recursive: true });
  chmodSync(commonHome, 0o700);
  chmodSync(commonCache, 0o775);
  const wrapperEnv = {
    ...process.env,
    HOME: commonHome,
    QMD_INDEX_PATH: dbPath,
    QMD_STORE_MODULE: storeModulePath,
  };
  const wrapperDryRun = spawnSync("bash", [refreshWrapper, "--dry-run"], { encoding: "utf8", env: wrapperEnv });
  assert.equal(wrapperDryRun.status, 0, wrapperDryRun.stderr);
  assert.equal(statSync(commonCache).mode & 0o777, 0o775, "shared cache permissions must not be changed");
  const privateLockDir = join(commonHome, ".local", "state", "qmd-refresh");
  assert.equal(statSync(privateLockDir).mode & 0o777, 0o700, "new lock leaf must be private");

  const hostileHome = join(root, "hostile-home");
  const hostileLockDir = join(hostileHome, ".local", "state", "qmd-refresh");
  mkdirSync(hostileLockDir, { recursive: true, mode: 0o700 });
  chmodSync(hostileHome, 0o700);
  chmodSync(join(hostileHome, ".local"), 0o700);
  chmodSync(join(hostileHome, ".local", "state"), 0o700);
  chmodSync(hostileLockDir, 0o700);
  const sentinel = join(root, "lock-symlink-sentinel");
  writeFileSync(sentinel, "unchanged\n");
  symlinkSync(sentinel, join(hostileLockDir, "workspace-refresh.lock"));
  const hostileRun = spawnSync("bash", [refreshWrapper, "--dry-run"], {
    encoding: "utf8",
    env: { ...wrapperEnv, HOME: hostileHome },
  });
  assert.notEqual(hostileRun.status, 0);
  assert.match(hostileRun.stderr, /refusing symlink lock file/);
  assert.equal(readFileSync(sentinel, "utf8"), "unchanged\n", "symlink target must not be truncated");
  console.log("PASS qmd refresh E2E: dry-run read-only, compatible API, scoped collection, retained history, excluded archive, untouched memory, no embedding");
} finally {
  rmSync(root, { recursive: true, force: true });
}
