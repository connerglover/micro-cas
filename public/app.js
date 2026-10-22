// SPDX-License-Identifier: GPL-2.0-or-later
import { Installer, LEGACY, validatePackage, validateLegacy, sha256 } from './installer.js';
import { WebTilpTransport } from './transport.js';

const $ = id => document.getElementById(id);
const bytes = n => `${(n / 1024).toFixed(1)} KB`;
const states = new Map();
const cells = new Map();
const rows = new Map();
const logs = [];
let pkg, legacy, transport, installer, working = false, installed = false, supported = false;

function log(message) {
  // Keep a bounded local log. Device identifiers never leave the browser.
  logs.push(`${new Date().toLocaleTimeString()}  ${String(message)}`);
  if (logs.length > 150) logs.shift();
  $('log').textContent = logs.join('\n');
}

function notice(message = '') {
  $('notice').textContent = message;
  $('notice').hidden = !message;
}

function stage(index) {
  ['connect', 'install', 'open'].forEach((name, i) => {
    const node = $(`stage-${name}`);
    node.classList.toggle('current', i === index);
    node.classList.toggle('done', i < index);
    if (i === index) node.setAttribute('aria-current', 'step');
    else node.removeAttribute('aria-current');
  });
}

function controls() {
  const connected = transport?.connected;
  $('primary').disabled = working || !pkg || !supported || transport?.dead;
  $('primary-label').textContent = transport?.dead ? 'Reload to reconnect'
    : working ? (installer?.busy ? 'Installing…' : 'Connecting…')
      : connected ? (installed ? 'Install again' : 'Install MicroCAS') : 'Connect your EVO';
  $('stop').hidden = !installer?.busy;
  $('stop').disabled = !!installer?.stopRequested;
  $('disconnect').hidden = !connected || working;
  $('connection-dot').classList.toggle('connected', !!connected);
  $('launch-note').hidden = !installed;
}

function fileState(name, state) {
  states.set(name, state);
  const cell = cells.get(name), row = rows.get(name);
  if (cell) cell.className = `file-cell ${state}`;
  if (row) {
    const td = row.lastElementChild;
    td.dataset.state = state;
    td.textContent = ({ sending: 'Sending', sent: 'Sent', verified: 'Verified', failed: 'Retry needed' })[state] || 'Ready';
  }
}

function showPackage() {
  if (typeof pkg.release === 'string') $('package-version').textContent = `v${pkg.release}`;
  else if (typeof pkg.version === 'string') $('package-version').textContent = pkg.version;
  $('file-count').textContent = `${pkg.files.length} files`;
  $('source-size').textContent = bytes(pkg.totalBytes);
  $('ram-size').textContent = `${bytes(pkg.files.filter(file => file.destination === 'ram').reduce((sum, file) => sum + file.bytes, 0))} in RAM`;
  $('manifest-count').textContent = pkg.files.length;
  $('progress').max = pkg.files.length;
  $('progress-count').textContent = `0 / ${pkg.files.length}`;
  for (const file of pkg.files) {
    const cell = document.createElement('span');
    cell.className = 'file-cell';
    cell.title = `${file.name} · ${file.destination}`;
    cells.set(file.name, cell);
    $('file-map').append(cell);
    const row = document.createElement('tr');
    for (const value of [file.name, bytes(file.bytes), file.destination === 'ram' ? 'RAM' : 'Archive', 'Ready']) {
      const td = document.createElement('td');
      td.textContent = value;
      row.append(td);
    }
    rows.set(file.name, row);
    $('file-list').append(row);
  }
  $('integrity').textContent = 'SHA-256 verified';
  $('integrity').classList.add('verified');
  $('status-text').textContent = 'Package ready to install';
}

function cleanupSummary(event) {
  // Removed files are reported once per run, in one log line.
  const removed = event.removed || [];
  if (removed.length) log(`Removed ${removed.length} outdated MicroCAS file(s): ${removed.map(item => item.name).join(', ')}.`);
}

function onProgress(event) {
  $('progress').value = event.completed;
  $('progress-count').textContent = `${event.completed} / ${pkg.files.length}`;
  const statuses = {
    checking: 'Checking calculator storage',
    removing: 'Removing earlier MicroCAS files', removed: 'Removing earlier MicroCAS files',
    cleaned: 'Earlier MicroCAS files removed',
    sending: 'Installing MicroCAS', sent: 'Installing MicroCAS', verifying: 'Checking file locations',
    complete: 'Installation complete. File locations verified.', stopped: 'Stopped after the current file', error: 'Installation needs attention'
  };
  $('status-text').textContent = statuses[event.phase];
  if (event.file) $('current-file').textContent = event.total ? `${event.file} · ${event.index} of ${event.total}` : event.file;
  if (event.phase === 'sending') fileState(event.file, 'sending');
  if (event.phase === 'sent') fileState(event.file, 'sent');
  if (event.phase === 'complete') {
    installed = true;
    pkg.files.forEach(file => fileState(file.name, 'verified'));
    stage(2);
    $('current-file').textContent = 'Libraries in archive. Launchers in RAM.';
    $('action-note').textContent = 'Transfer complete. You can disconnect the USB cable.';
    cleanupSummary(event);
    log('Verified every file and its storage location. Calculator execution is the next check.');
  }
  if (event.phase === 'error') {
    for (const [name, state] of states) if (state === 'sending') fileState(name, 'failed');
    cleanupSummary(event);
  }
  if (event.phase === 'stopped') {
    $('current-file').textContent = 'Choose Install MicroCAS to retry the complete package.';
    $('action-note').textContent = 'The partial installation is not ready to run. Install again to finish.';
    cleanupSummary(event);
    const removed = (event.removed || []).length;
    log(`Stopped safely after ${event.completed} new file(s)${removed ? `; ${removed} earlier MicroCAS file(s) were removed` : ''}.`);
  }
  controls();
}

$('primary').addEventListener('click', async () => {
  if (working || !pkg || !supported) return;
  notice();
  working = true;
  controls();
  try {
    if (!transport?.connected) {
      // Request permission directly inside the gesture, before awaiting WASM.
      const port = await navigator.serial.requestPort({ filters: [{ usbVendorId: 0x0451, usbProductId: 0xe018 }] });
      transport ||= new WebTilpTransport({ log });
      $('status-text').textContent = 'Opening a connection to your EVO';
      const device = await transport.connect(port);
      installer = new Installer(transport, onProgress);
      log(device.details);
      $('device-name').textContent = device.model === 49 ? 'TI-84 EVO-T connected' : 'TI-84 EVO connected';
      $('archive-free').textContent = device.listing.memory?.ok ? `${bytes(device.listing.memory.flash_free)} free in archive` : '';
      $('status-text').textContent = 'Connected. Ready to install.';
      $('action-note').textContent = 'Libraries go to archive; CAS goes to RAM. Outdated MicroCAS files are deleted; the rest are replaced.';
      stage(1);
    } else {
      installed = false;
      $('stop').textContent = 'Stop after this file';
      states.clear();
      pkg.files.forEach(file => fileState(file.name, ''));
      stage(1);
      $('action-note').textContent = 'Keep the cable connected. Stop waits for the current file to finish.';
      await installer.install(pkg, legacy);
    }
  } catch (error) {
    const cancelled = error.name === 'NotFoundError';
    const message = cancelled ? 'Connection canceled. Choose Connect your EVO when you’re ready.' : error.message || String(error);
    notice(message);
    log(message);
    if (!transport?.connected) {
      $('device-name').textContent = 'No calculator connected';
      $('archive-free').textContent = '';
    }
    if (!installer?.busy && !cancelled) $('status-text').textContent = 'Connection or installation needs attention';
  } finally {
    working = false;
    controls();
  }
});

$('stop').addEventListener('click', () => {
  installer?.stop();
  $('stop').textContent = 'Stopping after this file…';
  controls();
});

$('disconnect').addEventListener('click', async () => {
  if (working) return;
  working = true;
  controls();
  try {
    await transport.disconnect();
    $('device-name').textContent = 'No calculator connected';
    $('archive-free').textContent = '';
    $('status-text').textContent = installed ? 'Installation complete; calculator disconnected' : 'Package ready to install';
    if (!installed) stage(0);
    log('Disconnected.');
  } catch (error) { notice(error.message); log(error.message); }
  finally { working = false; controls(); }
});

$('file-search').addEventListener('input', event => {
  const query = event.target.value.trim().toUpperCase();
  let count = 0;
  for (const [name, row] of rows) {
    row.hidden = !name.includes(query);
    if (!row.hidden) count++;
  }
  $('no-files').hidden = count !== 0;
});

$('copy-log').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(logs.join('\n'));
    $('copy-log').textContent = 'Copied';
  } catch { $('copy-log').textContent = 'Select and copy the details below'; }
});

navigator.serial?.addEventListener('disconnect', event => {
  if ((event.port || event.target) !== transport?.port) return;
  transport.connected = false;
  transport.dead = true;
  notice('The USB connection was lost. Reload this page, reconnect, and install again.');
  $('device-name').textContent = 'Calculator disconnected';
  log('USB disconnected. This connection instance cannot be reused.');
  controls();
});

window.addEventListener('beforeunload', event => {
  if (working) { event.preventDefault(); event.returnValue = ''; }
});

try {
  const [metaResponse, response] = await Promise.all(['./package-meta.json', './package.json']
    .map(url => fetch(url, { cache: 'no-store' })));
  if (!metaResponse.ok || !response.ok) throw new Error('The download package is unavailable. Reload the page and try again.');
  const [meta, data] = await Promise.all([metaResponse.json(), response.arrayBuffer()]);
  if (await sha256(data) !== meta.sha256) throw new Error('The package download was incomplete. Reload before connecting.');
  // The records of earlier releases, each pinned by the build (build/website.py).
  const records = await Promise.all(LEGACY.map(async name => {
    const reply = await fetch('./' + name, { cache: 'no-store' });
    if (!reply.ok) throw new Error('The download package is unavailable. Reload the page and try again.');
    const bytes = await reply.arrayBuffer();
    if (await sha256(bytes) !== meta.legacy?.[name]) throw new Error('The package download was incomplete. Reload before connecting.');
    return JSON.parse(new TextDecoder().decode(bytes));
  }));
  pkg = await validatePackage(JSON.parse(new TextDecoder().decode(data)));
  validateLegacy(records);
  legacy = records;
  showPackage();
  const isolated = await globalThis.isolationReady;
  supported = !!(isSecureContext && navigator.serial?.requestPort && isolated && globalThis.TILibsModule);
  if (!supported) {
    notice(!navigator.serial?.requestPort
      ? 'USB installation needs Chrome or Edge on a computer. You can download the ZIP on this browser.'
      : 'This page could not enable the browser isolation needed for USB transfer. Reload, or open the site directly in Chrome or Edge.');
    $('action-note').textContent = 'The ZIP and installation help remain available.';
  }
  log(`Verified ${pkg.files.length} transfer files; ${pkg.totalBytes} bytes. Libraries use MPY v5.3.`);
  for (const record of legacy) log(`Loaded the record of ${record.files.length} earlier MicroCAS ${record.release} names to remove.`);
} catch (error) {
  pkg = undefined;
  legacy = undefined;
  notice(error.message);
  $('status-text').textContent = 'Package could not be verified';
  $('integrity').textContent = 'Verification failed';
  log(error.message);
}
controls();
