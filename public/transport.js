// SPDX-License-Identifier: GPL-2.0-or-later
// Uses the unmodified, pinned WebTILP runtime. See vendor/PROVENANCE.md.
import { decode, sha256, PYTHON_TYPES } from './installer.js';

const fromHex = text => {
  if (typeof text !== 'string' || text.length % 2 || /[^0-9a-f]/i.test(text)) return null;
  const bytes = new Uint8Array(text.length / 2);
  for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(text.substr(i * 2, 2), 16);
  return bytes;
};

// Decode an EVO Python object with the pinned TIVarsLib and fingerprint what the
// calculator stores: the compiled module body, or the source text of a script.
// build/legacy_manifest.mjs records earlier releases with this definition.
export async function describePythonObject(converter, bytes) {
  const path = '/casevo-object.8xpy2';
  converter.FS.writeFile(path, bytes);
  let variable, options, decoded;
  try {
    variable = converter.TIVarFile.loadFromFile(path);
    options = new converter.options_t();
    options.set('prettify', 0);
    options.set('reindent', 0);
    decoded = JSON.parse(variable.getReadableContent(options));
  } finally {
    options?.delete();
    variable?.delete();
    converter.FS.unlink(path);
  }
  const python = decoded.python || {};
  const compiled = python.compiledModule === true;
  const content = compiled ? fromHex(python.bodyHex)
    : typeof python.code === 'string' ? new TextEncoder().encode(python.code) : null;
  if (!content || typeof decoded.name !== 'string' || !PYTHON_TYPES.has(decoded.type)) {
    throw new Error('Not a readable Python object.');
  }
  return { name: decoded.name, type: decoded.type, compiled, bytes: content.length, sha256: await sha256(content) };
}

export class WebTilpTransport {
  constructor({ factory = globalThis.TILibsModule,
    log = () => {}, gap = 100, timeout = 90000 } = {}) {
    this.factory = factory;
    this.log = log;
    this.gap = gap;
    this.timeout = timeout;
    this.tail = Promise.resolve();
    this.handle = 0;
    this.dead = false;
    this.connected = false;
  }

  call(name, resultType = 'number', argTypes = [], args = []) {
    const operation = this.tail.then(async () => {
      if (this.dead) throw new Error('The connection stopped responding. Reload this page and reconnect.');
      if (this.gap) await new Promise(resolve => setTimeout(resolve, this.gap));
      let timer;
      const underlying = Promise.resolve().then(() => this.module.ccall(name, resultType, argTypes, args, { async: true }));
      try {
        return await Promise.race([underlying, new Promise((_, reject) => {
          timer = setTimeout(() => {
            // A JS timeout does not cancel Asyncify. Retire this instance permanently.
            this.dead = true;
            this.connected = false;
            reject(new Error('The calculator stopped responding. Reload this page, reconnect, and install again.'));
          }, this.timeout);
        })]);
      } catch (error) {
        if (error instanceof WebAssembly.RuntimeError) this.dead = true;
        throw error;
      } finally { clearTimeout(timer); }
    });
    this.tail = operation.catch(() => {});
    return operation;
  }

  check(result, action) {
    if (result !== 0) {
      const reason = this.module.ccall('get_error_message', 'string', ['number'], [result]);
      throw new Error(`${action}: ${reason || `calculator error ${result}`}. Close TI Connect and other calculator tabs, then reconnect and retry.`);
    }
  }

  async connect(port) {
    if (this.dead) throw new Error('Reload this page before reconnecting.');
    const info = port.getInfo();
    if (info.usbVendorId !== 0x0451 || info.usbProductId !== 0xe018) {
      throw new Error('Select a TI-84 EVO serial port. Other calculators are not supported by this installer.');
    }
    if (!this.module) {
      this.module = await this.factory({ print: this.log, printErr: this.log });
      // ticalcs_library_init returns its positive reference count, not an error code.
      const initialized = await this.call('init');
      if (!(initialized > 0)) throw new Error('WebTILP could not initialize. Reload this page and try again.');
    }
    this.port = port;
    this.module.__ticablesWebSerial = { kind: 1, port };
    this.module._set_cable_model(5); // DirectLink, with EVO CDC serial bound above.
    this.module._set_force_cable(1);
    this.module._set_calc_model(48); // EVO; the version query resolves EVO-T.
    this.module._set_force_calc(0);
    this.module._set_cable_timeout(250); // Archive writes may trigger flash collection.
    this.module._set_cable_delay(10);
    try {
      this.handle = await this.call('create_handle');
      if (!this.handle) throw new Error('WebTILP could not create a connection. Reconnect and try again.');
      this.check(await this.call('open_cable', 'number', ['number'], [this.handle]), 'Opening the calculator');
      const details = await this.call('calc_get_info_string', 'string', ['number'], [this.handle]);
      const model = this.module._get_calc_model_id();
      if (!details || ![48, 49].includes(model)) {
        throw new Error('The device could not be identified as a TI-84 EVO or EVO-T. Nothing was sent.');
      }
      this.connected = true;
      this.moduleType = /OS version[^\n]*\b7\.0(?:\.|\b)/i.test(details) ? 15 : 18;
      return { model, details, listing: await this.list() };
    } catch (error) {
      await this.disconnect().catch(() => {});
      throw error;
    }
  }

  async list() {
    if (!this.connected) throw new Error('Connect the calculator before installing.');
    const path = '/casevo-dir.json';
    this.check(await this.call('calc_dirlist_json', 'number', ['number', 'string'], [this.handle, path]), 'Reading archive');
    try {
      return JSON.parse(this.module.FS.readFile(path, { encoding: 'utf8' }));
    } finally { this.module.FS.unlink(path); }
  }

  // WebTILP: int calc_del_var(CableHandle*, const char* folder, const char* name, uint8_t type).
  // EVO variables have no folder; the calculator matches by name and type.
  async remove(entry) {
    if (!this.connected) throw new Error('The calculator disconnected. Reconnect and install again.');
    this.check(await this.call('calc_del_var', 'number',
      ['number', 'string', 'string', 'number'],
      [this.handle, '', entry.name, entry.type]), `Removing old ${entry.name}`);
  }

  async send(file) {
    if (!this.connected) throw new Error('The calculator disconnected. Reconnect and install again.');
    const data = decode(file.data);
    const path = `/${file.name}`;
    this.module.FS.writeFile(path, data);
    try {
      // Compiled companions go to archive; only the CAS launcher source goes to RAM.
      this.check(await this.call('send_file_custom', 'number',
        ['number', 'string', 'string', 'number', 'number'],
        [this.handle, path, '', file.destination === 'archive' ? 1 : 0, 0]), `Sending ${file.name}`);
    } finally {
      // A timed-out WASM call may still own this path until the page is reloaded.
      if (!this.dead) this.module.FS.unlink(path);
    }
  }

  async disconnect() {
    this.connected = false;
    if (this.handle && !this.dead) {
      this.check(await this.call('close_cable', 'number', ['number'], [this.handle]), 'Closing the connection');
      this.handle = 0;
    }
  }
}
