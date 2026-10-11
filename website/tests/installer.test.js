import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { Installer, validatePackage, installationOrder, checkInstalled, sha256 } from '../installer.js';
import { WebTilpTransport } from '../transport.js';
import createConverter from '../vendor/TIVarsLib.js';

async function fixture() {
  const files = [];
  for (const [module, destination] of [['CASEVO', 'ram'], ['CVNODE', 'archive'], ['CVTEST', 'ram']]) {
    const data = new TextEncoder().encode(module);
    files.push({ module, destination, name: module + (destination === 'ram' ? '.8xpy2' : '.8mp2'),
      kind: destination === 'ram' ? 'source' : 'bytecode', data: btoa(module), bytes: data.length,
      sha256: await sha256(data), sourceSha256: '0'.repeat(64) });
  }
  return { schema: 2, runtimeCompilation: false, files, totalBytes: files.reduce((s, f) => s + f.bytes, 0) };
}

function fakeTransport() {
  const vars = [], sent = [];
  return { vars, sent, moduleType: 18,
    async list() { return { vars: structuredClone(vars), memory: { ok: true, flash_free: 3000000, ram_free: 100000 } }; },
    async send(file) {
      sent.push(file);
      vars.push({ name: file.module, type: file.destination === 'ram' ? 15 : 18, attr: file.destination === 'ram' ? 0 : 3 });
    },
    async archiveLegacySource(file, old) { vars.find(v => v.name === old.name && v.type === 15).attr = 3; }
  };
}

test('corrupt packages and wrong destinations fail before any device access', async () => {
  for (const mutation of [p => p.files[1].data = btoa('wrong'), p => p.files[1].destination = 'ram', p => p.files.push(p.files[0])]) {
    const pkg = await fixture(); mutation(pkg);
    const installer = new Installer({ list() { assert.fail('device was accessed'); } });
    await assert.rejects(installer.install(pkg));
    assert.equal(installer.busy, false);
  }
});

test('libraries install first, launchers last, and every destination is verified', async () => {
  const pkg = await fixture(), transport = fakeTransport(), events = [];
  const result = await new Installer(transport, e => events.push(e)).install(pkg);
  assert.deepEqual(transport.sent.map(f => f.module), ['CVNODE', 'CVTEST', 'CASEVO']);
  assert.equal(result.completed, 3);
  assert.equal(events.at(-1).phase, 'complete');
  assert.deepEqual(checkInstalled(pkg.files, await transport.list()), []);
});

test('old source companions leave RAM before the compiled package arrives', async () => {
  const pkg = await fixture(), transport = fakeTransport(), events = [];
  transport.vars.push({ name: 'CVNODE', type: 15, attr: 0, size: 1000 });
  await new Installer(transport, e => events.push(e.phase)).install(pkg);
  assert.ok(events.indexOf('migrating') < events.indexOf('sending'));
  assert.equal(transport.vars[0].attr, 3);
});

test('low archive/RAM capacity rejects before sending launchers', async () => {
  const pkg = await fixture();
  for (const memory of [{ ok: true, flash_free: 0, ram_free: 100000 }, { ok: true, flash_free: 3000000, ram_free: 0 }]) {
    const transport = fakeTransport();
    transport.list = async () => ({ vars: [], memory });
    await assert.rejects(new Installer(transport).install(pkg), /free|RAM/);
    assert.equal(transport.sent.length, 0);
  }
});

test('stop waits for the current file and never starts the next', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  let installer;
  installer = new Installer(transport, e => { if (e.phase === 'sending') installer.stop(); });
  const result = await installer.install(pkg);
  assert.deepEqual(result, { stopped: true, completed: 1 });
  assert.equal(transport.sent.length, 1);
});

test('acknowledged transfer with the wrong location is not reported as installed', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.send = async file => transport.vars.push({ name: file.module, type: 15, attr: 0 });
  await assert.rejects(new Installer(transport).install(pkg), /could not be confirmed/);
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
  assert.equal(pkg.files.length, 238);
  assert.equal(pkg.files.filter(f => f.destination === 'ram').length, 2);
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

test('migration reads actual EVO source objects and archives only exact source matches', async () => {
  const converter = await createConverter();
  const source = 'value=42\nprint(value)\n';
  const variable = converter.TIVarFile.createNew('PythonAppVar', 'CVNODE', '84Evo');
  let data;
  try {
    variable.setContentFromString(source);
    const path = variable.saveVarToFile('.', 'CVNODE');
    data = converter.FS.readFile(path);
    converter.FS.unlink(path);
  } finally { variable.delete(); }
  const sent = [];
  const transport = new WebTilpTransport({ gap: 0, converterFactory: async () => converter });
  transport.handle = 1;
  transport.module = { FS: {
    analyzePath: () => ({ exists: true }),
    readFile: path => path === '/last_recv_path.txt' ? '/casevo-old/CVNODE.8xpy2' : data,
    unlink() {}
  }, ccall(name, type, types, args) { if (name === 'send_file_custom') sent.push(args); return 0; } };
  const file = { sourceSha256: await sha256(new TextEncoder().encode(source)) };
  await transport.archiveLegacySource(file, { name: 'CVNODE' });
  assert.equal(sent.length, 1);
  assert.equal(sent[0][3], 1);
  file.sourceSha256 = '0'.repeat(64);
  await assert.rejects(transport.archiveLegacySource(file, { name: 'CVNODE' }), /contents have been preserved/);
  assert.equal(sent.length, 1);
});

test('missing directory listing and interrupted migration do not send the package', async () => {
  const pkg = await fixture(), transport = fakeTransport();
  transport.list = async () => ({ memory: { ok: true, flash_free: 3000000, ram_free: 100000 } });
  await assert.rejects(new Installer(transport).install(pkg), /file list/);
  assert.equal(transport.sent.length, 0);
  const migrating = fakeTransport();
  migrating.vars.push({ name: 'CVNODE', type: 15, attr: 0 });
  const installer = new Installer(migrating, event => { if (event.phase === 'migrating') installer.stop(); });
  assert.deepEqual(await installer.install(pkg), { stopped: true, completed: 0 });
  assert.equal(migrating.sent.length, 0);
});
