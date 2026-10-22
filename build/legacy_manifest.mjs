// Record what each object of an earlier MicroCAS release (cas-evo before v1.0.2) contains on the calculator.
//
//   git show 2849055909cabe6137bcdda0ada89b579628da11:public/package.json > v1-package.json
//   node build/legacy_manifest.mjs v1-package.json [output] [--archive archive.json] [--check]
//   git show b6cb2e1aee5899e7731f62ac94ff447e4ad4a804:public/package.json > packs-v1-package.json
//   node build/legacy_manifest.mjs packs-v1-package.json [--check]
//   node build/legacy_manifest.mjs dist/cas-evo-mathprint-1b94211.zip [--check]
//
// The input is a published installer package (package.json) or a delivered calculator ZIP;
// RELEASES names each recorded one by its sha256, and its default output file. Every transfer
// object is decoded with the pinned TIVarsLib (website/transport.js describePythonObject); the
// browser installer itself uses only the recorded names. --archive cross-checks the per-file hashes recorded
// by build/archive.py; --check compares with the committed manifest instead of writing it.
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';
import createConverter from '../website/vendor/TIVarsLib.js';
import { decode, validatePackage, validateLegacy } from '../website/installer.js';
import { describePythonObject } from '../website/transport.js';

// Earlier releases whose objects the installer may remove or replace. Every one had the two
// launchers CASEVO and CVTEST; package is the header written into its record.
export const RELEASES = [
  { release: 'v1', output: 'website/legacy-v1.json', launchers: ['CASEVO', 'CVTEST'],
    package: { pagesCommit: '2849055909cabe6137bcdda0ada89b579628da11',
      sourceCommit: '25b83b0eb8cf4a90b9ba0ee0c734cae55b47247b', path: 'public/package.json',
      sha256: '930f71aceda6c1cccd2de5a08bdf0ed6d19bc17936aa35018142b4bee2ba3901', files: 238 } },
  { release: 'packs-v1', output: 'website/legacy-packs-v1.json', launchers: ['CASEVO', 'CVTEST'],
    package: { pagesCommit: 'b6cb2e1aee5899e7731f62ac94ff447e4ad4a804',
      sourceCommit: '702bc53964bc5af3f67c452ca5aa8504272b4c06', path: 'public/package.json',
      sha256: '714debeec00fdc786750948e0a7bffc76080f0ca361df6895060d0eb1faef18b', files: 23 } },
  // MathPrint test builds delivered as calculator ZIPs (branch mathprint).
  { release: 'mathprint-da7f036', output: 'website/legacy-mathprint-da7f036.json', launchers: ['CASEVO', 'CVTEST'],
    package: { zip: 'cas-evo-mathprint-da7f036.zip', sourceCommit: 'da7f036ed6bf4aa9d514139145734c170c46fdaa',
      sha256: 'c20a9c064fc09d7d1a40a70d92b74969f3f968905aa89a3d40485947a5fe4574', files: 23 } },
  { release: 'mathprint-1b94211', output: 'website/legacy-mathprint-1b94211.json', launchers: ['CASEVO', 'CVTEST'],
    package: { zip: 'cas-evo-mathprint-1b94211.zip', sourceCommit: '1b942116b81e94c985ff3a91e69e7be622bc97ed',
      sha256: '42ff38657cd2bf91bbef1900fc89004046574faef6dfdcef113ed4b5a67b73ad', files: 23 } },
];
const V1R = RELEASES[0];
export const V1 = { release: V1R.release, ...V1R.package };
export const PACKS_V1 = { release: 'packs-v1', ...RELEASES[1].package };

const SOURCE_DIGEST = {
  v1: 'sha256 of an earlier source companion (type 15) that the v1 installer recognized by name',
  other: 'sha256 of the source text the object was built from (archive.json sourceSha256)',
};

// The members of a ZIP file: {name: bytes} (stored or deflated, no ZIP64).
export function readZip(bytes) {
  const buf = Buffer.from(bytes);
  let end = buf.length - 22;
  while (end >= 0 && buf.readUInt32LE(end) !== 0x06054b50) end--;
  if (end < 0) throw new Error('not a ZIP file');
  const count = buf.readUInt16LE(end + 10);
  let at = buf.readUInt32LE(end + 16);
  const members = {};
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(at) !== 0x02014b50) throw new Error('bad ZIP directory');
    const method = buf.readUInt16LE(at + 10), size = buf.readUInt32LE(at + 20);
    const nameLength = buf.readUInt16LE(at + 28), extra = buf.readUInt16LE(at + 30), comment = buf.readUInt16LE(at + 32);
    const local = buf.readUInt32LE(at + 42);
    const name = buf.subarray(at + 46, at + 46 + nameLength).toString('utf8');
    if (buf.readUInt32LE(local) !== 0x04034b50) throw new Error('bad ZIP member ' + name);
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const raw = buf.subarray(start, start + size);
    if (method !== 0 && method !== 8) throw new Error('unsupported ZIP method for ' + name);
    members[name] = method === 8 ? zlib.inflateRawSync(raw) : Buffer.from(raw);
    at += 46 + nameLength + extra + comment;
  }
  return members;
}

// A calculator ZIP as an installer package: its archive.json with each object's bytes.
function zipPackage(bytes) {
  const members = readZip(bytes);
  const pkg = JSON.parse(members['archive.json'].toString('utf8'));
  pkg.files = pkg.files.map(file => {
    const data = members[file.name];
    if (!data || crypto.createHash('sha256').update(data).digest('hex') !== file.sha256) {
      throw new Error(`${file.name} is missing or changed in the ZIP`);
    }
    return { ...file, data: data.toString('base64') };
  });
  return pkg;
}

export async function buildLegacyManifest(bytes, converter) {
  const digest = crypto.createHash('sha256').update(bytes).digest('hex');
  const record = RELEASES.find(r => r.package.sha256 === digest);
  if (!record) throw new Error(`not a recorded MicroCAS (cas-evo) release package: sha256 ${digest}`);
  const raw = record.package.zip ? zipPackage(bytes) : JSON.parse(Buffer.from(bytes).toString('utf8'));
  const pkg = await validatePackage(raw, record.launchers);
  if (pkg.files.length !== record.package.files || pkg.version !== (record.release === 'v1' ? 'v1' : 'packs-v1')) {
    throw new Error(`unexpected ${record.release} package shape`);
  }
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
    release: record.release,
    package: { ...record.package, totalBytes: pkg.totalBytes },
    digest: 'sha256 of the TIVarsLib-decoded python.bodyHex bytes (type 18, archive) or UTF-8 python.code (type 15, RAM)',
    sourceDigest: SOURCE_DIGEST[record.release] || SOURCE_DIGEST.other,
    files,
  };
  validateLegacy(manifest);
  return { manifest, record };
}

// One object per line keeps reviews and diffs readable.
export function formatManifest(manifest) {
  const { files, ...header } = manifest;
  const lines = Object.entries(header).map(([key, value]) => `  ${JSON.stringify(key)}: ${JSON.stringify(value)},`);
  return `{\n${lines.join('\n')}\n  "files": [\n${files.map(file => '    ' + JSON.stringify(file)).join(',\n')}\n  ]\n}\n`;
}

// The object hashes must agree with a local rebuild. Source-companion hashes
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
  const [input, chosen] = positional;
  if (!input) throw new Error('usage: node build/legacy_manifest.mjs package.json|calculator.zip [output] [--archive archive.json] [--check]');
  const converter = await createConverter();
  const { manifest, record } = await buildLegacyManifest(fs.readFileSync(input), converter);
  const output = chosen || path.join(root, record.output);
  if (archivePath) crossCheck(manifest, JSON.parse(fs.readFileSync(archivePath, 'utf8')));
  const text = formatManifest(manifest);
  if (flags.has('--check')) {
    if (fs.readFileSync(output, 'utf8') !== text) throw new Error(`${output} differs from the ${record.release} package`);
    console.log(`${output} matches the ${record.release} package (${manifest.files.length} objects)`);
  } else {
    fs.writeFileSync(output, text);
    console.log(`Legacy ${record.release} manifest: ${manifest.files.length} objects -> ${output}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error => { console.error(error.message || error); process.exitCode = 1; });
}
