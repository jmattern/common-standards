# Standard catalog

The checker loads one JSON definition per ID from this directory. IDs are
unique and immutable. Add a new ID for a new requirement; never reuse an ID
after retirement. Each definition declares a required severity and a concrete
verification statement.

| ID | Severity | Requirement |
| --- | --- | --- |
| CS-001 | error | Declare dependencies or explicitly state that none are used. |
| CS-002 | error | Run the applicable configured language and file-type linters. |
| CS-003 | error | Declare and pass the test command. |
| CS-004 | error | Declare and pass a build or compile command when source exists. |
| CS-005 | error | Declare and pass format checks. |
| CS-006 | error | Declare supported runtime and toolchain versions. |
| CS-007 | error | Pin or lock dependency resolution for reproducible installs. |
| CS-008 | error | Keep secrets out of source and committed configuration. |
| CS-009 | warning | Document setup, build, test, and lint commands in README.md. |
| CS-010 | warning | Identify code owners when an authorized owner is known. |
| CS-011 | warning | State licensing terms when authorized terms are known. |
| CS-012 | error | Validate all temporary exceptions, their scope, owner, reason, and expiry. |
| CS-013 | warning | Provide top-level AGENTS.md contributor guidance. |

The individual JSON files are authoritative for exact definitions and
verification behavior. Schemas live in `schema.json` and the repository root
`standards.schema.json`.
