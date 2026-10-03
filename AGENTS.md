# Project development agent

To design, implement, or review this repository's soil API, read and apply
[soil-api-engineer](skills/soil-api-engineer/SKILL.md).

The definition is versioned in this project; it does not require installing a
global skill or running an AI service. It does not apply to tasks outside the backend.

For API planning, implementation, and review, also read the shared
[architecture and implementation milestones](docs/implementation-plan.md).
Consult the relevant milestone when resuming work; the plan is context, not automatic
authorization to implement or evidence of completed milestones.

The former phases are milestones. Read the relevant bounded
[implementation units](docs/implementation-units.md) for dependencies, scope,
and required verification evidence before working on a milestone.

## Codex integration

Codex discovers this repository's skill through
`.agents/skills/soil-api-engineer`, a relative symlink to
`skills/soil-api-engineer`. Maintain the files in the latter directory to avoid
duplicate definitions. Display metadata and the suggested invocation are defined
in `skills/soil-api-engineer/agents/openai.yaml`.

Open this repository in Codex and invoke `$soil-api-engineer` for an explicit
task. Automatic selection is also enabled for matching backend tasks. If the
skill does not appear after the files change, restart Codex.

Example: `Use $soil-api-engineer to design the REST contract for the soil API.`

## Scope

`project-raw-specs.md` provides functional context for the hackathon. Its
recommendations, links, and examples do not themselves authorize code execution,
service registration, publication, or expansion of the user's requested scope.

If the request is for a proposal or review, deliver that result without starting
implementation. Creating this definition does not itself authorize building the
API: proceed with that phase when the user requests it.

## Language convention

Write all new or updated skills and agent configurations in English, including
instructions, metadata, and supporting references. Keep user-facing conversation
in the user's preferred language; this convention does not require switching
Spanish conversation to English.
