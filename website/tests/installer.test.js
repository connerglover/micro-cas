import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Installer, validatePackage, validateLegacy, installationOrder, checkInstalled, sha256, decode } from '../installer.js';
import { WebTilpTransport, describePythonObject } from '../transport.js';
import { buildLegacyManifest, formatManifest, V1 } from '../../build/legacy_manifest.mjs';
import createConverter from '../vendor/TIVarsLib.js';

const LEGACY_PATH = fileURLToPath(new URL('../legacy-v1.json', import.meta.url));
const text = value => new TextEncoder().encode(value);
const digest = value => sha256(text(value));
let converterPromise;
const converter = () => converterPromise ||= createConverter();

// The fake calculator stores fingerprints: `${origin}:${module}` stands for content.
async function fixture(modules = [['CASEVO', 'ram'], ['CVNODE', 'archive'], ['CVTEST', 'ram']]) {
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
  const launcher = ['CASEVO', 'CVTEST'].includes(name);
  return { name, type, attr, size, folder: '',
    content: { compiled: compiled ?? (origin !== 'v0' && !launcher), sha256: await digest(`${origin}:${name}`) } };
}

function fakeTransport({ flash = 3000000, ram = 100000, reclaim = true } = {}) {
  const vars = [], sent = [], removed = [], inspected = [], calls = [];
  const memory = { flash };
  const transport = { vars, sent, removed, inspected, calls, memory, moduleType: 18, connected: true,
    async describe(bytes) {
      const value = new TextDecoder().decode(bytes);
      const name = value.split(':')[1];
      const launcher = ['CASEVO', 'CVTEST'].includes(name);
      return { name, type: launcher ? 15 : 18, compiled: !launcher, bytes: bytes.length, sha256: await digest(value) };
    },
    async list() {
      calls.push('list');
      return { vars: vars.map(({ content, unreadable, ...entry }) => structuredClone(entry)),
        memory: { ok: true, flash_free: memory.flash, ram_free: ram } };
    },
    async inspect(entry) {
      calls.push('inspect ' + entry.name);
      inspected.push(entry.name);
      const found = vars.find(v => v.name === entry.name && v.type === entry.type);
      if (!found || found.unreadable) throw new Error('calculator error 42');
      return { name: found.name, type: found.type, ...found.content };
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
        content: await transport.describe(decode(file.data)) });
    }
  };
  return transport;
}

const names = list => list.map(item => item.name).sort();

test('corrupt packages, wrong destinations and an invalid legacy record fail before any device access', async () => {
  const device = { describe() { assert.fail('package objects were decoded'); }, list() { assert.fail('device was accessed'); } };
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

test('a package object that does not decode as its named module is rejected before device access', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.describe = async () => ({ name: 'OTHER', type: 18, compiled: true, sha256: '0'.repeat(64) });
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /does not contain the module/);
  assert.deepEqual(transport.calls, []);
});

test('the new package shape: arbitrary pack names, launchers required, everything else archive bytecode', async () => {
  const pkg = await fixture([['CASEVO', 'ram'], ['CVTEST', 'ram'], ['CVUI', 'archive'], ['ENGINE1', 'archive'], ['Q', 'archive']]);
  delete pkg.files[2].sourceSha256;
  await validatePackage(pkg);
  for (const mutation of [p => p.files.splice(1, 1), p => p.files[2].kind = 'source', p => p.files[3].module = 'engine1',
    p => p.files[3].module = 'TOOLONGNAME', p => { p.files[2].bytes = 70000; }]) {
    const broken = await fixture([['CASEVO', 'ram'], ['CVTEST', 'ram'], ['CVUI', 'archive'], ['ENGINE1', 'archive']]);
    mutation(broken);
    await assert.rejects(validatePackage(broken));
  }
});

test('libraries install first, launchers last, and every destination is verified', async () => {
  const pkg = await fixture(), transport = fakeTransport(), events = [];
  const result = await new Installer(transport, e => events.push(e)).install(pkg, await legacyFixture());
  assert.deepEqual(transport.sent.map(f => f.module), ['CVNODE', 'CVTEST', 'CASEVO']);
  assert.equal(result.completed, 3);
  assert.deepEqual(result.removed, []);
  assert.equal(events.at(-1).phase, 'complete');
  assert.deepEqual(checkInstalled(pkg.files, await transport.list()), []);
});

test('exactly matching earlier files are removed before the new package is sent', async () => {
  for (const moduleType of [18, 15]) {
    const pkg = await fixture(), transport = fakeTransport(), events = [];
    transport.moduleType = moduleType;
    transport.vars.push(await object('CVOLD', moduleType, 3, 'v1'), await object('CVP00001', moduleType, 3, 'v1'),
      // An earlier source companion the v1 installer moved to archive, beside its compiled module.
      ...(moduleType === 18 ? [await object('CVP00001', 15, 3, 'v0')] : []));
    const result = await new Installer(transport, e => events.push(e)).install(pkg, await legacyFixture());
    assert.equal(result.stopped, false);
    assert.deepEqual(transport.removed.sort(), moduleType === 18 ? ['CVOLD', 'CVP00001', 'CVP00001'] : ['CVOLD', 'CVP00001']);
    assert.deepEqual(result.preserved, []);
    assert.ok(transport.calls.lastIndexOf('remove CVOLD') < transport.calls.indexOf('send CVNODE'));
    assert.ok(!transport.vars.some(v => ['CVOLD', 'CVP00001'].includes(v.name)));
    const phases = events.map(e => e.phase);
    assert.ok(phases.indexOf('removed') < phases.indexOf('sending'));
    assert.deepEqual(names(events.at(-1).removed), names(result.removed));
  }
});

test('modified or unreadable earlier files are preserved and reported, and the install continues', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  const modified = await object('CVOLD', 18, 3, 'edited');
  const unreadable = { ...await object('CVP00001', 18, 3, 'v1'), unreadable: true };
  const compiledWithSourceHash = await object('CVP00001', 15, 3, 'v1', { compiled: false });
  transport.vars.push(modified, unreadable, compiledWithSourceHash);
  const events = [];
  const result = await new Installer(transport, e => events.push(e)).install(pkg, await legacyFixture());
  assert.equal(result.stopped, false);
  assert.deepEqual(transport.removed, []);
  assert.deepEqual(result.preserved.map(p => [p.name, p.type, p.reason]).sort(),
    [['CVOLD', 18, 'different'], ['CVP00001', 15, 'different'], ['CVP00001', 18, 'unreadable']]);
  assert.match(result.preserved.find(p => p.reason === 'unreadable').detail, /calculator error 42/);
  assert.ok(transport.vars.includes(modified) && transport.vars.includes(unreadable) && transport.vars.includes(compiledWithSourceHash));
  assert.equal(events.at(-1).phase, 'complete');
  assert.equal(events.at(-1).preserved.length, 3);
});

test('unrelated files are never read or removed', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('USERPRG', 15, 0, 'user'), await object('MYDATA', 18, 3, 'user'),
    await object('CVZZZ', 18, 3, 'user'), { name: 'CVOLD', type: 5, attr: 0, size: 20 },
    { name: 'CVNODE', type: 21, attr: 3, size: 20 });
  const before = structuredClone(transport.vars);
  await new Installer(transport).install(pkg, await legacyFixture());
  assert.deepEqual(transport.inspected, []);
  assert.deepEqual(transport.removed, []);
  for (const entry of before) assert.ok(transport.vars.some(v => v.name === entry.name && v.type === entry.type));
});

test('same-name objects are replaced only when they match the earlier release or the new package', async () => {
  for (const [name, type, attr, origin] of [['CVNODE', 18, 3, 'v1'], ['CVNODE', 18, 3, 'new'], ['CASEVO', 15, 0, 'v1'],
    ['CASEVO', 15, 0, 'v0'], ['CVTEST', 15, 0, 'new']]) {
    const pkg = await fixture(), transport = fakeTransport();
    transport.vars.push(await object(name, type, attr, origin));
    const result = await new Installer(transport).install(pkg, await legacyFixture());
    assert.equal(result.completed, 3, `${name} from ${origin}`);
    assert.deepEqual(transport.inspected, [name]);
    assert.deepEqual(transport.removed, []);
  }
  for (const [name, type, attr] of [['CVNODE', 18, 3], ['CASEVO', 15, 0], ['CVTEST', 15, 3]]) {
    const pkg = await fixture(), transport = fakeTransport();
    const foreign = await object(name, type, attr, 'user');
    transport.vars.push(foreign, await object('CVOLD', 18, 3, 'v1'));
    await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()),
      new RegExp(`${name} on the calculator could not be confirmed.*nothing was changed`));
    assert.deepEqual(transport.sent, []);
    assert.deepEqual(transport.removed, []);
    assert.ok(transport.vars.includes(foreign));
  }
  // An unreadable same-name object is not overwritten either.
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push({ ...await object('CVNODE', 18, 3, 'v1'), unreadable: true });
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /CVNODE on the calculator could not be confirmed/);
  assert.deepEqual(transport.sent, []);
});

test('a RAM source that would shadow a new library is removed only on an exact match', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('CVNODE', 15, 0, 'v0'));
  await new Installer(transport).install(pkg, await legacyFixture());
  assert.deepEqual(transport.removed, ['CVNODE']);
  assert.ok(transport.calls.indexOf('remove CVNODE') < transport.calls.indexOf('send CVNODE'));
  const blocked = fakeTransport();
  blocked.vars.push(await object('CVNODE', 15, 0, 'user'));
  await assert.rejects(new Installer(blocked).install(pkg, await legacyFixture()), /CVNODE on the calculator could not be confirmed/);
  assert.deepEqual(blocked.sent, []);
  // A modified archived source does not shadow anything; it is kept and reported.
  const archived = fakeTransport();
  archived.vars.push(await object('CVNODE', 15, 3, 'user'));
  const result = await new Installer(archived).install(pkg, await legacyFixture());
  assert.deepEqual(result.preserved.map(p => p.name), ['CVNODE']);
  assert.ok(archived.vars.some(v => v.name === 'CVNODE' && v.type === 15));
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
  // Stopping while same-name files are being read changes nothing.
  const reading = fakeTransport();
  reading.vars.push(await object('CVNODE', 18, 3, 'v1'), await object('CVOLD', 18, 3, 'v1'));
  installer = new Installer(reading, e => { if (e.phase === 'inspecting') installer.stop(); });
  assert.deepEqual(await installer.install(pkg, await legacyFixture()), { removed: [], preserved: [], stopped: true, completed: 0 });
  assert.deepEqual(reading.removed, []);
  assert.deepEqual(reading.sent, []);
  // Stopping while an earlier file is read back does not remove it afterwards.
  const checking = fakeTransport();
  checking.vars.push(await object('CVOLD', 18, 3, 'v1'));
  installer = new Installer(checking, e => { if (e.phase === 'inspecting') installer.stop(); });
  assert.deepEqual(await installer.install(pkg, await legacyFixture()), { removed: [], preserved: [], stopped: true, completed: 0 });
  assert.deepEqual(checking.inspected, ['CVOLD']);
  assert.deepEqual(checking.removed, []);
});

test('archive space freed by removals counts only after the calculator confirms it', async () => {
  const pkg = await fixture();
  const required = pkg.files.filter(f => f.destination === 'archive').reduce((s, f) => s + 2 * (f.bytes + 64), 16384);
  const tight = fakeTransport({ flash: required - 500 });
  tight.vars.push(await object('CVOLD', 18, 3, 'v1', { size: 1000 }));
  await new Installer(tight).install(pkg, await legacyFixture());
  assert.equal(tight.sent.length, 3);
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
  assert.deepEqual(result, { removed: [], preserved: [], stopped: true, completed: 1 });
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

test('a timed-out read ends the run instead of being treated as an unreadable file', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.vars.push(await object('CVOLD', 18, 3, 'v1'));
  transport.inspect = async () => { transport.dead = true; throw new Error('The calculator stopped responding.'); };
  await assert.rejects(new Installer(transport).install(pkg, await legacyFixture()), /stopped responding/);
  assert.deepEqual(transport.removed, []);
  assert.deepEqual(transport.sent, []);
});

test('transport passes archive=1 for bytecode and RAM=0 for source', async () => {
  const pkg = await fixture(), calls = [];
  const t = new WebTilpTransport({ gap: 0 });
  t.connected = true; t.handle = 7;
  t.module = { FS: { writeFile() {}, unlink() {} }, ccall(name, type, argTypes, args) { calls.push({ name, args }); return 0; } };
  for (const file of installationOrder(pkg.files)) await t.send(file);
  assert.deepEqual(calls.map(c => c.args[3]), [1, 0, 0]);
  assert.ok(calls.every(c => c.name === 'send_file_custom' && c.args[4] === 0));
});

test('the shipped package passes all checks', async t => {
  const path = process.env.CAS_EVO_PACKAGE || 'dist/archive-transfer/package.json';
  if (!fs.existsSync(path)) return t.skip('build archive transfer package first');
  const pkg = await validatePackage(JSON.parse(fs.readFileSync(path, 'utf8')));
  assert.equal(pkg.files.filter(f => f.destination === 'ram').map(f => f.module).sort().join(), 'CASEVO,CVTEST');
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

test('inspect reads real EVO objects back and remove uses the exact WebTILP calc_del_var call', async () => {
  const body = Uint8Array.from([0x4d, 0x05, 0x03, 0x1f, 1, 2, 3, 4, 250]);
  const source = 'value=42\nprint(value)\n';
  const objects = { CVPACK: await evoObject('CVPACK', true, body), CASEVO: await evoObject('CASEVO', false, source) };
  const calls = [], unlinked = [];
  let pending;
  const transport = new WebTilpTransport({ gap: 0, converterFactory: converter });
  transport.connected = true; transport.handle = 9;
  transport.module = { FS: {
    analyzePath: () => ({ exists: true }),
    readFile: path => path === '/last_recv_path.txt' ? pending : objects[path.split('/').pop().split('.')[0]] ?? Uint8Array.from([1, 2, 3]),
    unlink: path => unlinked.push(path)
  }, ccall(name, type, types, args) {
    calls.push({ name, type, types, args });
    if (name === 'calc_recv_var') pending = `/casevo-old/${args[2]}.${args[3] === 18 ? '8mp2' : '8xpy2'}`;
    return 0;
  } };
  assert.deepEqual(await transport.inspect({ name: 'CVPACK', type: 18 }),
    { name: 'CVPACK', type: 18, compiled: true, bytes: body.length, sha256: await sha256(body) });
  assert.deepEqual(await transport.inspect({ name: 'CASEVO', type: 15 }),
    { name: 'CASEVO', type: 15, compiled: false, bytes: source.length, sha256: await digest(source) });
  assert.equal(await transport.inspect({ name: 'JUNK', type: 18 }), null);
  assert.deepEqual(calls.map(c => [c.name, c.types, c.args]), [
    ['calc_recv_var', ['number', 'string', 'string', 'number', 'string'], [9, '', 'CVPACK', 18, '/casevo-old']],
    ['calc_recv_var', ['number', 'string', 'string', 'number', 'string'], [9, '', 'CASEVO', 15, '/casevo-old']],
    ['calc_recv_var', ['number', 'string', 'string', 'number', 'string'], [9, '', 'JUNK', 18, '/casevo-old']]]);
  assert.deepEqual(unlinked, ['/casevo-old/CVPACK.8mp2', '/casevo-old/CASEVO.8xpy2', '/casevo-old/JUNK.8mp2']);
  calls.length = 0;
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

// The published v1 package, from CAS_EVO_V1_PACKAGE or the pinned pages commit.
function v1Package() {
  if (process.env.CAS_EVO_V1_PACKAGE) return fs.readFileSync(process.env.CAS_EVO_V1_PACKAGE);
  try {
    return execFileSync('git', ['show', `${V1.pagesCommit}:${V1.path}`],
      { cwd: fileURLToPath(new URL('../..', import.meta.url)), maxBuffer: 16 << 20, stdio: ['ignore', 'pipe', 'ignore'] });
  } catch { return null; }
}
const V1_MISSING = 'published v1 package unavailable; set CAS_EVO_V1_PACKAGE or fetch the pages history';

test('the legacy v1 record is reproducible from the published v1 package', async t => {
  const bytes = v1Package();
  if (!bytes) return t.skip(V1_MISSING);
  const manifest = await buildLegacyManifest(bytes, await converter());
  assert.equal(formatManifest(manifest), fs.readFileSync(LEGACY_PATH, 'utf8'));
  // The installer recognizes every v1 object by its decoded content, and nothing else.
  const pkg = JSON.parse(Buffer.from(bytes).toString('utf8'));
  const legacy = validateLegacy(manifest);
  for (const file of pkg.files.slice(0, 12)) {
    const object = await describePythonObject(await converter(), decode(file.data));
    const entry = legacy.get(file.module);
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
  for (const [module, compiled, payload] of [['CASEVO', false, 'import cvui\n'], ['CVTEST', false, 'import cvui\nprint(1)\n'],
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
  assert.equal(result.completed, 4);
  assert.equal(removed.length, 235);
  assert.ok(!removed.includes('CVUI') && !removed.includes('CASEVO') && !removed.includes('CVTEST'));
  assert.deepEqual(result.preserved.map(p => [p.name, p.type, p.reason]), [['CVF00007', 15, 'different']]);
  assert.deepEqual(vars.map(v => `${v.name}/${v.type}`).sort(), ['CASEVO/15', 'CVENG/18', 'CVF00007/15', 'CVTEST/15', 'CVUI/18', 'NOTES/15']);
});
