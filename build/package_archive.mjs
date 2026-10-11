// Package with the same pinned TIVarsLib converter used by WebTILP.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import createConverter from '../website/vendor/TIVarsLib.js';
const root = path.resolve(process.argv[2] || 'dist/archive');
const output = path.resolve(process.argv[3] || 'dist/archive-transfer');
fs.mkdirSync(output, { recursive: true });
const meta = JSON.parse(fs.readFileSync(path.join(root, 'archive.json'), 'utf8'));
const converter = await createConverter();
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const result = { ...meta, files: [] };
for (const file of meta.files) {
  const bytes = fs.readFileSync(path.join(root, file.name));
  if (hash(bytes) !== file.sha256) throw new Error(`Compiler artifact changed: ${file.name}`);
  const variable = converter.TIVarFile.createNew('PythonAppVar', file.module, '84Evo');
  let converted;
  try {
    variable.setContentFromString(file.kind === 'source' ? bytes.toString('ascii') : JSON.stringify({
      python: { compiledModule: true, name: file.module, bodyHex: bytes.toString('hex') }
    }));
    if (file.kind === 'bytecode') variable.convertToEvoPythonFormat('8mp2');
    variable.setArchived(file.destination === 'archive');
    const temporary = variable.saveVarToFile('.', file.module);
    converted = Buffer.from(converter.FS.readFile(temporary));
    const roundtrip = converter.TIVarFile.loadFromFile(temporary);
    const options = new converter.options_t();
    try {
      options.set('prettify', 0);
      options.set('reindent', 0);
      const actual = JSON.parse(roundtrip.getReadableContent(options));
      if (actual.name !== file.module || actual.type !== (file.kind === 'bytecode' ? 18 : 15)
          || actual.python?.compiledModule !== (file.kind === 'bytecode')
          || actual.python?.bodyHex?.toLowerCase() !== bytes.toString('hex')) {
        throw new Error(`Converter round-trip changed ${file.module}`);
      }
    } finally { options.delete(); roundtrip.delete(); }
    converter.FS.unlink(temporary);
  } finally { variable.delete(); }
  const name = file.module + (file.kind === 'bytecode' ? '.8mp2' : '.8xpy2');
  fs.writeFileSync(path.join(output, name), converted);
  result.files.push({ ...file, name, bytes: converted.length, sha256: hash(converted), data: converted.toString('base64') });
}
result.totalBytes = result.files.reduce((sum, file) => sum + file.bytes, 0);
fs.writeFileSync(path.join(output, 'package.json'), JSON.stringify(result) + '\n');
console.log(`EVO transfer package: ${result.files.length} files, ${result.totalBytes} bytes`);
