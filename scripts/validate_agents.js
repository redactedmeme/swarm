#!/usr/bin/env node
// Validate every .character.json agent/node file under agents/ parses and has a name.
// Usage: node scripts/validate_agents.js
//
// The character files use several coexisting schemas (elizaOS-style, v2 lore-card,
// sevenfold "voice", ad-hoc node). The only invariant we can enforce across all of
// them is: valid JSON, an object (or a one-element array wrapping one), and a
// non-empty string `name`. Duplicate `id`s (when present) are also flagged.

const fs = require('fs');
const path = require('path');

function walk(dir, acc) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__pycache__') continue;
      walk(full, acc);
    } else if (entry.name.endsWith('.character.json')) {
      acc.push(full);
    }
  }
  return acc;
}

function validate(data) {
  const errs = [];
  let obj = data;
  if (Array.isArray(obj)) {
    if (obj.length !== 1 || typeof obj[0] !== 'object') {
      errs.push('top-level array is not a single wrapped object');
      return { errs, obj: null };
    }
    obj = obj[0];
  }
  if (!obj || typeof obj !== 'object') {
    errs.push('not a JSON object');
    return { errs, obj: null };
  }
  if (!obj.name || typeof obj.name !== 'string' || !obj.name.trim()) {
    errs.push('missing non-empty string "name"');
  }
  return { errs, obj };
}

function main() {
  const agentsDir = path.resolve(__dirname, '..', 'agents');
  let files;
  try {
    files = walk(agentsDir, []).sort();
  } catch (e) {
    console.error('Failed to read agents directory:', e.message);
    process.exit(1);
  }

  let ok = true;
  const seenIds = new Map();

  for (const f of files) {
    const rel = path.relative(agentsDir, f);
    let data;
    try {
      data = JSON.parse(fs.readFileSync(f, 'utf8'));
    } catch (e) {
      console.error(`Invalid JSON in agents/${rel}: ${e.message}`);
      ok = false;
      continue;
    }
    const { errs, obj } = validate(data);
    if (obj && obj.id && typeof obj.id === 'string') {
      if (seenIds.has(obj.id)) {
        console.error(`Duplicate agent id '${obj.id}': agents/${rel} (earlier: agents/${seenIds.get(obj.id)})`);
        ok = false;
      } else {
        seenIds.set(obj.id, rel);
      }
    }
    if (errs.length) {
      ok = false;
      console.error(`Validation errors in agents/${rel}:`);
      errs.forEach((e) => console.error('  -', e));
    } else {
      console.log(`OK  agents/${rel}`);
    }
  }

  console.log(`\n${files.length} character files checked.`);
  if (ok) {
    console.log('All agent character files loaded and valid.');
    process.exit(0);
  }
  console.error('Agent character validation failed.');
  process.exit(2);
}

main();
