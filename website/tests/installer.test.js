import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Installer, LEGACY, validatePackage, validateLegacy, installationOrder, checkInstalled, sha256, decode } from '../installer.js';
import { WebTilpTransport, describePythonObject } from '../transport.js';
import { buildLegacyManifest, formatManifest, readZip, RELEASES, V1, PACKS_V1 } from '../../build/legacy_manifest.mjs';
import createConverter from '../vendor/TIVarsLib.js';

const LEGACY_PATH = fileURLToPath(new URL('../legacy-v1.json', import.meta.url));
const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const path = relative => fileURLToPath(new URL('../../' + relative, import.meta.url));
const record = name => JSON.parse(fs.readFileSync(fileURLToPath(new URL('../' + name, import.meta.url)), 'utf8'));
const text = value => new TextEncoder().encode(value);
const digest = value => sha256(text(value));
let converterPromise;
const converter = () => converterPromise ||= createConverter();

// The fake calculator stores fingerprints: `${origin}:${module}` stands for content.
async function fixture(modules = [['CAS', 'ram'], ['CVNODE', 'archive']]) {
  const files = [];
  for (const [module, destination] of modules) {
    const data = text(`new:${module}`);
    files.push({ module, destination, name: module + (destination === 'ram' ? '.8xpy2' : '.8mp2'),
      kind: destination === 'ram' ? 'source' : 'bytecode', data: btoa(`new:${module}`), bytes: data.length,
      sha256: await sha256(data), sourceSha256: await digest(`newsrc:${module}`) });
  }
  return { schema: 2, runtimeCompilation: false, files, totalBytes: files.reduce((s, f) => s + f.bytes, 0) };
}

async function legacyFixture() {
  const files = [];
  for (const [module, type] of [['CASEVO', 15], ['CVTEST', 15], ['CVNODE', 18], ['CVOLD', 18], ['CVP00001', 18]]) {
    files.push({ module, type, location: type === 18 ? 'archive' : 'ram',
      sha256: await digest(`v1:${module}`), sourceSha256: await digest(`v0:${module}`) });
  }
  return { schema: 1, release: 'v1', files };
}

// A calculator object: origin 'v1' or 'new' objects are compiled unless they are launchers;
// 'v0' objects and anything named in `source` are Python source text.
async function object(name, type, attr, origin, { size = 1000, compiled } = {}) {
  const launcher = ['CAS', 'CASEVO', 'CVTEST'].includes(name);
  return { name, type, attr, size, folder: '',
    content: { compiled: compiled ?? (origin !== 'v0' && !launcher), sha256: await digest(`${origin}:${name}`) } };
}

function fakeTransport({ flash = 3000000, ram = 100000, reclaim = true } = {}) {
  const vars = [], sent = [], removed = [], calls = [];
  const memory = { flash };
  const transport = { vars, sent, removed, calls, memory, moduleType: 18, connected: true,
    async list() {
      calls.push('list');
      return { vars: vars.map(({ content, unreadable, ...entry }) => structuredClone(entry)),
        memory: { ok: true, flash_free: memory.flash, ram_free: ram } };
    },
    async remove(entry) {
      calls.push('remove ' + entry.name);
      const index = vars.findIndex(v => v.name === entry.name && v.type === entry.type);
      assert.notEqual(index, -1, 'removed a file that does not exist');
      if (reclaim && vars[index].attr === 3) memory.flash += vars[index].size;
      vars.splice(index, 1);
      removed.push(entry.name);
    },
    async send(file) {
      calls.push('send ' + file.module);
      sent.push(file);
      const type = file.destination === 'ram' ? 15 : transport.moduleType;
      const index = vars.findIndex(v => v.name === file.module && v.type === type);
      if (index >= 0) vars.splice(index, 1);
      vars.push({ name: file.module, type, attr: file.destination === 'ram' ? 0 : 3, size: file.bytes,
        content: { sha256: await sha256(decode(file.data)) } });
    }
  };
  return transport;
}

const names = list => list.map(item => item.name).sort();

test('corrupt packages, wrong destinations and an invalid legacy record fail before any device access', async () => {
  const device = { list() { assert.fail('device was accessed'); } };
  for (const mutation of [p => p.files[1].data = btoa('wrong'), p => p.files[1].destination = 'ram', p => p.files.push(p.files[0]),
    p => p.files[1].sourceSha256 = 'nothex']) {
    const pkg = await fixture(); mutation(pkg);
    const installer = new Installer(device);
    await assert.rejects(installer.install(pkg, await legacyFixture()));
    assert.equal(installer.busy, false);
  }
  for (const mutation of [l => l.files[2].sha256 = 'x', l => l.files.push(l.files[0]), l => l.files[0].type = 5,
    l => l.files[2].location = 'ram', l => l.schema = 2, l => { l.files = []; }]) {
    const legacy = await legacyFixture(); mutation(legacy);
    await assert.rejects(new Installer(device).install(await fixture(), legacy), /record of earlier/);
  }
  await assert.rejects(new Installer(device).install(await fixture()), /record of earlier/);
});

test('the new package shape: arbitrary pack names, launchers required, everything else archive bytecode', async () => {
  const pkg = await fixture([['CAS', 'ram'], ['CVUI', 'archive'], ['ENGINE1', 'archive'], ['Q', 'archive']]);
  delete pkg.files[1].sourceSha256;
  await validatePackage(pkg);
  // The launcher is required; CVTEST (developer only since QPL Q1) is no RAM launcher any more.
  for (const mutation of [p => p.files.splice(0, 1), p => p.files[1].kind = 'source', p => p.files[2].module = 'engine1',
    p => p.files[2].module = 'TOOLONGNAME', p => { p.files[1].bytes = 70000; },
    p => Object.assign(p.files[1], { module: 'CVTEST', name: 'CVTEST.8xpy2', destination: 'ram', kind: 'source' })]) {
    const broken = await fixture([['CAS', 'ram'], ['CVUI', 'archive'], ['ENGINE1', 'archive']]);
    mutation(broken);
    await assert.rejects(validatePackage(broken));
  }
});

test('libraries install first, launchers last, and every destination is verified', async () => {
  const pkg = await fixture(), transport = fakeTransport(), events = [];
  const result = await new Installer(transport, e => events.push(e)).install(pkg, await legacyFixture());
  assert.deepEqual(transport.sent.map(f => f.module), ['CVNODE', 'CAS']);
  assert.equal(result.completed, 2);
  assert.deepEqual(result.removed, []);
  assert.equal(events.at(-1).phase, 'complete');
  assert.deepEqual(checkInstalled(pkg.files, await transport.list()), []);
});

test('earlier files are removed before the new package is sent', async () => {
  for (const moduleType of [18, 15]) {
    const pkg = await fixture(), transport = fakeTransport(), events = [];
    transport.moduleType = moduleType;
    transport.vars.push(await object('CVOLD', moduleType, 3, 'v1'), await object('CVP00001', moduleType, 3, 'v1'),
      // An earlier source companion the v1 installer moved to archive, beside its compiled module.
      ...(moduleType === 18 ? [await object('CVP00001', 15, 3, 'v0')] : []));
    const result = await new Installer(transport, e => events.push(e)).install(pkg, await legacyFixture());
    assert.equal(result.stopped, false);
    assert.deepEqual(transport.removed.sort(), moduleType === 18 ? ['CVOLD', 'CVP00001', 'CVP00001'] : ['CVOLD', 'CVP00001']);
    assert.ok(transport.calls.lastIndexOf('remove CVOLD') < transport.calls.indexOf('send CVNODE'));
    assert.ok(!transport.vars.some(v => ['CVOLD', 'CVP00001'].includes(v.name)));
    const phases = events.map(e => e.phase);
    assert.ok(phases.indexOf('removed') < phases.indexOf('sending'));
    assert.deepEqual(names(events.at(-1).removed), names(result.removed));
  }
});

test('outdated files are deleted without reading them back, whatever their contents', async () => {
  const pkg = await fixture(), transport = fakeTransport(), events = [];
  transport.vars.push(await object('CVOLD', 18, 3, 'edited'), { ...await object('CVP00001', 18, 3, 'v1'), unreadable: true },
    await object('CVP00001', 15, 3, 'user'));
  const result = await new Installer(transport, e => events.push(e)).install(pkg, await legacyFixture());
  assert.equal(result.stopped, false);
  assert.deepEqual(transport.removed.sort(), ['CVOLD', 'CVP00001', 'CVP00001']);
  assert.deepEqual(transport.calls.slice(0, 4), ['list', 'remove CVOLD', 'remove CVP00001', 'remove CVP00001']);
  assert.equal(events.at(-1).phase, 'complete');
  assert.deepEqual(names(events.at(-1).removed), names(result.removed));
});

test('unrelated files are never read or removed', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('USERPRG', 15, 0, 'user'), await object('MYDATA', 18, 3, 'user'),
    await object('CVZZZ', 18, 3, 'user'), { name: 'CVOLD', type: 5, attr: 0, size: 20 },
    { name: 'CVNODE', type: 21, attr: 3, size: 20 });
  const before = structuredClone(transport.vars);
  await new Installer(transport).install(pkg, await legacyFixture());
  assert.deepEqual(transport.removed, []);
  for (const entry of before) assert.ok(transport.vars.some(v => v.name === entry.name && v.type === entry.type));
});

test('same-name objects in the package slots are overwritten by the send, not read or deleted', async () => {
  for (const [name, type, attr, origin] of [['CVNODE', 18, 3, 'v1'], ['CVNODE', 18, 3, 'user'], ['CAS', 15, 0, 'user']]) {
    const pkg = await fixture(), transport = fakeTransport();
    transport.vars.push(await object(name, type, attr, origin));
    const result = await new Installer(transport).install(pkg, await legacyFixture());
    assert.equal(result.completed, 2, `${name} from ${origin}`);
    assert.deepEqual(transport.removed, []);
    assert.deepEqual(transport.calls.filter(c => !c.startsWith('send')), ['list', 'list', 'list']);
  }
});

test('a copy of a library in the wrong slot is deleted before the library is sent', async () => {
  for (const [type, attr] of [[15, 0], [15, 3]]) {
    const pkg = await fixture(), transport = fakeTransport();
    transport.vars.push(await object('CVNODE', type, attr, 'user'));
    await new Installer(transport).install(pkg, await legacyFixture());
    assert.deepEqual(transport.removed, ['CVNODE']);
    assert.ok(transport.calls.indexOf('remove CVNODE') < transport.calls.indexOf('send CVNODE'));
    assert.deepEqual(transport.vars.filter(v => v.name === 'CVNODE').map(v => v.type), [18]);
  }
});

test('stop during cleanup waits for the active removal and sends nothing', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('CVOLD', 18, 3, 'v1'), await object('CVP00001', 18, 3, 'v1'));
  let installer;
  installer = new Installer(transport, e => { if (e.phase === 'removing') installer.stop(); });
  const result = await installer.install(pkg, await legacyFixture());
  assert.equal(result.stopped, true);
  assert.equal(result.completed, 0);
  assert.equal(transport.removed.length, 1);
  assert.deepEqual(names(result.removed), transport.removed);
  assert.deepEqual(transport.sent, []);
  // Stopping while the calculator is listed changes nothing.
  const checking = fakeTransport();
  checking.vars.push(await object('CVOLD', 18, 3, 'v1'));
  installer = new Installer(checking, e => { if (e.phase === 'checking') installer.stop(); });
  assert.deepEqual(await installer.install(pkg, await legacyFixture()), { removed: [], stopped: true, completed: 0 });
  assert.deepEqual(checking.removed, []);
  assert.deepEqual(checking.sent, []);
});

test('archive space freed by removals counts only after the calculator confirms it', async () => {
  const pkg = await fixture();
  const required = pkg.files.filter(f => f.destination === 'archive').reduce((s, f) => s + 2 * (f.bytes + 64), 16384);
  const tight = fakeTransport({ flash: required - 500 });
  tight.vars.push(await object('CVOLD', 18, 3, 'v1', { size: 1000 }));
  await new Installer(tight).install(pkg, await legacyFixture());
  assert.equal(tight.sent.length, 2);
  // The calculator still reports the old free space after removal: nothing is sent.
  const stale = fakeTransport({ flash: required - 500, reclaim: false });
  stale.vars.push(await object('CVOLD', 18, 3, 'v1', { size: 1000 }));
  await assert.rejects(new Installer(stale).install(pkg, await legacyFixture()), /after removing 1 earlier/);
  assert.deepEqual(stale.sent, []);
  // Too little space even if every candidate were removed: nothing is read or changed.
  const hopeless = fakeTransport({ flash: required - 5000 });
  hopeless.vars.push(await object('CVOLD', 18, 3, 'v1', { size: 1000 }));
  await assert.rejects(new Installer(hopeless).install(pkg, await legacyFixture()), /Archive needs/);
  assert.deepEqual(hopeless.calls, ['list']);
});

test('a removal the calculator does not confirm stops before sending', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('CVOLD', 18, 3, 'v1'));
  transport.remove = async entry => { transport.removed.push(entry.name); };
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /CVOLD could not be confirmed as removed/);
  assert.deepEqual(transport.sent, []);
});

test('low archive/RAM capacity rejects before sending launchers', async () => {
  const pkg = await fixture();
  for (const memory of [{ ok: true, flash_free: 0, ram_free: 100000 }, { ok: true, flash_free: 3000000, ram_free: 0 }]) {
    const transport = fakeTransport();
    transport.list = async () => ({ vars: [], memory });
    await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /free|RAM/);
    assert.equal(transport.sent.length, 0);
  }
});

test('stop waits for the current file and never starts the next', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  let installer;
  installer = new Installer(transport, e => { if (e.phase === 'sending') installer.stop(); });
  const result = await installer.install(pkg, await legacyFixture());
  assert.deepEqual(result, { removed: [], stopped: true, completed: 1 });
  assert.equal(transport.sent.length, 1);
});

test('acknowledged transfer with the wrong location is not reported as installed', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.send = async file => transport.vars.push({ name: file.module, type: 15, attr: 0 });
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /could not be confirmed/);
});

test('missing directory listing does not send the package', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.list = async () => ({ memory: { ok: true, flash_free: 3000000, ram_free: 100000 } });
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /file list/);
  assert.equal(transport.sent.length, 0);
});

test('native calls are serialized and timeout permanently retires WASM', async () => {
  const t = new WebTilpTransport({ gap: 0, timeout: 15 });
  let active = 0, maximum = 0, calls = 0;
  t.module = { ccall: async name => {
    calls++; active++; maximum = Math.max(maximum, active);
    if (name === 'hang') return new Promise(() => {});
    await new Promise(resolve => setTimeout(resolve, 1)); active--; return 0;
  } };
  await Promise.all([t.call('a'), t.call('b')]);
  assert.equal(maximum, 1);
  await assert.rejects(t.call('hang'), /stopped responding/);
  await assert.rejects(t.call('after'), /Reload/);
  assert.equal(calls, 3);
});

test('a timed-out removal ends the run before anything is sent', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('CVOLD', 18, 3, 'v1'), await object('CVP00001', 18, 3, 'v1'));
  transport.remove = async () => { transport.dead = true; throw new Error('The calculator stopped responding.'); };
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /stopped responding/);
  assert.deepEqual(transport.sent, []);
});

test('transport passes archive=1 for bytecode and RAM=0 for source', async () => {
  const pkg = await fixture(), calls = [];
  const t = new WebTilpTransport({ gap: 0 });
  t.connected = true; t.handle = 7;
  t.module = { FS: { writeFile() {}, unlink() {} }, ccall(name, type, argTypes, args) { calls.push({ name, args }); return 0; } };
  for (const file of installationOrder(pkg.files)) await t.send(file);
  assert.deepEqual(calls.map(c => c.args[3]), [1, 0]);
  assert.deepEqual(installationOrder(pkg.files).map(f => f.module), ['CVNODE', 'CAS']);
  assert.ok(calls.every(c => c.name === 'send_file_custom' && c.args[4] === 0));
});

test('the shipped package passes all checks', async t => {
  const path = process.env.CAS_EVO_PACKAGE || 'dist/archive-transfer/package.json';
  if (!fs.existsSync(path)) return t.skip('build archive transfer package first');
  const pkg = await validatePackage(JSON.parse(fs.readFileSync(path, 'utf8')));
  assert.equal(pkg.files.filter(f => f.destination === 'ram').map(f => f.module).sort().join(), 'CAS');
  assert.ok(!pkg.files.some(f => ['CVTEST', 'CASEVO'].includes(f.module)));
  assert.ok(pkg.files.every(f => f.destination === 'ram' || (f.kind === 'bytecode' && f.name.endsWith('.8mp2'))));
  const known = await converter();
  for (const file of pkg.files) {
    const object = await describePythonObject(known, decode(file.data));
    assert.equal(object.name, file.module);
    assert.equal(object.compiled, file.destination === 'archive');
  }
});

test('connect accepts the native positive init count and identifies EVO OS module types', async () => {
  for (const [version, expected] of [['7.0.0', 15], ['7.1.1', 18]]) {
    const calls = [];
    const module = { FS: { readFile: () => '{"vars":[],"memory":{"ok":true}}', unlink() {} },
      ccall(name) {
        calls.push(name);
        return { init: 1, create_handle: 123, calc_get_info_string: `OS Version: ${version}` }[name] ?? 0;
      }, _get_calc_model_id: () => 48 };
    for (const setting of ['cable_model', 'force_cable', 'calc_model', 'force_calc', 'cable_timeout', 'cable_delay']) {
      module['_set_' + setting] = () => {};
    }
    const transport = new WebTilpTransport({ gap: 0, factory: async () => module });
    const port = { getInfo: () => ({ usbVendorId: 0x0451, usbProductId: 0xe018 }) };
    const device = await transport.connect(port);
    assert.equal(device.model, 48);
    assert.equal(transport.moduleType, expected);
    assert.equal(module.__ticablesWebSerial.port, port);
    assert.deepEqual(calls, ['init', 'create_handle', 'open_cable', 'calc_get_info_string', 'calc_dirlist_json']);
    await transport.disconnect();
    assert.equal(transport.connected, false);
  }
});

// Build real EVO transfer objects with the pinned converter, as build/package_archive.mjs does.
async function evoObject(name, compiled, payload) {
  const known = await converter();
  const variable = known.TIVarFile.createNew('PythonAppVar', name, '84Evo');
  try {
    variable.setContentFromString(compiled ? JSON.stringify({ python: { compiledModule: true, name, bodyHex: Buffer.from(payload).toString('hex') } }) : payload);
    if (compiled) variable.convertToEvoPythonFormat('8mp2');
    variable.setArchived(compiled);
    const path = variable.saveVarToFile('.', name);
    const data = known.FS.readFile(path);
    known.FS.unlink(path);
    return data;
  } finally { variable.delete(); }
}

test('remove uses the exact WebTILP calc_del_var call', async () => {
  const calls = [];
  const transport = new WebTilpTransport({ gap: 0 });
  transport.connected = true; transport.handle = 9;
  transport.module = { ccall(name, type, types, args) { calls.push({ name, type, types, args }); return 0; } };
  await transport.remove({ name: 'CVPACK', type: 18, folder: '' });
  await transport.remove({ name: 'CVOLD', type: 15, folder: '' });
  assert.deepEqual(calls, [
    { name: 'calc_del_var', type: 'number', types: ['number', 'string', 'string', 'number'], args: [9, '', 'CVPACK', 18] },
    { name: 'calc_del_var', type: 'number', types: ['number', 'string', 'string', 'number'], args: [9, '', 'CVOLD', 15] }]);
  // A failing native call reports the calculator error and is not treated as success.
  transport.module.ccall = (name, type, types, args) => name === 'get_error_message' ? 'Variable is locked' : 7;
  await assert.rejects(transport.remove({ name: 'CVPACK', type: 18 }), /Removing old CVPACK: Variable is locked/);
  transport.connected = false;
  await assert.rejects(transport.remove({ name: 'CVPACK', type: 18 }), /disconnected/);
});

test('the legacy v1 record lists every v1 object with its calculator type and content hash', async () => {
  const raw = fs.readFileSync(LEGACY_PATH, 'utf8');
  const legacy = JSON.parse(raw);
  const modules = validateLegacy(legacy);
  assert.equal(legacy.release, 'v1');
  assert.equal(modules.size, 238);
  assert.deepEqual(legacy.package, { pagesCommit: V1.pagesCommit, sourceCommit: V1.sourceCommit, path: V1.path,
    sha256: V1.sha256, files: 238, totalBytes: 266520 });
  const launchers = legacy.files.filter(f => f.type === 15);
  assert.deepEqual(launchers.map(f => [f.module, f.location]), [['CASEVO', 'ram'], ['CVTEST', 'ram']]);
  const libraries = legacy.files.filter(f => f.type === 18);
  assert.equal(libraries.length, 236);
  assert.ok(libraries.every(f => f.location === 'archive' && /^CV[A-Z0-9]{1,6}$/.test(f.module)));
  assert.equal(libraries.filter(f => /^CVF\d{5}$/.test(f.module)).length, 128);
  assert.equal(libraries.filter(f => /^CVP\d{5}$/.test(f.module)).length, 56);
  assert.equal(new Set(legacy.files.map(f => f.sha256)).size, 238);
  assert.ok(legacy.files.every(f => /^[a-f0-9]{64}$/.test(f.sourceSha256)));
  assert.deepEqual(legacy.files.map(f => f.module), legacy.files.map(f => f.module).sort());
  assert.equal(formatManifest(legacy), raw);
});

// A published package from its pinned pages commit (or the CAS_EVO_V1_PACKAGE file for v1).
function pagesPackage(release) {
  if (release === V1 && process.env.CAS_EVO_V1_PACKAGE) return fs.readFileSync(process.env.CAS_EVO_V1_PACKAGE);
  try {
    return execFileSync('git', ['show', `${release.pagesCommit}:${release.path}`],
      { cwd: ROOT, maxBuffer: 16 << 20, stdio: ['ignore', 'pipe', 'ignore'] });
  } catch { return null; }
}
const v1Package = () => pagesPackage(V1);
const V1_MISSING = 'published v1 package unavailable; set CAS_EVO_V1_PACKAGE or fetch the pages history';

test('the legacy v1 record is reproducible from the published v1 package', async t => {
  const bytes = v1Package();
  if (!bytes) return t.skip(V1_MISSING);
  const { manifest } = await buildLegacyManifest(bytes, await converter());
  assert.equal(formatManifest(manifest), fs.readFileSync(LEGACY_PATH, 'utf8'));
  // The installer recognizes every v1 object by its decoded content, and nothing else.
  const pkg = JSON.parse(Buffer.from(bytes).toString('utf8'));
  const legacy = validateLegacy(manifest);
  for (const file of pkg.files.slice(0, 12)) {
    const object = await describePythonObject(await converter(), decode(file.data));
    const [entry] = legacy.get(file.module);
    assert.equal(object.sha256, entry.sha256);
    assert.equal(object.compiled, entry.type === 18);
  }
});

test('a calculator holding the complete v1 install is reduced to the new packs', async t => {
  const bytes = v1Package();
  if (!bytes) return t.skip(V1_MISSING);
  const v1 = JSON.parse(Buffer.from(bytes).toString('utf8'));
  const known = await converter();
  // A new release: two launchers and two packs, one reusing the v1 name CVUI.
  const files = [];
  for (const [module, compiled, payload] of [['CAS', false, 'import cvui\n'],
    ['CVUI', true, Uint8Array.from([0x4d, 5, 3, 0x1f, 9, 9])], ['CVENG', true, Uint8Array.from([0x4d, 5, 3, 0x1f, 7])]]) {
    const data = await evoObject(module, compiled, payload);
    files.push({ module, name: module + (compiled ? '.8mp2' : '.8xpy2'), kind: compiled ? 'bytecode' : 'source',
      destination: compiled ? 'archive' : 'ram', bytes: data.length, sha256: await sha256(data), data: Buffer.from(data).toString('base64') });
  }
  const pkg = { schema: 2, version: 'next', runtimeCompilation: false, files, totalBytes: files.reduce((s, f) => s + f.bytes, 0) };
  const vars = v1.files.map(file => ({ name: file.module, type: file.destination === 'ram' ? 15 : 18,
    attr: file.destination === 'ram' ? 0 : 3, size: file.bytes, folder: '', data: decode(file.data) }));
  vars.push({ name: 'CVF00007', type: 15, attr: 3, size: 40, folder: '', data: await evoObject('CVF00007', false, '# my edits\n') },
    { name: 'NOTES', type: 15, attr: 0, size: 40, folder: '', data: await evoObject('NOTES', false, 'x=1\n') });
  let flash = 1000000;
  const removed = [];
  const transport = { moduleType: 18, connected: true,
    describe: data => describePythonObject(known, data),
    async list() { return { vars: vars.map(({ data, ...entry }) => ({ ...entry })), memory: { ok: true, flash_free: flash, ram_free: 100000 } }; },
    inspect: entry => describePythonObject(known, vars.find(v => v.name === entry.name && v.type === entry.type).data),
    async remove(entry) {
      const index = vars.findIndex(v => v.name === entry.name && v.type === entry.type);
      flash += vars[index].size;
      removed.push(vars.splice(index, 1)[0].name);
    },
    async send(file) {
      const type = file.destination === 'ram' ? 15 : 18;
      const index = vars.findIndex(v => v.name === file.module && v.type === type);
      if (index >= 0) vars.splice(index, 1);
      vars.push({ name: file.module, type, attr: file.destination === 'ram' ? 0 : 3, size: file.bytes, folder: '', data: decode(file.data) });
    } };
  const result = await new Installer(transport).install(pkg, JSON.parse(fs.readFileSync(LEGACY_PATH, 'utf8')));
  assert.equal(result.completed, 3);
  assert.equal(removed.length, 238);
  assert.ok(!removed.includes('CVUI') && removed.includes('CASEVO') && removed.includes('CVTEST') && removed.includes('CVF00007'));
  assert.deepEqual(vars.map(v => `${v.name}/${v.type}`).sort(), ['CAS/15', 'CVENG/18', 'CVUI/18', 'NOTES/15']);
});

test('every recorded earlier release is served and validates, one record per file', async () => {
  assert.deepEqual(LEGACY, RELEASES.map(r => r.output.replace('website/', '')));
  const records = LEGACY.map(record);
  const modules = validateLegacy(records);
  assert.deepEqual(records.map(r => r.release), ['v1', 'packs-v1', 'mathprint-da7f036', 'mathprint-1b94211']);
  for (const [r, release] of records.map((r, i) => [r, RELEASES[i]])) {
    assert.deepEqual(r.package, { ...release.package, totalBytes: r.package.totalBytes });
    assert.equal(r.files.length, release.package.files);
    assert.equal(formatManifest(r), fs.readFileSync(path(release.output), 'utf8'));
  }
  // CASEVO and CVTEST are in every release; each pack-era record has the 21 packs and both launchers.
  assert.equal(modules.get('CASEVO').length, 4);
  assert.equal(modules.get('CVTEST').length, 4);
  for (const r of records.slice(1)) {
    assert.deepEqual(r.files.filter(f => f.type === 15).map(f => f.module), ['CASEVO', 'CVTEST']);
    assert.ok(r.files.filter(f => f.type === 18).every(f => /^CAS[A-Z0-9]{1,5}$/.test(f.module) && f.location === 'archive'));
  }
  // Within one record a module appears once.
  assert.throws(() => validateLegacy([records[1], { ...records[2], files: [...records[2].files, records[2].files[0]] }]), /record of earlier/);
  assert.throws(() => validateLegacy([]), /record of earlier/);
});
test('the packs-v1 record is reproducible from the published packs-v1 package', async t => {
  const bytes = pagesPackage(PACKS_V1);
  if (!bytes) return t.skip('published packs-v1 package unavailable; fetch the pages history');
  const { manifest, record: release } = await buildLegacyManifest(bytes, await converter());
  assert.equal(release.release, 'packs-v1');
  assert.equal(formatManifest(manifest), fs.readFileSync(path('website/legacy-packs-v1.json'), 'utf8'));
});

test('the MathPrint test-build records are reproducible from the delivered calculator ZIPs', async t => {
  for (const release of RELEASES.filter(r => r.package.zip)) {
    const file = path('dist/' + release.package.zip);
    if (!fs.existsSync(file)) { t.diagnostic(`${release.package.zip} not in dist; skipped`); continue; }
    const bytes = fs.readFileSync(file);
    assert.ok(readZip(bytes)['archive.json']);
    const { manifest } = await buildLegacyManifest(bytes, await converter());
    assert.equal(formatManifest(manifest), fs.readFileSync(path(release.output), 'utf8'));
  }
});

test('an earlier CASEVO or CVTEST is removed whatever its contents', async () => {
  for (const [name, origin] of [['CASEVO', 'v1'], ['CASEVO', 'edited'], ['CVTEST', 'v1'], ['CVTEST', 'edited'], ['CVTEST', 'v0']]) {
    const pkg = await fixture(), transport = fakeTransport();
    transport.vars.push(await object(name, 15, origin === 'v0' ? 3 : 0, origin));
    const result = await new Installer(transport).install(pkg, await legacyFixture());
    assert.equal(result.completed, 2);
    assert.deepEqual(transport.removed, [name]);
    assert.ok(transport.vars.some(v => v.name === 'CAS' && v.type === 15 && v.attr === 0));
  }
});

test('validatePackage requires the launcher it is given', async () => {
  const pkg = await fixture();
  await validatePackage(pkg);
  await assert.rejects(validatePackage(pkg, ['CASEVO', 'CVTEST']), /invalid or repeated|incomplete/);
  const old = await fixture([['CASEVO', 'ram'], ['CVNODE', 'archive'], ['CVTEST', 'ram']]);
  await validatePackage(old, ['CASEVO', 'CVTEST']);
  await assert.rejects(validatePackage(old), /invalid or repeated|incomplete/);
});

test('a calculator holding the published packs-v1 install is upgraded', async t => {
  const bytes = pagesPackage(PACKS_V1);
  if (!bytes) return t.skip('published packs-v1 package unavailable; fetch the pages history');
  const old = JSON.parse(Buffer.from(bytes).toString('utf8'));
  const known = await converter();
  // The next release: the launcher CAS, every pack name again (new contents for two of them,
  // the others unchanged), and no CVTEST or CASEVO.
  const files = [];
  for (const file of old.files.filter(f => f.destination === 'archive')) {
    if (file.module === 'CASUI' || file.module === 'CASUX') {
      const data = await evoObject(file.module, true, Uint8Array.from([0x4d, 5, 3, 0x1f, file.module.length]));
      files.push({ ...file, bytes: data.length, sha256: await sha256(data), data: Buffer.from(data).toString('base64') });
    } else files.push(file);
  }
  const launcher = await evoObject('CAS', false, 'import CASUI\n');
  files.push({ module: 'CAS', name: 'CAS.8xpy2', kind: 'source', destination: 'ram', bytes: launcher.length,
    sha256: await sha256(launcher), data: Buffer.from(launcher).toString('base64') });
  const pkg = { schema: 2, version: 'packs-v1', runtimeCompilation: false, files, totalBytes: files.reduce((s, f) => s + f.bytes, 0) };
  const vars = old.files.map(file => ({ name: file.module, type: file.destination === 'ram' ? 15 : 18,
    attr: file.destination === 'ram' ? 0 : 3, size: file.bytes, folder: '', data: decode(file.data) }));
  vars.push({ name: 'NOTES', type: 15, attr: 0, size: 40, folder: '', data: await evoObject('NOTES', false, 'x=1\n') });
  let flash = 1000000;
  const removed = [], sent = [];
  const transport = { moduleType: 18, connected: true,
    describe: data => describePythonObject(known, data),
    async list() { return { vars: vars.map(({ data, ...entry }) => ({ ...entry })), memory: { ok: true, flash_free: flash, ram_free: 100000 } }; },
    inspect: entry => describePythonObject(known, vars.find(v => v.name === entry.name && v.type === entry.type).data),
    async remove(entry) {
      const index = vars.findIndex(v => v.name === entry.name && v.type === entry.type);
      flash += vars[index].size;
      removed.push(vars.splice(index, 1)[0].name);
    },
    async send(file) {
      sent.push(file.module);
      const type = file.destination === 'ram' ? 15 : 18;
      const index = vars.findIndex(v => v.name === file.module && v.type === type);
      if (index >= 0) vars.splice(index, 1);
      vars.push({ name: file.module, type, attr: file.destination === 'ram' ? 0 : 3, size: file.bytes, folder: '', data: decode(file.data) });
    } };
  const result = await new Installer(transport).install(pkg, LEGACY.map(record));
  assert.equal(result.stopped, false);
  assert.deepEqual(removed.sort(), ['CASEVO', 'CVTEST']);
  assert.equal(sent.length, 22);
  assert.equal(sent.at(-1), 'CAS');
  assert.deepEqual(vars.filter(v => v.type === 15).map(v => v.name).sort(), ['CAS', 'NOTES']);
  // The pack names are current names, so the v1 record alone upgrades it the same way.
  const fresh = old.files.map(file => ({ name: file.module, type: file.destination === 'ram' ? 15 : 18,
    attr: file.destination === 'ram' ? 0 : 3, size: file.bytes, folder: '', data: decode(file.data) }));
  vars.length = 0; vars.push(...fresh); sent.length = 0; removed.length = 0;
  await new Installer(transport).install(pkg, record('legacy-v1.json'));
  assert.deepEqual(removed.sort(), ['CASEVO', 'CVTEST']);
  assert.equal(sent.length, 22);
});
