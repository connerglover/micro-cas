# Pinned upstream components

Downloaded from https://adriweb.github.io/tilibs/ on 2026-10-11, without
modification. `build-sources.json` and `webtilp-deps.txt` are the deployment's
own build records, not inferred versions.

- WebTILP: https://github.com/adriweb/tilibs/tree/06d60cbc795c801061ab40bce0f932cade94bc1a
  (`webtilp.js`, `webtilp.wasm`; GPL-2.0-or-later, see COPYING).
- TIVarsLib: https://github.com/adriweb/tivars_lib_cpp/tree/cfb3529ccdc2f34918a928a5080b195585d11842
  (`TIVarsLib.js`, `TIVarsLib.wasm`; MIT, see TIVarsLib-LICENSE).
- Emscripten 6.0.9. Dependency versions, hashes, URLs and patches are recorded
  in `webtilp-deps.txt`. The pinned tilibs tree contains the build scripts.

The converter is also used by the automatic calculator build. Every source or
bytecode payload is converted, read back, and compared byte-for-byte, including
the embedded module name and the PythonScript/PythonModule type.

cas-evo's browser code uses the unmodified runtime through its public C exports.
No dependency supplies claims of cas-evo hardware acceptance.
