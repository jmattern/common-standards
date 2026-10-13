# Agent and maintainer instructions

## Maintaining this catalog

- Each rule lives in its own `rules/CS-NNN.json` file and must satisfy
  `rules/schema.json`. IDs are unique, immutable, and never reused. Every rule
  declares exactly `error` or `warning` severity.
- Add new standards with the next unused ID. If a rule must change meaning,
  create a new ID and mark the old one superseded in its definition; do not
  silently rewrite the old contract.
- Update `standards.schema.json`, `rules/profiles.json`, docs, tests, and
  consuming examples when the checker contract changes.
- Keep JavaScript/TypeScript parser dependencies exactly pinned in
  `linters/package.json` and lockfile. Retain the TypeScript syntax smoke
  fixture when changing ESLint parser configuration.
- Keep commands as argv arrays, not shell strings. A `{files}` argument is
  replaced with the repository's matching paths. Missing required tools,
  configs, malformed metadata, and expired exceptions fail checks.
- Exceptions need `rule_id`, nonempty path `scope`, known `owner`, a useful
  `justification`, and a future `expires` date. Do not add open-ended waivers.
- Never claim a check passed unless its command actually ran successfully.
  Preserve `not_applicable` and `approved_exception` as distinct report states.

## Adopting in another repository

1. Pin this repo by immutable commit or vendor the reviewed files.
2. Add `DEPENDENCIES.md` or pip-compatible `requirements.txt`, a `TOOLCHAINS.md`,
   and `standards.json` based on the schema. State explicitly when there are no
   third-party dependencies.
3. Copy and review applicable files from `linters/`; configure commands and
   exact versions for the project's real build. For C/C++, provide a compile
   database for clang-tidy.
4. Run `python tools/standards.py --repo /path/to/project` locally.
5. In CI, run `python tools/standards.py --lint-only --lint-output lint.json`
   in the lint job. Upload `lint.json`; in an always-running standards job,
   pass it with `--lint-report lint.json`. The standards job then consumes
   CS-002 results without repeating linter commands.

This repository does not claim ownership or licensing authority. Add
`.github/CODEOWNERS` and a license only when the responsible people have
provided those facts.
