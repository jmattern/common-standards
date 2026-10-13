#!/usr/bin/env python3
"""Validate and run the repository coding standards declared by this project."""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError as exc:  # pragma: no cover - exercised in a subprocess fixture
    raise SystemExit("jsonschema is required; install requirements.txt") from exc


ROOT = Path(__file__).resolve().parents[1]
RULE_SCHEMA = ROOT / "rules" / "schema.json"
CONFIG_SCHEMA = ROOT / "standards.schema.json"
PROFILES_FILE = ROOT / "rules" / "profiles.json"
PROFILES_SCHEMA = ROOT / "rules" / "profiles.schema.json"
IGNORED_DIRS = {".git", ".venv", "node_modules", "vendor", "target", "build", "dist"}
REQUIRED_RULE_IDS = {f"CS-{number:03d}" for number in range(1, 14)}
SOURCE_GLOBS = [
    "*.py",
    "*.js",
    "*.mjs",
    "*.cjs",
    "*.jsx",
    "*.ts",
    "*.tsx",
    "*.go",
    "*.rs",
    "*.java",
    "*.sh",
    "*.bash",
    "*.c",
    "*.h",
    "*.cc",
    "*.hh",
    "*.cpp",
    "*.hpp",
    "*.cxx",
    "*.hxx",
    "*.cs",
    "*.swift",
    "*.kt",
    "*.kts",
    "*.rb",
    "*.php",
]
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
]


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def validate(instance: Any, schema: dict[str, Any], label: str) -> list[str]:
    if not isinstance(schema, dict):
        return [f"{label}: invalid JSON Schema: schema must be an object"]
    try:
        Draft202012Validator.check_schema(schema)
    except (SchemaError, TypeError) as exc:
        return [f"{label}: invalid JSON Schema: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{label}: {error.json_path}: {error.message}"
        for error in sorted(
            validator.iter_errors(instance), key=lambda item: item.json_path
        )
    ]


def load_rules() -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    rules: dict[str, dict[str, Any]] = {}
    try:
        schema = read_json(RULE_SCHEMA)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"cannot read rule schema: {exc}"]
    for path in sorted((ROOT / "rules").glob("CS-*.json")):
        try:
            rule = read_json(path)
            errors.extend(validate(rule, schema, str(path.relative_to(ROOT))))
            if not isinstance(rule, dict):
                continue
            rule_id = rule.get("id")
            if rule_id in rules:
                errors.append(f"duplicate immutable rule ID: {rule_id}")
            elif isinstance(rule_id, str):
                rules[rule_id] = rule
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: cannot read rule definition: {exc}")
    missing = sorted(REQUIRED_RULE_IDS - set(rules))
    if missing:
        errors.append(f"catalog is missing required rule IDs: {', '.join(missing)}")
    return rules, errors


def files_in(repo: Path) -> list[Path]:
    found = []
    for path in repo.rglob("*"):
        if not path.is_file() or any(
            part in IGNORED_DIRS for part in path.relative_to(repo).parts
        ):
            continue
        found.append(path)
    return sorted(found)


def matched_files(repo: Path, globs: list[str]) -> list[Path]:
    return [
        path
        for path in files_in(repo)
        if any(
            fnmatch.fnmatch(path.relative_to(repo).as_posix(), pattern)
            for pattern in globs
        )
    ]


def profile_files(repo: Path, profile: dict[str, Any]) -> list[Path]:
    excluded = profile.get("exclude_globs", [])
    return [
        path
        for path in matched_files(repo, profile["globs"])
        if not any(
            fnmatch.fnmatch(path.relative_to(repo).as_posix(), pattern)
            for pattern in excluded
        )
    ]


def source_files(repo: Path) -> list[Path]:
    excluded = ["linters/**", "tests/fixtures/**"]
    return [
        path
        for path in matched_files(repo, SOURCE_GLOBS)
        if not any(
            fnmatch.fnmatch(path.relative_to(repo).as_posix(), pattern)
            for pattern in excluded
        )
    ]


def command_argv(
    command: dict[str, Any], selected_files: list[Path], repo: Path
) -> list[str]:
    relative = [path.relative_to(repo).as_posix() for path in selected_files]
    argv: list[str] = []
    for arg in command["argv"]:
        if arg == "{files}":
            argv.extend(relative)
        else:
            argv.append(arg)
    return argv


def execute(argv: list[str], cwd: Path) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        return "fail", f"required command is missing: {argv[0]}"
    except OSError as exc:
        return "fail", f"could not start {argv[0]}: {exc}"
    output = completed.stdout.strip()
    if completed.returncode:
        return "fail", output or f"command exited with status {completed.returncode}"
    return "pass", output or "command succeeded"


def exception_errors(
    config: dict[str, Any], rule_ids: set[str], today: dt.date
) -> list[str]:
    errors: list[str] = []
    for index, item in enumerate(config.get("exceptions", [])):
        rule_id = item.get("rule_id")
        if rule_id not in rule_ids:
            errors.append(f"exception {index}: unknown rule ID {rule_id!r}")
        try:
            expires = dt.date.fromisoformat(item.get("expires", ""))
        except (TypeError, ValueError):
            errors.append(f"exception {index}: expires must be an ISO date")
        else:
            if expires < today:
                errors.append(
                    f"exception {index}: exception for {rule_id} expired on {expires}"
                )
        if not item.get("scope") or any(
            not str(scope).strip() for scope in item.get("scope", [])
        ):
            errors.append(f"exception {index}: scope must contain a path or glob")
    return errors


def exception_for(
    config: dict[str, Any], rule_id: str, paths: list[str]
) -> dict[str, Any] | None:
    for item in config.get("exceptions", []):
        if item.get("rule_id") != rule_id:
            continue
        scopes = item.get("scope", [])
        if paths and all(path_is_covered(path, scopes) for path in paths):
            return item
    return None


def path_is_covered(path: str, scopes: list[str]) -> bool:
    return any(
        scope in {".", "**/*"} or fnmatch.fnmatch(path, scope) for scope in scopes
    )


def result(
    rule_id: str, severity: str, status: str, detail: str, **extra: Any
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "severity": severity,
        "status": status,
        "detail": detail,
        **extra,
    }


def apply_exception(
    item: dict[str, Any], config: dict[str, Any], paths: list[str]
) -> dict[str, Any]:
    if item["status"] != "fail":
        return item
    exception = exception_for(config, item["id"], paths)
    if exception:
        item = dict(item)
        item["status"] = "approved_exception"
        item["detail"] += (
            f"; exception owner={exception['owner']}, expires={exception['expires']}: "
            f"{exception['justification']}"
        )
    return item


def run_profiles(repo: Path, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outcomes = []
    for profile in profiles:
        selected = profile_files(repo, profile)
        if not selected:
            continue
        missing = [
            config for config in profile["configs"] if not (repo / config).is_file()
        ]
        if missing:
            outcomes.append(
                {
                    "key": f"{profile['id']}/configuration",
                    "profile": profile["id"],
                    "files": [path.relative_to(repo).as_posix() for path in selected],
                    "status": "fail",
                    "detail": f"required configuration missing: {', '.join(missing)}",
                }
            )
            continue
        if (
            profile.get("compilation_database")
            and not (repo / "build" / "compile_commands.json").is_file()
        ):
            outcomes.append(
                {
                    "key": f"{profile['id']}/compilation-database",
                    "profile": profile["id"],
                    "files": [path.relative_to(repo).as_posix() for path in selected],
                    "status": "fail",
                    "detail": (
                        "C/C++ clang-tidy requires build/compile_commands.json. "
                        "Configure CMake with -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "
                        "or pass the actual database directory."
                    ),
                }
            )
            continue
        for command in profile["commands"]:
            argv = command_argv(command, selected, repo)
            status, detail = execute(argv, repo)
            outcomes.append(
                {
                    "key": f"{profile['id']}/{command['id']}",
                    "profile": profile["id"],
                    "command": argv,
                    "files": [path.relative_to(repo).as_posix() for path in selected],
                    "status": status,
                    "detail": detail,
                }
            )
    return outcomes


def load_lint_report(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("checks"), list)
    ):
        raise ValueError(
            "lint report must be an object with version=1 and checks array"
        )
    for item in data["checks"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("key"), str)
            or item.get("status") not in {"pass", "fail", "not_applicable"}
            or not isinstance(item.get("files", []), list)
            or any(not isinstance(file, str) for file in item.get("files", []))
        ):
            raise ValueError("lint report contains an invalid check entry")
    return data


def check_profile_coverage(
    repo: Path, profiles: list[dict[str, Any]], outcomes: list[dict[str, Any]]
) -> list[str]:
    actual = {item["key"] for item in outcomes}
    expected: set[str] = set()
    for profile in profiles:
        if not profile_files(repo, profile):
            continue
        if any(not (repo / config).is_file() for config in profile["configs"]):
            expected.add(f"{profile['id']}/configuration")
        elif (
            profile.get("compilation_database")
            and not (repo / "build" / "compile_commands.json").is_file()
        ):
            expected.add(f"{profile['id']}/compilation-database")
        else:
            expected.update(
                f"{profile['id']}/{command['id']}" for command in profile["commands"]
            )
    return sorted(expected - actual)


def check_dependencies(repo: Path) -> tuple[str, str]:
    declaration = repo / "DEPENDENCIES.md"
    requirements = repo / "requirements.txt"
    if declaration.is_file():
        content = declaration.read_text(encoding="utf-8")
        body = "\n".join(
            line
            for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ).strip()
        if body:
            return (
                "pass",
                "top-level DEPENDENCIES.md contains dependency guidance or "
                "an explicit no-dependencies statement",
            )
    if requirements.is_file():
        lines = [
            line.strip()
            for line in requirements.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        active = [line for line in lines if not line.startswith("#")]
        if active and all(
            line.startswith(
                (
                    "-r ",
                    "--requirement ",
                    "-c ",
                    "--constraint ",
                    "--index-url ",
                    "--extra-index-url ",
                    "--trusted-host ",
                    "--find-links ",
                    "--no-index",
                )
            )
            or re.match(
                r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:\s*(?:===|==|!=|~=|<=|>=|<|>)\s*[^\s,;]+(?:\s*,\s*(?:===|==|!=|~=|<=|>=|<|>)\s*[^\s,;]+)*)?(?:\s*;\s*.+)?$",
                line,
            )
            for line in active
        ):
            return "pass", "top-level requirements.txt contains dependency declarations"
        if any("no dependenc" in line.lower() for line in lines):
            return (
                "pass",
                "requirements.txt explicitly states there are no dependencies",
            )
    return (
        "fail",
        "add nonempty dependency guidance or a pip-compatible top-level "
        "requirements.txt; state explicitly if there are no dependencies",
    )


def check_reproducibility(repo: Path) -> tuple[str, str]:
    requirements = repo / "requirements.txt"
    declaration = repo / "DEPENDENCIES.md"
    lock_pairs = {
        "package-lock.json": "package.json",
        "npm-shrinkwrap.json": "package.json",
        "yarn.lock": "package.json",
        "pnpm-lock.yaml": "package.json",
        "Cargo.lock": "Cargo.toml",
        "go.sum": "go.mod",
        "Gemfile.lock": "Gemfile",
        "composer.lock": "composer.json",
        "uv.lock": "pyproject.toml",
        "poetry.lock": "pyproject.toml",
        "Pipfile.lock": "Pipfile",
        "packages.lock.json": "*.csproj",
        "gradle.lockfile": "*.gradle*",
    }
    for lockfile, manifest in lock_pairs.items():
        if (repo / lockfile).is_file() and any(repo.glob(manifest)):
            return "pass", f"{lockfile} is present with its {manifest} manifest"
    if requirements.is_file():
        pending = [requirements]
        seen: set[Path] = set()
        active = 0
        while pending:
            file = pending.pop()
            if file in seen:
                continue
            seen.add(file)
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                return (
                    "fail",
                    f"cannot read requirements include {file.relative_to(repo)}: {exc}",
                )
            for number, line in enumerate(lines, start=1):
                value = line.partition("#")[0].strip()
                if not value:
                    continue
                include = re.match(r"^(?:-r|--requirement)(?:\s+|=)(.+)$", value)
                if include:
                    included = (file.parent / include.group(1).strip()).resolve()
                    if not included.is_relative_to(repo.resolve()):
                        return (
                            "fail",
                            "requirements include escapes repository at "
                            f"{file.relative_to(repo)}:{number}",
                        )
                    pending.append(included)
                    continue
                if value.startswith(("-c ", "--constraint ")):
                    included = (file.parent / value.split(maxsplit=1)[1]).resolve()
                    if not included.is_relative_to(repo.resolve()):
                        return (
                            "fail",
                            "constraint include escapes repository at "
                            f"{file.relative_to(repo)}:{number}",
                        )
                    pending.append(included)
                    continue
                if value.startswith(
                    (
                        "--index-url ",
                        "--extra-index-url ",
                        "--trusted-host ",
                        "--find-links ",
                        "--no-index",
                    )
                ):
                    continue
                active += 1
                if not re.match(
                    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9.!+_-]*(?:\s*;\s*.+)?$",
                    value,
                ):
                    return (
                        "fail",
                        f"{file.relative_to(repo)}:{number} must use an exact "
                        "package==version pin; unsupported/unpinned entries "
                        "are not reproducible",
                    )
        if active:
            return (
                "pass",
                f"all {active} requirements entries use exact pins, with "
                "includes resolved within the repository",
            )
        content = "\n".join(path.read_text(encoding="utf-8").lower() for path in seen)
        if "no third-party dependenc" in content:
            return (
                "pass",
                "dependency declaration explicitly states there are no "
                "third-party dependencies",
            )
        return (
            "fail",
            "requirements files contain no dependencies but do not "
            "explicitly state that fact",
        )
    if declaration.is_file():
        content = declaration.read_text(encoding="utf-8").lower()
        if "no third-party dependenc" in content:
            return (
                "pass",
                "dependency declaration explicitly states there are no "
                "third-party dependencies",
            )
        return (
            "fail",
            "dependency declaration needs pinned versions or lockfile "
            "guidance, or an explicit no-dependencies statement",
        )
    return "fail", "no dependency declaration exists"


def check_secrets(repo: Path) -> tuple[str, str]:
    findings = []
    for path in files_in(repo):
        if path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".pdf",
            ".zip",
            ".lock",
        }:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            findings.append(path.relative_to(repo).as_posix())
    if findings:
        return (
            "fail",
            f"high-confidence credential pattern found in: {', '.join(findings)}",
        )
    return "pass", "no high-confidence private-key or common provider-key pattern found"


def check_readme(repo: Path) -> tuple[str, str]:
    path = repo / "README.md"
    if not path.is_file():
        return "fail", "README.md is missing"
    content = path.read_text(encoding="utf-8").lower()
    missing = [
        label
        for label, terms in {
            "setup": ["setup", "install", "getting started"],
            "build": ["build", "compile"],
            "test": ["test"],
            "lint": ["lint", "format"],
        }.items()
        if not any(term in content for term in terms)
    ]
    return (
        (
            "fail",
            "README.md needs setup/build/test/lint instructions; missing: "
            f"{', '.join(missing)}",
        )
        if missing
        else ("pass", "README.md mentions setup, build, test, and lint")
    )


def check_toolchains(repo: Path) -> tuple[str, str]:
    path = repo / "TOOLCHAINS.md"
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        return "fail", "add TOOLCHAINS.md with supported runtime and tool versions"
    return "pass", "TOOLCHAINS.md is present and nonempty"


def check_license(repo: Path) -> tuple[str, str]:
    if any(
        (repo / name).is_file()
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
    ):
        return "pass", "license file exists"
    readme = repo / "README.md"
    content = readme.read_text(encoding="utf-8").lower() if readme.is_file() else ""
    if "proprietary" in content or "all rights reserved" in content:
        return "pass", "README.md states restrictive rights terms"
    return (
        "fail",
        "license is unknown; add a license or an authorized rights statement",
    )


def check_owner(repo: Path) -> tuple[str, str]:
    for name in (".github/CODEOWNERS", "CODEOWNERS"):
        path = repo / name
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            return "pass", f"{name} is present"
    return (
        "fail",
        "ownership is unknown; add CODEOWNERS when an authorized owner is known",
    )


def evaluate(
    repo: Path,
    config_path: Path,
    lint_report: Path | None = None,
    lint_only: bool = False,
    today: dt.date | None = None,
) -> dict[str, Any]:
    today = today or dt.date.today()
    rules, rule_errors = load_rules()
    config_errors: list[str] = []
    try:
        config = read_json(config_path)
        config_errors.extend(
            validate(config, read_json(CONFIG_SCHEMA), str(config_path))
        )
    except (OSError, json.JSONDecodeError) as exc:
        config = {"schema_version": 1, "checks": {}, "exceptions": []}
        config_errors.append(f"cannot read standards configuration: {exc}")
    if rule_errors or config_errors:
        detail = "; ".join(rule_errors + config_errors)
        return make_report(
            repo,
            [result("CS-012", "error", "fail", detail)],
            rule_errors,
            config_errors,
        )
    config_errors.extend(exception_errors(config, set(rules), today))
    if config_errors:
        detail = "; ".join(config_errors)
        return make_report(
            repo,
            [result("CS-012", "error", "fail", detail)],
            rule_errors,
            config_errors,
        )
    try:
        profiles_document = read_json(PROFILES_FILE)
        profile_errors = validate(
            profiles_document, read_json(PROFILES_SCHEMA), str(PROFILES_FILE)
        )
        if profile_errors:
            raise ValueError("; ".join(profile_errors))
        profiles = profiles_document["profiles"]
        if len({profile["id"] for profile in profiles}) != len(profiles):
            raise ValueError("linter profile IDs must be unique")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        rule_errors.append(f"invalid linter profiles: {exc}")
        detail = "; ".join(rule_errors)
        return make_report(
            repo,
            [result("CS-012", "error", "fail", detail)],
            rule_errors,
            config_errors,
        )

    lint_checks: list[dict[str, Any]]
    lint_report_error = ""
    if lint_report:
        try:
            lint_checks = load_lint_report(lint_report)["checks"]
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            lint_checks = []
            lint_report_error = f"invalid lint report: {exc}"
    else:
        lint_checks = run_profiles(repo, profiles)

    results: list[dict[str, Any]] = []
    if not lint_only:
        status, detail = check_dependencies(repo)
        results.append(result("CS-001", rules["CS-001"]["severity"], status, detail))

    expected_missing = check_profile_coverage(repo, profiles, lint_checks)
    lint_failures = [item for item in lint_checks if item.get("status") == "fail"]
    if expected_missing:
        lint_failures.extend(
            {"key": key, "status": "fail", "detail": "lint result missing from report"}
            for key in expected_missing
        )
    if lint_report_error:
        lint_failures.append(
            {"key": "report", "status": "fail", "detail": lint_report_error}
        )
    if lint_only:
        lint_results = [
            result(
                "CS-002",
                rules["CS-002"]["severity"],
                item["status"],
                item.get("detail", ""),
                check=item["key"],
                profile=item.get("profile"),
                files=item.get("files", []),
            )
            for item in lint_checks
        ]
        if not lint_checks and not expected_missing:
            lint_results.append(
                result(
                    "CS-002",
                    rules["CS-002"]["severity"],
                    "not_applicable",
                    "no configured linter profile matches repository files",
                )
            )
        return make_report(repo, lint_results, rule_errors, config_errors)
    if lint_checks or expected_missing or lint_report_error:
        detail = (
            "all applicable linter profiles passed"
            if not lint_failures
            else "; ".join(
                f"{item['key']}: {item.get('detail', item['status'])}"
                for item in lint_failures
            )
        )
        status = (
            "fail"
            if lint_failures
            else (
                "not_applicable"
                if lint_checks
                and all(item.get("status") == "not_applicable" for item in lint_checks)
                and not expected_missing
                else "pass"
            )
        )
    else:
        status, detail = (
            "not_applicable",
            "no configured linter profile matches repository files",
        )
    affected_lint_paths = sorted(
        {path for item in lint_failures for path in item.get("files", [])}
    ) or (["."] if lint_failures else [])
    results.append(
        result(
            "CS-002",
            rules["CS-002"]["severity"],
            status,
            detail,
            checks=lint_checks,
            affected_files=affected_lint_paths,
        )
    )

    for rule_id in ("CS-003", "CS-004", "CS-005"):
        commands = config.get("checks", {}).get(rule_id, [])
        if rule_id == "CS-004" and not source_files(repo):
            results.append(
                result(
                    rule_id,
                    rules[rule_id]["severity"],
                    "not_applicable",
                    "no source files found",
                )
            )
            continue
        command_results = []
        affected_paths: set[str] = set()
        for command in commands:
            when = command.get("when", [])
            selected = matched_files(repo, when) if when else []
            if when and not selected:
                command_results.append(
                    {
                        "id": command["id"],
                        "status": "not_applicable",
                        "detail": "no matching files",
                    }
                )
                continue
            argv = command_argv(command, selected, repo)
            command_status, command_detail = execute(argv, repo)
            command_files = [path.relative_to(repo).as_posix() for path in selected]
            command_results.append(
                {
                    "id": command["id"],
                    "argv": argv,
                    "files": command_files,
                    "status": command_status,
                    "detail": command_detail,
                }
            )
            if command_status == "fail":
                affected_paths.update(command_files)
        failed = [item for item in command_results if item["status"] == "fail"]
        if not commands:
            status, detail = "fail", f"{rule_id} has no configured command"
        elif failed:
            status = "fail"
            detail = "; ".join(f"{item['id']}: {item['detail']}" for item in failed)
        elif command_results and all(
            item["status"] == "not_applicable" for item in command_results
        ):
            status, detail = (
                "not_applicable",
                "all configured commands are not applicable",
            )
        else:
            status = "pass"
            detail = (
                f"{len(command_results)} configured command(s) passed or "
                "were not applicable"
            )
        results.append(
            result(
                rule_id,
                rules[rule_id]["severity"],
                status,
                detail,
                checks=command_results,
                affected_files=sorted(affected_paths)
                or (["."] if status == "fail" else []),
            )
        )

    simple_checks = {
        "CS-006": check_toolchains,
        "CS-007": check_reproducibility,
        "CS-008": check_secrets,
        "CS-009": check_readme,
        "CS-010": check_owner,
        "CS-011": check_license,
        "CS-013": lambda root: (
            ("pass", "AGENTS.md is present")
            if (root / "AGENTS.md").is_file() and (root / "AGENTS.md").stat().st_size
            else ("fail", "top-level AGENTS.md is missing or empty")
        ),
    }
    for rule_id, check in simple_checks.items():
        status, detail = check(repo)
        results.append(result(rule_id, rules[rule_id]["severity"], status, detail))

    metadata_status = "fail" if config_errors or rule_errors else "pass"
    metadata_detail = (
        "; ".join(config_errors + rule_errors)
        if config_errors or rule_errors
        else "catalog, schemas, configuration, and exceptions are valid"
    )
    results.append(
        result("CS-012", rules["CS-012"]["severity"], metadata_status, metadata_detail)
    )

    results = [
        apply_exception(item, config, item.get("affected_files") or ["."])
        for item in results
    ]
    return make_report(repo, results, rule_errors, config_errors)


def make_report(
    repo: Path,
    results: list[dict[str, Any]],
    rule_errors: list[str],
    config_errors: list[str],
) -> dict[str, Any]:
    has_errors = any(
        item["severity"] == "error" and item["status"] == "fail" for item in results
    )
    metadata_errors = rule_errors + config_errors
    return {
        "version": 1,
        "repository": str(repo.resolve()),
        "status": "fail" if has_errors or metadata_errors else "pass",
        "counts": {
            status: sum(item["status"] == status for item in results)
            for status in ("pass", "fail", "not_applicable", "approved_exception")
        },
        "results": results,
        "metadata_errors": metadata_errors,
    }


def print_human(report: dict[str, Any]) -> None:
    print(f"Standards: {report['status'].upper()} ({report['repository']})")
    for item in report["results"]:
        print(
            f"{item['id']} [{item['severity']}] {item['status'].upper()}: "
            f"{item['detail']}"
        )


def write_github_summary(report: dict[str, Any], path: Path) -> None:
    lines = [
        f"## Coding standards: {report['status'].upper()}",
        "",
        "| Rule | Severity | Result | Details |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["results"]:
        detail = str(item["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item['id']} | {item['severity']} | {item['status']} | {detail} |"
        )
    if report.get("metadata_errors"):
        lines.extend(["", "### Metadata errors", ""])
        lines.extend(f"- {error}" for error in report["metadata_errors"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=ROOT, help="target repository root"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="standards.json path (default: <repo>/standards.json)",
    )
    parser.add_argument(
        "--lint-only", action="store_true", help="run CS-002 and emit a lint artifact"
    )
    parser.add_argument(
        "--lint-output",
        type=Path,
        help="write lint-only check results to this JSON path",
    )
    parser.add_argument(
        "--lint-report",
        type=Path,
        help="consume CS-002 results from a previous lint job",
    )
    parser.add_argument(
        "--json-out", type=Path, help="write the full JSON report to this path"
    )
    parser.add_argument(
        "--github-summary",
        type=Path,
        help="append a Markdown report to a GitHub Actions summary file",
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    config = (args.config or repo / "standards.json").resolve()
    report = evaluate(repo, config, args.lint_report, args.lint_only)
    print_human(report)
    if args.lint_only and args.lint_output:
        checks = []
        for item in report["results"]:
            if item["id"] == "CS-002":
                checks.append(
                    {
                        "key": item.get("check", "not-applicable"),
                        "profile": item.get("profile"),
                        "status": item["status"],
                        "detail": item["detail"],
                        "files": item.get("files", []),
                    }
                )
        args.lint_output.parent.mkdir(parents=True, exist_ok=True)
        args.lint_output.write_text(
            json.dumps({"version": 1, "checks": checks}, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.github_summary:
        write_github_summary(report, args.github_summary)
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
