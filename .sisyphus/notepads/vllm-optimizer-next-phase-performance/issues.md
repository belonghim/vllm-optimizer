# Issues
- 2026-03-07: `lsp_diagnostics` still reports existing typing/queue warnings in `backend/services/load_engine.py` and deprecated typing in `backend/models/load_test.py`; left as-is because they predate this change.

- None encountered; pipeline YAML passed python safe_load validation.

- Unable to run `lsp_diagnostics` because yaml-language-server is not installed and `npm install -g yaml-language-server` fails with EACCES on /usr/local/lib/node_modules.
