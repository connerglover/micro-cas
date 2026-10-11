// SPDX-License-Identifier: GPL-2.0-or-later
export const ARCHIVE = 3;
export const PYTHON_TYPES = new Set([15, 18]);
export const decode = text => Uint8Array.from(atob(text), c => c.charCodeAt(0));
export const hex = bytes => [...bytes].map(n => n.toString(16).padStart(2, '0')).join('');
export const sha256 = async bytes => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));

export async function validatePackage(pkg) {
  if (pkg.schema !== 2 || pkg.runtimeCompilation !== false || !Array.isArray(pkg.files) || !pkg.files.length || pkg.files.length > 1024) {
    throw new Error('This installer has an invalid package. Reload the page to get a fresh copy.');
  }
  const names = new Set();
  let total = 0;
  for (const file of pkg.files) {
    const launcher = ['CASEVO', 'CVTEST'].includes(file.module);
    const extension = launcher ? '.8xpy2' : '.8mp2';
    if (!/^[A-Z][A-Z0-9]{0,7}$/.test(file.module) || file.name !== file.module + extension
        || names.has(file.module) || typeof file.data !== 'string'
        || !/^[a-f0-9]{64}$/.test(file.sourceSha256)
        || file.destination !== (launcher ? 'ram' : 'archive')
        || file.kind !== (launcher ? 'source' : 'bytecode')) {
      throw new Error('The package contains an invalid or repeated filename. Nothing was sent.');
    }
    const data = decode(file.data);
    if (data.length !== file.bytes || data.length > 65535
        || await sha256(data) !== file.sha256) {
      throw new Error(`The integrity check failed for ${file.name}. Reload before connecting.`);
    }
    names.add(file.module);
    total += data.length;
  }
  if (!names.has('CASEVO') || !names.has('CVTEST') || total !== pkg.totalBytes || total > 3500000) {
    throw new Error('The calculator package is incomplete or too large. Nothing was sent.');
  }
  return pkg;
}

export function installationOrder(files) {
  // Entrypoints arrive last, after all their dependencies.
  return [...files].sort((a, b) => {
    const rank = name => name === 'CASEVO' ? 2 : name === 'CVTEST' ? 1 : 0;
    return rank(a.module) - rank(b.module) || a.name.localeCompare(b.name, 'en');
  });
}

export function checkInstalled(files, listing, moduleType = 18) {
  if (!Array.isArray(listing?.vars)) throw new Error('The calculator did not return a file list. Reconnect and try again.');
  return files.filter(file => !listing.vars.some(entry =>
    entry.name === file.module && entry.type === (file.destination === 'ram' ? 15 : moduleType)
    && entry.attr === (file.destination === 'ram' ? 0 : ARCHIVE)));
}

export function requiredSpace(files, listing) {
  // Credit only existing archived Python objects with matching names, not RAM copies.
  // Keep room for the largest in-flight replacement plus VAT/flash bookkeeping.
  const objects = files.filter(file => file.destination === 'archive').map(file => {
    const existing = listing.vars?.find(entry => entry.name === file.module
      && entry.type === 18 && entry.attr === ARCHIVE);
    const bytes = file.bytes + 64;
    const credit = Number.isFinite(existing?.size) ? Math.max(0, existing.size) : 0;
    return { bytes, additional: Math.max(0, bytes - credit) };
  });
  const oldRam = listing.vars?.filter(entry => entry.type === 15 && entry.attr === 0
    && files.some(file => file.module === entry.name && file.destination === 'archive')) || [];
  return oldRam.reduce((sum, entry) => sum + Math.max(0, Number(entry.size) || 0) + 64, 0)
    + objects.reduce((sum, item) => sum + item.additional, 0)
    + Math.max(...objects.map(item => item.bytes), 0) + 16384;
}

export class Installer {
  constructor(transport, onChange = () => {}) {
    this.transport = transport;
    this.onChange = onChange;
    this.busy = false;
    this.stopRequested = false;
    this.completed = new Set();
  }

  stop() { this.stopRequested = true; }

  async install(pkg) {
    if (this.busy) throw new Error('An installation is already running.');
    this.busy = true;
    this.stopRequested = false;
    this.completed.clear();
    try {
      // Never trust UI state as an integrity or destination check.
      await validatePackage(pkg);
      this.onChange({ phase: 'checking', completed: 0 });
      const listing = await this.transport.list();
      if (!Array.isArray(listing?.vars)) throw new Error('The calculator did not return a file list. Reconnect and try again.');
      const required = requiredSpace(pkg.files, listing);
      const free = listing.memory?.flash_free;
      if (!listing.memory?.ok || !Number.isFinite(free) || free === 0xffffffff) {
        throw new Error('Archive space could not be read. Reconnect the calculator and try again.');
      }
      if (free < required) {
        throw new Error(`Archive needs about ${Math.ceil(required / 1024)} KB free; the calculator reports ${Math.floor(free / 1024)} KB. Free some archive space, then retry.`);
      }
      // Old source companions would still synchronize into Python and shadow the
      // compiled modules. Move only hash-matched cas-evo sources out of RAM.
      for (const file of pkg.files.filter(item => item.destination === 'archive')) {
        if (this.stopRequested) break;
        const old = listing.vars.find(entry => entry.name === file.module && entry.type === 15 && entry.attr === 0);
        if (old) {
          this.onChange({ phase: 'migrating', file: file.module, completed: 0 });
          await this.transport.archiveLegacySource(file, old);
        }
      }
      if (this.stopRequested) {
        this.onChange({ phase: 'stopped', completed: 0 });
        return { stopped: true, completed: 0 };
      }
      const afterMigration = await this.transport.list();
      const ramNeeded = pkg.files.filter(file => file.destination === 'ram')
        .reduce((sum, file) => sum + file.bytes + 64, 4096);
      if (!afterMigration.memory?.ok || !Number.isFinite(afterMigration.memory.ram_free)
          || afterMigration.memory.ram_free === 0xffffffff || afterMigration.memory.ram_free < ramNeeded) {
        throw new Error(`The launchers need about ${Math.ceil(ramNeeded / 1024)} KB free in RAM. Free some RAM on the calculator, then retry.`);
      }
      for (const file of installationOrder(pkg.files)) {
        if (this.stopRequested) {
          this.onChange({ phase: 'stopped', completed: this.completed.size });
          return { stopped: true, completed: this.completed.size };
        }
        this.onChange({ phase: 'sending', file: file.name, completed: this.completed.size });
        await this.transport.send(file);
        this.completed.add(file.name);
        this.onChange({ phase: 'sent', file: file.name, completed: this.completed.size });
      }
      this.onChange({ phase: 'verifying', completed: this.completed.size });
      const finalListing = await this.transport.list();
      const missing = checkInstalled(pkg.files, finalListing, this.transport.moduleType);
      if (missing.length) {
        throw new Error(`${missing.length} file(s) could not be confirmed in their required location, starting with ${missing[0].name}. Reconnect and install again.`);
      }
      if (finalListing.vars.some(entry => entry.type === 15 && entry.attr === 0
          && pkg.files.some(file => file.module === entry.name && file.destination === 'archive'))) {
        throw new Error('Some old cas-evo source companions are still in RAM. Move them to archive before opening Python.');
      }
      this.onChange({ phase: 'complete', completed: this.completed.size });
      return { stopped: false, completed: this.completed.size };
    } catch (error) {
      this.onChange({ phase: 'error', completed: this.completed.size, error });
      throw error;
    } finally {
      this.busy = false;
    }
  }
}
