// SPDX-License-Identifier: GPL-2.0-or-later
export const ARCHIVE = 3;
export const PYTHON_TYPES = new Set([15, 18]);
export const LAUNCHERS = ['CAS'];
// The records of earlier releases served beside the package (build/legacy_manifest.mjs).
export const LEGACY = ['legacy-v1.json', 'legacy-packs-v1.json', 'legacy-mathprint-da7f036.json',
  'legacy-mathprint-1b94211.json'];
const NAME = /^[A-Z][A-Z0-9]{0,7}$/;
const HASH = /^[a-f0-9]{64}$/;
export const decode = text => Uint8Array.from(atob(text), c => c.charCodeAt(0));
export const hex = bytes => [...bytes].map(n => n.toString(16).padStart(2, '0')).join('');
export const sha256 = async bytes => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));

export async function validatePackage(pkg, launchers = LAUNCHERS) {
  if (pkg?.schema !== 2 || pkg.runtimeCompilation !== false || !Array.isArray(pkg.files) || !pkg.files.length || pkg.files.length > 1024) {
    throw new Error('This installer has an invalid package. Reload the page to get a fresh copy.');
  }
  const names = new Set();
  let total = 0;
  for (const file of pkg.files) {
    // Any valid device name may be a library; only the launchers go to RAM.
    const launcher = launchers.includes(file?.module);
    const extension = launcher ? '.8xpy2' : '.8mp2';
    if (!NAME.test(file?.module) || file.name !== file.module + extension
        || names.has(file.module) || typeof file.data !== 'string'
        || (file.sourceSha256 !== undefined && !HASH.test(file.sourceSha256))
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
  if (!launchers.every(name => names.has(name)) || total !== pkg.totalBytes || total > 3500000) {
    throw new Error('The calculator package is incomplete or too large. Nothing was sent.');
  }
  return pkg;
}

// The records of earlier releases: what each of their calculator objects contains.
// sha256 is the decoded module body (compiled) or source text (launchers);
// sourceSha256 is the source companion the earlier installer recognized.
// One manifest or a list of them; the result maps each module to its records.
export function validateLegacy(manifests) {
  const invalid = () => new Error('This installer has an invalid record of earlier MicroCAS files. Reload the page to get a fresh copy.');
  const list = Array.isArray(manifests) ? manifests : [manifests];
  if (!list.length || list.length > 16) throw invalid();
  const modules = new Map();
  for (const manifest of list) {
    if (manifest?.schema !== 1 || typeof manifest.release !== 'string' || !Array.isArray(manifest.files)
        || !manifest.files.length || manifest.files.length > 1024) throw invalid();
    const seen = new Set();
    for (const entry of manifest.files) {
      const compiled = entry?.type === 18;
      if (!NAME.test(entry?.module) || seen.has(entry.module) || !PYTHON_TYPES.has(entry.type)
          || entry.location !== (compiled ? 'archive' : 'ram') || !HASH.test(entry.sha256)
          || (entry.sourceSha256 !== undefined && !HASH.test(entry.sourceSha256))) throw invalid();
      seen.add(entry.module);
      if (!modules.has(entry.module)) modules.set(entry.module, []);
      modules.get(entry.module).push(entry);
    }
  }
  return modules;
}

export function installationOrder(files) {
  // The launcher arrives last, after all its dependencies.
  return [...files].sort((a, b) => {
    const rank = name => name === 'CAS' ? 1 : 0;
    return rank(a.module) - rank(b.module) || a.name.localeCompare(b.name, 'en');
  });
}

export const calculatorType = (file, moduleType = 18) => file.destination === 'ram' ? 15 : moduleType;

export function checkInstalled(files, listing, moduleType = 18) {
  if (!Array.isArray(listing?.vars)) throw new Error('The calculator did not return a file list. Reconnect and try again.');
  return files.filter(file => !listing.vars.some(entry =>
    entry.name === file.module && entry.type === calculatorType(file, moduleType)
    && entry.attr === (file.destination === 'ram' ? 0 : ARCHIVE)));
}

export function requiredSpace(files, listing, moduleType = 18) {
  // Credit only existing archived objects that the send replaces, not RAM copies
  // or deletions that have not happened yet. Keep room for the largest in-flight
  // replacement plus VAT/flash bookkeeping.
  const objects = files.filter(file => file.destination === 'archive').map(file => {
    const existing = listing.vars?.find(entry => entry.name === file.module
      && entry.type === moduleType && entry.attr === ARCHIVE);
    const bytes = file.bytes + 64;
    const credit = Number.isFinite(existing?.size) ? Math.max(0, existing.size) : 0;
    return { bytes, additional: Math.max(0, bytes - credit) };
  });
  return objects.reduce((sum, item) => sum + item.additional, 0)
    + Math.max(...objects.map(item => item.bytes), 0) + 16384;
}

// Content fingerprints that prove a calculator object came from MicroCAS:
// the current package, an earlier release, or a source companion either recorded.
export function knownObjects(pkg, digests, legacy) {
  const known = new Map();
  const add = (name, compiled, digest, origin) => {
    if (!digest) return;
    if (!known.has(name)) known.set(name, []);
    known.get(name).push({ compiled, sha256: digest, origin });
  };
  for (const file of pkg.files) {
    add(file.module, file.destination === 'archive', digests.get(file.module), 'current');
    add(file.module, false, file.sourceSha256, 'current source');
  }
  for (const entries of legacy.values()) {
    for (const entry of entries) {
      add(entry.module, entry.type === 18, entry.sha256, 'earlier');
      add(entry.module, false, entry.sourceSha256, 'earlier source');
    }
  }
  return known;
}

export function identify(entry, object, known) {
  if (!object || object.name !== entry.name) return null;
  return (known.get(entry.name) || []).find(item =>
    item.compiled === object.compiled && item.sha256 === object.sha256) || null;
}

// Classify listed Python objects that carry a MicroCAS name. Same-slot objects are
// overwritten by the send; everything else is a leftover to remove or preserve.
export function cleanupPlan(pkg, legacy, listing, moduleType = 18) {
  const current = new Map(pkg.files.map(file => [file.module, file]));
  const replaced = [], leftovers = [];
  for (const entry of listing.vars) {
    if (!PYTHON_TYPES.has(entry.type) || !(legacy.has(entry.name) || current.has(entry.name))) continue;
    const file = current.get(entry.name);
    if (file && entry.type === calculatorType(file, moduleType)) replaced.push(entry);
    else leftovers.push(entry);
  }
  return { replaced, leftovers };
}

// A RAM source with a library's name would be imported instead of the library.
const shadows = (entry, pkg) => entry.type === 15 && entry.attr === 0
  && pkg.files.some(file => file.module === entry.name && file.destination === 'archive');

const keep = (entry, object) => ({ name: entry.name, type: entry.type, attr: entry.attr,
  reason: !object || object.unreadable ? 'unreadable' : 'different', ...(object?.detail ? { detail: object.detail } : {}) });

const describeList = items => {
  const names = items.map(item => item.name);
  return names.length > 4 ? `${names.slice(0, 4).join(', ')} and ${names.length - 4} more` : names.join(', ');
};

export class Installer {
  constructor(transport, onChange = () => {}) {
    this.transport = transport;
    this.onChange = onChange;
    this.busy = false;
    this.stopRequested = false;
    this.completed = new Set();
  }

  stop() { this.stopRequested = true; }

  async inspect(entry, progress) {
    this.onChange({ phase: 'inspecting', file: entry.name, ...progress, completed: 0 });
    try {
      return await this.transport.inspect(entry);
    } catch (error) {
      // A lost connection ends the run. A file that cannot be read is not ours to touch.
      if (this.transport.dead) throw error;
      return { unreadable: true, detail: error?.message || String(error) };
    }
  }

  async install(pkg, legacyManifest) {
    if (this.busy) throw new Error('An installation is already running.');
    this.busy = true;
    this.stopRequested = false;
    this.completed.clear();
    const removed = [], preserved = [];
    const report = extra => ({ removed: [...removed], preserved: [...preserved], ...extra });
    const stopped = () => {
      this.onChange(report({ phase: 'stopped', completed: this.completed.size }));
      return report({ stopped: true, completed: this.completed.size });
    };
    try {
      // Never trust UI state as an integrity or destination check.
      await validatePackage(pkg);
      const legacy = validateLegacy(legacyManifest);
      const digests = new Map();
      for (const file of pkg.files) {
        // Fingerprint our own objects exactly as they will read back from the calculator.
        const object = await this.transport.describe(decode(file.data));
        const compiled = file.destination === 'archive';
        if (object?.name !== file.module || object.compiled !== compiled || object.type !== (compiled ? 18 : 15)) {
          throw new Error(`${file.name} does not contain the module its manifest names. Reload before connecting.`);
        }
        digests.set(file.module, object.sha256);
      }
      const known = knownObjects(pkg, digests, legacy);
      this.onChange({ phase: 'checking', completed: 0 });
      const listing = await this.transport.list();
      if (!Array.isArray(listing?.vars)) throw new Error('The calculator did not return a file list. Reconnect and try again.');
      const moduleType = this.transport.moduleType ?? 18;
      const free = listing.memory?.flash_free;
      if (!listing.memory?.ok || !Number.isFinite(free) || free === 0xffffffff) {
        throw new Error('Archive space could not be read. Reconnect the calculator and try again.');
      }
      const { replaced, leftovers } = cleanupPlan(pkg, legacy, listing, moduleType);
      const required = requiredSpace(pkg.files, listing, moduleType);
      // Only an upper bound before contents are checked; the real check follows cleanup.
      const reclaimable = leftovers.filter(entry => entry.attr === ARCHIVE)
        .reduce((sum, entry) => sum + Math.max(0, Number(entry.size) || 0), 0);
      if (free + reclaimable < required) {
        throw new Error(`Archive needs about ${Math.ceil(required / 1024)} KB free; the calculator reports ${Math.floor(free / 1024)} KB. Free some archive space, then retry.`);
      }

      // 1. Read every object the send would overwrite or that would shadow a
      //    library. Anything unproven stops the run before any change.
      const blockers = [], queued = [];
      const current = new Set(pkg.files.map(file => file.module));
      const first = [...replaced, ...leftovers.filter(entry => current.has(entry.name))];
      for (const [index, entry] of first.entries()) {
        if (this.stopRequested) return stopped();
        const object = await this.inspect(entry, { index: index + 1, total: first.length });
        const match = identify(entry, object, known);
        if (replaced.includes(entry)) {
          if (!match) blockers.push(entry);
        } else if (match) queued.push(entry);
        else if (shadows(entry, pkg)) blockers.push(entry);
        else preserved.push(keep(entry, object));
      }
      if (blockers.length) {
        throw new Error(`${describeList(blockers)} on the calculator could not be confirmed as ${blockers.length === 1 ? 'a MicroCAS file' : 'MicroCAS files'}, so nothing was changed. Back up and delete ${blockers.length === 1 ? 'it' : 'them'} with TI Connect Evo, then install again.`);
      }

      // 2. Remove earlier MicroCAS objects the new package does not replace, one
      //    exact content match at a time. Modified or unreadable files stay.
      const rest = leftovers.filter(entry => !current.has(entry.name));
      const total = queued.length + rest.length;
      const remove = async (entry, index) => {
        if (this.stopRequested) return false;
        this.onChange({ phase: 'removing', file: entry.name, index, total, completed: 0 });
        await this.transport.remove(entry);
        removed.push({ name: entry.name, type: entry.type, size: entry.size });
        this.onChange({ phase: 'removed', file: entry.name, index, total, completed: 0 });
        return true;
      };
      for (const [index, entry] of queued.entries()) if (!await remove(entry, index + 1)) return stopped();
      for (const [offset, entry] of rest.entries()) {
        if (this.stopRequested) return stopped();
        const index = queued.length + offset + 1;
        const object = await this.inspect(entry, { index, total });
        if (identify(entry, object, known)) {
          if (!await remove(entry, index)) return stopped();
        } else {
          preserved.push(keep(entry, object));
        }
      }
      if (removed.length || preserved.length) this.onChange(report({ phase: 'cleaned', completed: 0 }));
      if (this.stopRequested) return stopped();

      // 3. Space is credited for deletions only after the calculator confirms them.
      const afterCleanup = await this.transport.list();
      if (!Array.isArray(afterCleanup?.vars)) throw new Error('The calculator did not return a file list. Reconnect and try again.');
      const lingering = removed.find(item => afterCleanup.vars.some(entry => entry.name === item.name && entry.type === item.type));
      if (lingering) throw new Error(`${lingering.name} could not be confirmed as removed. Reconnect and install again.`);
      const freeNow = afterCleanup.memory?.flash_free;
      if (!afterCleanup.memory?.ok || !Number.isFinite(freeNow) || freeNow === 0xffffffff) {
        throw new Error('Archive space could not be read. Reconnect the calculator and try again.');
      }
      const requiredNow = requiredSpace(pkg.files, afterCleanup, moduleType);
      if (freeNow < requiredNow) {
        throw new Error(`Archive needs about ${Math.ceil(requiredNow / 1024)} KB free; the calculator reports ${Math.floor(freeNow / 1024)} KB${removed.length ? ` after removing ${removed.length} earlier MicroCAS file(s)` : ''}. Free some archive space, then install again.`);
      }
      const ramNeeded = pkg.files.filter(file => file.destination === 'ram')
        .reduce((sum, file) => sum + file.bytes + 64, 4096);
      if (!Number.isFinite(afterCleanup.memory.ram_free)
          || afterCleanup.memory.ram_free === 0xffffffff || afterCleanup.memory.ram_free < ramNeeded) {
        throw new Error(`The launcher needs about ${Math.ceil(ramNeeded / 1024)} KB free in RAM. Free some RAM on the calculator, then retry.`);
      }
      for (const file of installationOrder(pkg.files)) {
        if (this.stopRequested) return stopped();
        this.onChange({ phase: 'sending', file: file.name, completed: this.completed.size });
        await this.transport.send(file);
        this.completed.add(file.name);
        this.onChange({ phase: 'sent', file: file.name, completed: this.completed.size });
      }
      this.onChange({ phase: 'verifying', completed: this.completed.size });
      const finalListing = await this.transport.list();
      const missing = checkInstalled(pkg.files, finalListing, moduleType);
      if (missing.length) {
        throw new Error(`${missing.length} file(s) could not be confirmed in their required location, starting with ${missing[0].name}. Reconnect and install again.`);
      }
      if (finalListing.vars.some(entry => shadows(entry, pkg))) {
        throw new Error('Some old MicroCAS source companions are still in RAM. Move them to archive before opening Python.');
      }
      this.onChange(report({ phase: 'complete', completed: this.completed.size }));
      return report({ stopped: false, completed: this.completed.size });
    } catch (error) {
      this.onChange(report({ phase: 'error', completed: this.completed.size, error }));
      throw error;
    } finally {
      this.busy = false;
    }
  }
}
