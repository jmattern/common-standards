from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.standards import (
    apply_exception,
    check_dependencies,
    check_reproducibility,
    evaluate,
    exception_errors,
    load_lint_report,
    load_rules,
    make_report,
    run_profiles,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]


class StandardsTests(unittest.TestCase):
    def test_dependency_declaration_accepts_either_alternative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.assertEqual(check_dependencies(repo)[0], "fail")
            (repo / "DEPENDENCIES.md").write_text("# Dependencies\n")
            self.assertEqual(check_dependencies(repo)[0], "fail")
            (repo / "DEPENDENCIES.md").write_text("No third-party dependencies.\n")
            self.assertEqual(check_dependencies(repo)[0], "pass")
            (repo / "DEPENDENCIES.md").unlink()
            (repo / "requirements.txt").write_text("example==1.2.3\n")
            self.assertEqual(check_dependencies(repo)[0], "pass")

    def test_requirements_includes_must_be_exactly_pinned_or_locked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "requirements.txt").write_text("-r nested.txt\n")
            (repo / "nested.txt").write_text("example>=1.2\n")
            self.assertEqual(check_reproducibility(repo)[0], "fail")
            (repo / "nested.txt").write_text("example==1.2.3\n")
            self.assertEqual(check_reproducibility(repo)[0], "pass")
            (repo / "nested.txt").write_text("-e .\n")
            self.assertEqual(check_reproducibility(repo)[0], "fail")

    def test_catalog_requires_known_unique_id_shape_and_severity(self) -> None:
        schema = json.loads((ROOT / "rules/schema.json").read_text())
        valid = {
            "id": "CS-999",
            "severity": "error",
            "title": "Example",
            "definition": "This is a sufficiently detailed definition.",
            "verification": "Run the example check.",
        }
        self.assertEqual(validate(valid, schema, "fixture"), [])
        invalid = {**valid, "severity": "critical"}
        self.assertTrue(validate(invalid, schema, "fixture"))

    def test_malformed_rule_definition_and_schema_return_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules_dir = root / "rules"
            rules_dir.mkdir()
            schema = (ROOT / "rules/schema.json").read_text()
            (rules_dir / "schema.json").write_text(schema)
            (rules_dir / "CS-001.json").write_text("[]")
            with (
                patch("tools.standards.ROOT", root),
                patch("tools.standards.RULE_SCHEMA", rules_dir / "schema.json"),
            ):
                rules, errors = load_rules()
            self.assertEqual(rules, {})
            self.assertTrue(any("CS-001.json" in error for error in errors))
        self.assertTrue(validate({}, {"type": "invalid"}, "schema"))

    def test_invalid_and_expired_exceptions_fail(self) -> None:
        today = dt.date(2026, 10, 12)
        errors = exception_errors(
            {
                "exceptions": [
                    {
                        "rule_id": "CS-999",
                        "scope": ["src/**"],
                        "owner": "team",
                        "justification": "Temporary while migration is underway.",
                        "expires": "2026-10-11",
                    }
                ]
            },
            {"CS-001"},
            today,
        )
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("unknown rule ID" in error for error in errors))
        self.assertTrue(any("expired" in error for error in errors))

    def test_warning_failures_do_not_fail_report_but_error_failures_do(self) -> None:
        warning = {
            "id": "CS-010",
            "severity": "warning",
            "status": "fail",
            "detail": "unknown owner",
        }
        report = make_report(Path("."), [warning], [], [])
        self.assertEqual(report["status"], "pass")
        error = {
            "id": "CS-003",
            "severity": "error",
            "status": "fail",
            "detail": "test failed",
        }
        self.assertEqual(
            make_report(Path("."), [warning, error], [], [])["status"], "fail"
        )

    def test_result_severity_comes_from_catalog_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            config_path = repo / "standards.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "checks": {
                            "CS-003": [
                                {
                                    "id": "test",
                                    "argv": ["missing"],
                                    "when": ["none/*.py"],
                                }
                            ],
                            "CS-004": [
                                {
                                    "id": "build",
                                    "argv": ["missing"],
                                    "when": ["none/*.py"],
                                }
                            ],
                            "CS-005": [
                                {
                                    "id": "format",
                                    "argv": ["missing"],
                                    "when": ["none/*.py"],
                                }
                            ],
                        },
                        "exceptions": [],
                    }
                )
            )
            rules, errors = load_rules()
            self.assertFalse(errors)
            rules["CS-001"]["severity"] = "warning"
            with patch("tools.standards.load_rules", return_value=(rules, [])):
                report = evaluate(repo, config_path)
            dependency_rule = next(
                item for item in report["results"] if item["id"] == "CS-001"
            )
            self.assertEqual(dependency_rule["severity"], "warning")

    def test_invalid_configuration_short_circuits_as_infrastructure_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "standards.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "checks": {"CS-003": [], "CS-004": [], "CS-005": []},
                        "exceptions": [],
                    }
                )
            )
            report = evaluate(Path(directory), config_path)
            self.assertEqual(report["status"], "fail")
            self.assertTrue(report["metadata_errors"])
            self.assertEqual([item["id"] for item in report["results"]], ["CS-012"])

    def test_command_sets_with_only_nonapplicable_checks_stay_nonapplicable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            config_path = repo / "standards.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "checks": {
                            "CS-003": [
                                {
                                    "id": "tests",
                                    "argv": ["missing-tool"],
                                    "when": ["tests/**/*.py"],
                                }
                            ],
                            "CS-004": [
                                {
                                    "id": "build",
                                    "argv": ["missing-tool"],
                                    "when": ["src/**/*.py"],
                                }
                            ],
                            "CS-005": [
                                {
                                    "id": "format",
                                    "argv": ["missing-tool"],
                                    "when": ["src/**/*.py"],
                                }
                            ],
                        },
                        "exceptions": [],
                    }
                )
            )
            report = evaluate(repo, config_path)
            self.assertEqual(
                [
                    item["status"]
                    for item in report["results"]
                    if item["id"] in {"CS-003", "CS-004", "CS-005"}
                ],
                ["not_applicable"] * 3,
            )

    def test_lint_report_preserves_not_applicable_and_affected_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lint.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "checks": [
                            {
                                "key": "python/ruff",
                                "status": "not_applicable",
                                "files": [],
                            },
                            {
                                "key": "shell/shellcheck",
                                "status": "fail",
                                "files": ["scripts/run.sh"],
                            },
                        ],
                    }
                )
            )
            report = load_lint_report(path)
            self.assertEqual(report["checks"][0]["status"], "not_applicable")
            self.assertEqual(report["checks"][1]["files"], ["scripts/run.sh"])

    def test_command_failure_and_missing_command_are_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "sample.py").write_text("print('fixture')\n")
            profile = {
                "id": "fixture-python",
                "globs": ["*.py"],
                "configs": [],
                "commands": [
                    {
                        "id": "nonzero",
                        "argv": [sys.executable, "-c", "raise SystemExit(3)"],
                    },
                    {"id": "missing", "argv": ["tool-that-does-not-exist"]},
                ],
            }
            results = run_profiles(repo, [profile])
            self.assertEqual([item["status"] for item in results], ["fail", "fail"])
            self.assertIn("missing", results[1]["detail"])

    def test_mixed_profiles_are_each_covered_and_missing_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "one.py").write_text("pass\n")
            (repo / "two.sh").write_text("#!/bin/sh\ntrue\n")
            profiles = [
                {
                    "id": "python",
                    "globs": ["*.py"],
                    "configs": ["ruff.toml"],
                    "commands": [],
                },
                {
                    "id": "shell",
                    "globs": ["*.sh"],
                    "configs": [".shellcheckrc"],
                    "commands": [],
                },
            ]
            result = run_profiles(repo, profiles)
            self.assertEqual([item["status"] for item in result], ["fail", "fail"])
            self.assertIn("configuration", result[0]["key"])
            (repo / "ruff.toml").touch()
            result = run_profiles(repo, profiles)
            self.assertEqual([item["key"] for item in result], ["shell/configuration"])

    def test_scoped_exception_changes_failed_rule_to_approved_exception(self) -> None:
        item = {
            "id": "CS-009",
            "severity": "warning",
            "status": "fail",
            "detail": "missing README",
        }
        config = {
            "exceptions": [
                {
                    "rule_id": "CS-009",
                    "scope": ["tests/**"],
                    "owner": "maintainers",
                    "justification": "Legacy fixture is being retired.",
                    "expires": "2099-01-01",
                }
            ]
        }
        self.assertEqual(
            apply_exception(item, config, ["tests/fixture.md"])["status"],
            "approved_exception",
        )
        self.assertEqual(
            apply_exception(item, config, ["tests/fixture.md", "src/file.py"])[
                "status"
            ],
            "fail",
        )

    def test_typescript_parser_accepts_generic_syntax_fixture(self) -> None:
        completed = subprocess.run(
            ["npm", "--prefix", "linters", "run", "lint-typescript-smoke"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()
