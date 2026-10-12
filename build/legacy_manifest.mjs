// Record what each object of the published v1 release contains on the calculator.
//
//   git show 2849055909cabe6137bcdda0ada89b579628da11:public/package.json > v1-package.json
//   node build/legacy_manifest.mjs v1-package.json [website/legacy-v1.json] [--archive archive.json] [--check]
//
// Every v1 transfer object is decoded with the pinned TIVarsLib through the same
// function the browser installer applies to objects read back from an EVO.
// --archive cross-checks the per-file hashes recorded by build/archive.py;
// --check compares with the committed manifest instead of writing it.
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import createConverter from '../website/vendor/TIVarsLib.js';
import { decode, validatePackage, validateLegacy } from '../website/installer.js';
import { describePythonObject } from '../website/transport.js';

export const V1 = {
  release: 'v1',
  pagesCommit: '2849055909cabe6137bcdda0ada89b579628da11',
  sourceCommit: '25b83b0eb8cf4a90b9ba0ee0c734cae55b47247b',
  path: 'public/package.json',
  sha256: '930f71aceda6c1cccd2de5a08bdf0ed6d19bc17936aa35018142b4bee2ba3901',
  files: 238,
};

export async function buildLegacyManifest(bytes, converter) {
  const digest = crypto.createHash('sha256').update(bytes).digest('hex');
  if (digest !== V1.sha256) throw new Error(`not the published v1 package: sha256 ${digest}`);
  const pkg = await validatePackage(JSON.parse(Buffer.from(bytes).toString('utf8')));
  if (pkg.version !== V1.release || pkg.files.length !== V1.files) throw new Error('unexpected v1 package shape');
  const files = [];
  for (const file of [...pkg.files].sort((a, b) => a.module < b.module ? -1 : a.module > b.module ? 1 : 0)) {
    const compiled = file.destination === 'archive';
    const object = await describePythonObject(converter, decode(file.data));
    if (object.name !== file.module || object.compiled !== compiled || object.type !== (compiled ? 18 : 15)) {
      throw new Error(`${file.name} does not decode as its recorded module`);
    }
    files.push({ module: file.module, type: object.type, location: file.destination,
      sha256: object.sha256, sourceSha256: file.sourceSha256 });
  }
  const manifest = {
    schema: 1,
    release: V1.release,
    package: { pagesCommit: V1.pagesCommit, sourceCommit: V1.sourceCommit, path: V1.path,
      sha256: V1.sha256, files: pkg.files.length, totalBytes: pkg.totalBytes },
    digest: 'sha256 of the TIVarsLib-decoded python.bodyHex bytes (type 18, archive) or UTF-8 python.code (type 15, RAM)',
    sourceDigest: 'sha256 of an earlier source companion (type 15) that the v1 installer recognized by name',
    files,
  };
  validateLegacy(manifest);
  return manifest;
}

// One object per line keeps reviews and diffs readable.
export function formatManifest(manifest) {
  const { files, ...header } = manifest;
  const lines = Object.entries(header).map(([key, value]) => `  ${JSON.stringify(key)}: ${JSON.stringify(value)},`);
  return `{\n${lines.join('\n')}\n  "files": [\n${files.map(file => '    ' + JSON.stringify(file)).join(',\n')}\n  ]\n}\n`;
}

// The object hashes must agree with a local v1 rebuild. Source-companion hashes
// are reported only: the published package stays authoritative for them.
function crossCheck(manifest, archive) {
  const records = new Map(archive.files.map(file => [file.module, file]));
  const sourceDifferences = [];
  for (const entry of manifest.files) {
    const record = records.get(entry.module);
    if (!record || record.sha256 !== entry.sha256) throw new Error(`archive.json disagrees for ${entry.module}`);
    if (record.sourceSha256 !== entry.sourceSha256) sourceDifferences.push(entry.module);
  }
  if (records.size !== manifest.files.length) throw new Error('archive.json has a different file count');
  console.log(`archive.json: ${manifest.files.length} object hashes agree`
    + (sourceDifferences.length ? `; source-companion hash differs for ${sourceDifferences.join(', ')} (published value kept)` : ''));
}

async function main(argv) {
  const flags = new Set(argv.filter(arg => arg === '--check'));
  const positional = [];
  let archivePath;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--archive') archivePath = argv[++i];
    else if (!flags.has(argv[i])) positional.push(argv[i]);
  }
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const [input, output = path.join(root, 'website/legacy-v1.json')] = positional;
  if (!input) throw new Error('usage: node build/legacy_manifest.mjs v1-package.json [output] [--archive archive.json] [--check]');
  const converter = await createConverter();
  const manifest = await buildLegacyManifest(fs.readFileSync(input), converter);
  if (archivePath) crossCheck(manifest, JSON.parse(fs.readFileSync(archivePath, 'utf8')));
  const text = formatManifest(manifest);
  if (flags.has('--check')) {
    if (fs.readFileSync(output, 'utf8') !== text) throw new Error(`${output} differs from the v1 package`);
    console.log(`${output} matches the v1 package (${manifest.files.length} objects)`);
  } else {
    fs.writeFileSync(output, text);
    console.log(`Legacy v1 manifest: ${manifest.files.length} objects -> ${output}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error => { console.error(error.message || error); process.exitCode = 1; });
}
