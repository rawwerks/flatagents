#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');

const ALLOWED_TAGS = new Set(['if', 'elif', 'else', 'endif', 'for', 'endfor', 'set']);
const ALLOWED_FILTERS = new Set([
  'default',
  'length',
  'lower',
  'upper',
  'trim',
  'replace',
  'join',
  'first',
  'last',
  'truncate',
  'tojson',
]);

const DISALLOWED_PATTERNS = [
  { regex: /\[[0-9]*:[0-9]*\]/g, message: 'python-style slicing is not allowed' },
  { regex: /\|\s*(map|dictsort|list|select|reject|attr|round|int|float)\b/g, message: 'unsupported filter' },
];

const TEMPLATE_BLOCK_REGEX = /{{[\s\S]*?}}|{%-?[\s\S]*?-?%}/g;
const TAG_REGEX = /{%\s*([A-Za-z_][\w-]*)/g;
const FILTER_REGEX = /\|\s*([A-Za-z_][\w-]*)/g;

function getLineOffsets(text) {
  const offsets = [0];
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '\n') {
      offsets.push(i + 1);
    }
  }
  return offsets;
}

function offsetToLineCol(offsets, index) {
  let low = 0;
  let high = offsets.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (offsets[mid] <= index) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  const line = Math.max(0, high) + 1;
  const col = index - offsets[Math.max(0, high)] + 1;
  return { line, col };
}

function walk(dir, results) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.git' || entry.name === 'dist') {
        continue;
      }
      walk(fullPath, results);
    } else if (entry.isFile()) {
      results.push(fullPath);
    }
  }
}

function isConfigFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (!['.yml', '.yaml', '.json'].includes(ext)) return false;
  const parts = filePath.split(path.sep);
  return parts.includes('config');
}

function lintFile(filePath) {
  const text = fs.readFileSync(filePath, 'utf8');
  const offsets = getLineOffsets(text);
  const errors = [];

  const blocks = text.matchAll(TEMPLATE_BLOCK_REGEX);
  for (const match of blocks) {
    const block = match[0];
    const startIndex = match.index ?? 0;

    for (const pattern of DISALLOWED_PATTERNS) {
      let patternMatch;
      while ((patternMatch = pattern.regex.exec(block)) !== null) {
        const absoluteIndex = startIndex + patternMatch.index;
        const { line, col } = offsetToLineCol(offsets, absoluteIndex);
        errors.push(`${filePath}:${line}:${col} ${pattern.message}`);
      }
    }

    if (block.startsWith('{%')) {
      let tagMatch;
      while ((tagMatch = TAG_REGEX.exec(block)) !== null) {
        const tag = tagMatch[1];
        if (!ALLOWED_TAGS.has(tag)) {
          const absoluteIndex = startIndex + tagMatch.index;
          const { line, col } = offsetToLineCol(offsets, absoluteIndex);
          errors.push(`${filePath}:${line}:${col} unsupported tag: ${tag}`);
        }
      }
    }

    let filterMatch;
    while ((filterMatch = FILTER_REGEX.exec(block)) !== null) {
      const filter = filterMatch[1];
      if (!ALLOWED_FILTERS.has(filter)) {
        const absoluteIndex = startIndex + filterMatch.index;
        const { line, col } = offsetToLineCol(offsets, absoluteIndex);
        errors.push(`${filePath}:${line}:${col} unsupported filter: ${filter}`);
      }
    }
  }

  return errors;
}

function main() {
  const allFiles = [];
  walk(ROOT_DIR, allFiles);

  const configFiles = allFiles.filter(isConfigFile);
  const allErrors = [];

  for (const filePath of configFiles) {
    allErrors.push(...lintFile(filePath));
  }

  if (allErrors.length) {
    console.error('[lint_templates] Template subset violations found:');
    for (const error of allErrors) {
      console.error(`- ${error}`);
    }
    process.exit(1);
  }

  console.log(`[lint_templates] OK (${configFiles.length} config files checked)`);
}

main();
