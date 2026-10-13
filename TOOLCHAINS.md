# Toolchains

- Python: 3.11 or newer (CI currently runs Python 3.12).
- Ruff: 0.17.0.
- Node.js: 24.
- Python lint tools: Ruff 0.17.0 and yamllint 1.38.0 (all dependencies pinned in `requirements.txt`).
- markdownlint-cli2: 0.17.2 (full npm dependency tree pinned in `linters/package-lock.json`).
- ESLint: 10.10.0, TypeScript: 5.9.3, typescript-eslint: 8.71.1 (locked in `linters/package-lock.json`).
- yamllint: 1.38.0.

Language-specific tools in `rules/` are selected and pinned by each adopting
repository. Their versions must be recorded alongside that repository's
commands. This repository's CI installs only the tools needed for files it
contains.
