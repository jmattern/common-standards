# Shared linter baselines

These files are templates for consuming repositories. Copy the applicable
configuration to a location the tool discovers, or pass the listed config
path explicitly. Root-level copies in this repository are active configs for
this repository. The `profiles.json` contract requires a profile's config to
exist and then runs its command; absent tools or configs fail CS-002.

| Files | Tool | Notes |
| --- | --- | --- |
| `eslint.config.mjs`, `package.json`, `package-lock.json` | ESLint + typescript-eslint | ESLint flat config parses TypeScript and applies the TS-specific unused-variable rule. Run `npm ci --prefix linters`; this lock also pins markdownlint-cli2. The parser smoke fixture is in `fixtures/`. |
| `ruff.toml` | Ruff | Python lint baseline. Formatting is checked separately with `ruff format --check`. |
| `.golangci.yml` | golangci-lint | Enables standard checks plus gosec and revive, with gofmt/goimports formatters. |
| `rustfmt.toml` | rustfmt | Rust formatting baseline. Clippy runs all targets and denies warnings. |
| `checkstyle.xml` | Checkstyle | Java import, whitespace, braces, and class structure rules. |
| `.shellcheckrc` | ShellCheck | Enables all available checks and external source following. |
| `.markdownlint-cli2.yaml` | markdownlint-cli2 | Enables standard Markdown checks, with explicit allowances for long lines, embedded HTML, and non-title-first documents. |
| `.yamllint` | yamllint | Relaxed YAML base with line length and truthy scalar policy. |
| `.clang-tidy`, `.clang-format` | clang-tidy, clang-format | C and C++ checks need `build/compile_commands.json`; generate it with CMake's `CMAKE_EXPORT_COMPILE_COMMANDS`. |
| `.editorconfig` | EditorConfig, dotnet format, ktlint | Shared whitespace settings; the C# section enables .NET analyzer diagnostics at warning severity. |
| `.swiftlint.yml` | SwiftLint | Enables selected opt-in rules and caps line lengths. |
| `.rubocop.yml` | RuboCop | Ruby version and common layout/complexity limits. |
| `phpcs.xml` | PHP_CodeSniffer | PSR-12 ruleset. |

The configs are tool-readable, but tool releases and project build integration
remain the adopting repository's responsibility. Pin each tool in that
repository's lockfile, tool-version file, or CI setup and record the pin in
`TOOLCHAINS.md`. The shared profile names tools but intentionally makes no
claim that every language tool is installed or executed in this repository's
CI. Current CI installs only Ruff, yamllint, markdownlint-cli2, ESLint, and
the TypeScript parser because those are the tools required by checked-in code
or fixtures.

For C#, `.editorconfig` provides analyzer severities, while `dotnet format
--verify-no-changes` requires a project or solution and the corresponding .NET
SDK. For Rust, the Clippy command is the baseline policy; `rustfmt.toml` is
passed explicitly. Kotlin ktlint reads EditorConfig settings. Check the
upstream tool documentation when selecting versions because supported options
can change between releases.
