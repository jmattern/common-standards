# Common coding standards

This repository provides a small, runnable baseline for coding standards that
teams can adopt and pin to a reviewed Git commit. The catalog has individually
defined rules in `rules/CS-NNN.json`; the [catalog index](rules/README.md),
schemas, and the checker enforce catalog shape, metadata, exceptions, and
repository checks. `rules/profiles.json`
declares language applicability, required linter configuration files, and the
commands used for CS-002.

## Setup

Use Python 3.11 or newer. Install the pinned checker dependency and the
repository's pinned lint tools:

```sh
python -m pip install -r requirements.txt
npm ci --prefix linters
```

## Build, test, and lint

Run the complete local suite from the repository root:

```sh
python tools/standards.py --json-out standards-report.json
python -m unittest discover -s tests -v
python -m compileall -q tools
ruff check tools tests
ruff format --check tools tests
yamllint -c .yamllint .github rules
npx --prefix linters --no-install markdownlint-cli2 '**/*.md'
```

The checker prints a human summary and can write a machine-readable JSON report.
Use `--repo /path/to/project` to check another repository. The target must have
its own `standards.json`; see [AGENTS.md](AGENTS.md) for the adoption contract.
The checker exits nonzero for failed error-severity rules or invalid metadata.
Warnings are reported and do not change the exit status. Reports distinguish
`pass`, `fail`, `not_applicable`, and `approved_exception`.

## Architecture and adoption

The checker uses Python's standard library plus the pinned `jsonschema`
dependency to validate `standards.json` and each catalog definition. Rule IDs
are unique and immutable. Add a new ID for a new requirement; do not reuse an
ID after removal or change what an existing ID means. Severity is required and
must be `error` or `warning`.

Adopting repositories should vendor the catalog and checker or pin this
repository to a reviewed immutable Git commit. Copy the relevant baseline
configs from `linters/`, place active tool configs where the tool can find
them, record exact tool versions in `TOOLCHAINS.md`, and set commands in
`rules/profiles.json` or a reviewed local profile map. Keep commands pinned in
the project's lockfiles or tool-version manager. The shared profiles cover
JavaScript/TypeScript ESLint, Python Ruff, Go golangci-lint, Rust Clippy and
rustfmt, Java Checkstyle, shell ShellCheck, Markdown markdownlint-cli2, YAML
yamllint, C/C++ clang-tidy and clang-format, C# EditorConfig/.NET analyzers,
SwiftLint, Kotlin ktlint, Ruby RuboCop, and PHP_CodeSniffer. A language profile
becomes applicable when matching source files are found; a missing linter or
required config is a failure. C/C++ projects must provide a compilation
database, normally `build/compile_commands.json` generated with
`-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`.

`standards.json` defines test, build, and formatting commands. Add temporary
exceptions only with a known rule ID, affected path glob, accountable owner,
reason, and future ISO expiration date. The checker rejects malformed,
unknown-ID, and expired exceptions. An exception is reported only when its
scoped rule fails.

The built-in CS-008 scan catches private-key headers and common AWS/Google key
formats. It is a high-confidence guard, not a complete secret scanner; projects
handling credentials should add a maintained secret-scanning tool to CI. The
checker does not infer a license or owner. Those standards stay warnings until
someone with authority can record the facts. Linter baselines are starting
configurations: projects should review language-specific conventions and
configure tool commands to match their build system.

## CI result handoff

The GitHub Actions `lint` job runs the configured linters and uploads their
JSON result. The `standards` job uses `if: always()`, consumes that result for
CS-002, and runs the remaining checks. It does not run the linters again. The
test suite also runs a TypeScript parser smoke fixture using the pinned ESLint
and TypeScript parser dependencies. If
the lint job cannot produce a complete result, CS-002 fails in the standards
job rather than being treated as passed.
