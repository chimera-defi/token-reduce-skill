#!/usr/bin/env node
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep, win32 } from "node:path";
import { pathToFileURL } from "node:url";

function usage() {
  return "Usage: qmd-refresh-workspace.mjs --db PATH --store-module PATH [--dry-run] --repo PATH [--repo PATH ...]";
}

function parseArgs(argv) {
  const options = { dryRun: false, repos: [] };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--db" || arg === "--store-module" || arg === "--repo") {
      const value = argv[++i];
      if (!value || value.startsWith("--")) throw new Error(`${arg} requires a value`);
      if (arg === "--db") options.dbPath = value;
      else if (arg === "--store-module") options.storeModule = value;
      else options.repos.push(value);
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (options.help) return options;
  if (!options.dbPath || !options.storeModule || options.repos.length === 0) {
    throw new Error(usage());
  }
  return options;
}

function canonicalGitRoot(input) {
  if (!existsSync(input)) return { skip: "path missing" };
  let path;
  try {
    path = realpathSync(input);
  } catch {
    return { skip: "path cannot be resolved" };
  }
  const gitResult = spawnSync("git", ["-C", path, "rev-parse", "--show-toplevel"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  });
  if (gitResult.status !== 0) return { skip: "not a Git worktree" };
  const gitRoot = realpathSync(gitResult.stdout.trim());
  if (gitRoot !== path) return { skip: "path is not the Git worktree root" };
  const home = process.env.HOME && existsSync(process.env.HOME)
    ? realpathSync(process.env.HOME)
    : "";
  if (home && (path === home || path === resolve(home, "workspace"))) {
    return { skip: "aggregate home/workspace root" };
  }
  if (/(^|\/)pytest-of-[^/]+(?:\/|$)/.test(path)) return { skip: "pytest fixture root" };
  return { path };
}

function loadDatabaseConstructor(storeModulePath) {
  const require = createRequire(pathToFileURL(resolve(storeModulePath)));
  return require("better-sqlite3");
}

function expandBracePatterns(pattern, limit = 256) {
  const start = pattern.indexOf("{");
  if (start === -1) {
    if (pattern.includes("}")) throw new Error("unmatched closing brace");
    return [pattern];
  }
  let depth = 0;
  let end = -1;
  const separators = [];
  for (let i = start; i < pattern.length; i++) {
    if (pattern[i] === "{") depth++;
    else if (pattern[i] === "}") {
      depth--;
      if (depth === 0) {
        end = i;
        break;
      }
      if (depth < 0) throw new Error("unmatched closing brace");
    } else if (pattern[i] === "," && depth === 1) {
      separators.push(i);
    }
  }
  if (end === -1) throw new Error("unmatched opening brace");
  if (separators.length === 0) throw new Error("brace groups must contain alternatives");
  const bounds = [start, ...separators, end];
  const alternatives = [];
  for (let i = 0; i < bounds.length - 1; i++) {
    alternatives.push(pattern.slice(bounds[i] + 1, bounds[i + 1]));
  }
  const prefix = pattern.slice(0, start);
  const suffix = pattern.slice(end + 1);
  const expanded = [];
  for (const alternative of alternatives) {
    expanded.push(...expandBracePatterns(`${prefix}${alternative}${suffix}`, limit - expanded.length));
    if (expanded.length > limit) throw new Error("brace expansion exceeds safety limit");
  }
  return expanded;
}

function validateGlobPattern(pattern, collectionName) {
  if (typeof pattern !== "string" || pattern.length === 0 || pattern.includes("\0")) {
    throw new Error(`Invalid empty or non-text glob for collection ${collectionName}`);
  }
  if (pattern.includes("\\")) {
    throw new Error(`Backslashes are not allowed in collection glob for ${collectionName}`);
  }
  let alternatives;
  try {
    alternatives = expandBracePatterns(pattern);
  } catch (error) {
    throw new Error(`Unsafe glob for collection ${collectionName}: ${error.message}`);
  }
  for (const alternative of alternatives) {
    if (isAbsolute(alternative) || win32.isAbsolute(alternative) || /^[A-Za-z]:/.test(alternative)) {
      throw new Error(`Absolute glob rejected for collection ${collectionName}`);
    }
    if (alternative.split("/").some((part) => part === "..")) {
      throw new Error(`Parent traversal glob rejected for collection ${collectionName}`);
    }
  }
}

function pathIsWithin(root, candidate) {
  const rel = relative(root, candidate);
  return rel === "" || (!isAbsolute(rel) && rel !== ".." && !rel.startsWith(`..${sep}`));
}

async function preflightTargets(targets, fastGlob) {
  const excludeDirs = ["node_modules", ".git", ".cache", "vendor", "dist", "build"];
  for (const target of targets) {
    validateGlobPattern(target.pattern, target.name);
    const ignores = target.ignore_patterns ? JSON.parse(target.ignore_patterns) : [];
    if (!Array.isArray(ignores) || ignores.some((pattern) => typeof pattern !== "string")) {
      throw new Error(`Invalid ignore_patterns for collection ${target.name}`);
    }
    const files = await fastGlob(target.pattern, {
      cwd: target.path,
      onlyFiles: true,
      followSymbolicLinks: false,
      dot: false,
      ignore: [...excludeDirs.map((dir) => `**/${dir}/**`), ...ignores],
    });
    for (const file of files) {
      if (file.split("/").some((part) => part.startsWith("."))) continue;
      let realFile;
      try {
        realFile = realpathSync(resolve(target.path, file));
      } catch (error) {
        throw new Error(`Cannot resolve indexed file ${file} in ${target.name}: ${error.message}`);
      }
      if (!pathIsWithin(target.path, realFile)) {
        throw new Error(`Indexed file escapes collection root: ${file} in ${target.name}`);
      }
    }
  }
}

function lookupTargets(db, repos) {
  const rows = db.prepare(
    "SELECT name, path, pattern, ignore_patterns, include_by_default FROM store_collections",
  ).all();
  const targets = [];
  for (const input of repos) {
    const root = canonicalGitRoot(input);
    if (root.skip) {
      console.log(`SKIP ${input}: ${root.skip}`);
      continue;
    }
    const collection = rows.find((row) => {
      try {
        return realpathSync(row.path) === root.path;
      } catch {
        return false;
      }
    });
    if (!collection) {
      console.log(`SKIP ${root.path}: no existing registered collection`);
      continue;
    }
    if (collection.include_by_default !== 1) {
      console.log(`SKIP ${root.path}: collection ${collection.name} is not explicitly default-included`);
      continue;
    }
    targets.push({ ...collection, path: root.path });
  }
  return targets;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(usage());
    return;
  }
  const dbPath = resolve(options.dbPath);
  const storeModulePath = resolve(options.storeModule);
  if (!existsSync(dbPath)) throw new Error(`QMD database does not exist: ${dbPath}`);
  if (!existsSync(storeModulePath)) throw new Error(`QMD store module does not exist: ${storeModulePath}`);

  const qmd = await import(pathToFileURL(storeModulePath).href);
  if (typeof qmd.createStore !== "function" || typeof qmd.reindexCollection !== "function") {
    throw new Error(`Unsupported QMD store API at ${storeModulePath}: expected createStore and reindexCollection`);
  }
  const Database = loadDatabaseConstructor(storeModulePath);
  const require = createRequire(pathToFileURL(storeModulePath));
  const fastGlob = require("fast-glob");
  if (options.dryRun) {
    const db = new Database(dbPath, { readonly: true, fileMustExist: true });
    try {
      const targets = lookupTargets(db, options.repos);
      await preflightTargets(targets, fastGlob);
      for (const target of targets) console.log(`DRY-RUN ${target.path}: ${target.name}`);
      console.log(`DRY-RUN eligible collections: ${targets.length}`);
    } finally {
      db.close();
    }
    return;
  }

  const store = qmd.createStore(dbPath);
  try {
    const targets = lookupTargets(store.db, options.repos);
    await preflightTargets(targets, fastGlob);
    store.db.exec(`
      CREATE TEMP TRIGGER qmd_preserve_content_history
      BEFORE DELETE ON main.content
      BEGIN
        SELECT RAISE(IGNORE);
      END
    `);
    try {
      for (const target of targets) {
        const ignores = target.ignore_patterns ? JSON.parse(target.ignore_patterns) : [];
        store.db.exec("BEGIN IMMEDIATE");
        try {
          const stats = await qmd.reindexCollection(
            store,
            target.path,
            target.pattern,
            target.name,
            { ignorePatterns: ignores },
          );
          store.db.exec("COMMIT");
          console.log(
            `REFRESH ${target.path}: ${target.name} indexed=${stats.indexed} updated=${stats.updated} unchanged=${stats.unchanged} deactivated=${stats.removed}; historical content retained`,
          );
        } catch (error) {
          store.db.exec("ROLLBACK");
          throw error;
        }
      }
    } finally {
      store.db.exec("DROP TRIGGER IF EXISTS temp.qmd_preserve_content_history");
    }
  } finally {
    store.close();
  }
}

main().catch((error) => {
  console.error(`qmd-refresh-workspace: ${error.stack || error.message || error}`);
  process.exitCode = 1;
});
