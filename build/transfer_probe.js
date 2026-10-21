/* Run as an expression on https://connectevo.ti.com/ticevo/en/ after it loads.
 * Uses the actual converter only; does not request a calculator connection.
 * Optional global casSource holds the ASCII program to reproduce its rejection.
 * Optional global casFiles is an array of [filename, ASCII source] pairs from
 * the generated release.json files list; this checks the actual multi-file app.
 */
(() => {
  function convert(source, name) {
    const data = new TextEncoder().encode(source);
    const file = new TIFile({dispName: name, tokName: '',
      type: TIFile.fileTypeFromExtension('.py'), size: data.length,
      memory: 'RAM', contents: data});
    const status = TIConnect.convertPyToPyVar(file, name);
    return {name, sourceBytes: data.length, status, convertedBytes: file.contents.length};
  }
  const rows = [];
  for (const [name, limit] of [['A.py', 65516], ['CAS.py', 65514],
                              ['ABCDEFGH.py', 65509]]) {
    for (const extra of [0, 1]) {
      const n = limit + extra;
      for (const shape of ['one line', 'short lines']) {
        const source = shape === 'one line' ? '#' + 'x'.repeat(n - 2) + '\n'
          : 'x=1\n'.repeat(Math.floor(n / 4)) + '#'.repeat(n % 4);
        const row = {...convert(source, name), shape};
        const expected = extra ? TIConnect.transferStatuses.XFR_ERROR_NOMEM
          : TIConnect.transferStatuses.XFR_SUCCESS;
        if (row.status !== expected) throw new Error(JSON.stringify(row));
        rows.push(row);
      }
    }
  }
  const actual = typeof casSource === 'string' ? convert(casSource, 'CAS.py') : null;
  const files = typeof casFiles === 'undefined' ? [] : casFiles.map(([name, source]) => {
    const row = convert(source, name);
    if (row.status !== TIConnect.transferStatuses.XFR_SUCCESS) throw new Error(JSON.stringify(row));
    return row;
  });
  return {converter: document.querySelector('#_tijs').src, rows, actual, files};
})()
