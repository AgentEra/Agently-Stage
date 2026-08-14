# Agently-Stage Repository Agent Rules

## Owner Boundary

- Agently-Stage owns process-local task lifetime, settlement, sync/async call
  bridging, loop-neutral handles, replay channels, and local listener mechanics.
- It does not own Agently workflow semantics, RuntimeEvent meaning, EventCenter
  policy, business retries, durable recovery, authorization, or side effects.
- Keep Stage usable as an independent Python package. Do not import Agently into
  Stage or add Agently-specific branches to Stage runtime code.

## Managed Companion Governance

- Agently-Stage is the required-runtime companion repository for Agently. The
  Agently repository remains the source of truth for the supported Stage range
  and integration contract under `runtime_support.agently_stage`.
- A Stage change that can affect Agently must be validated twice: first against
  the Stage test/type/example contract, then against the Agently development
  line using the candidate Stage wheel.
- Raise Agently's minimum Stage dependency only after the selected Stage version
  is published on PyPI and can be installed in a clean environment.
- Changes to Stage public APIs, recommended usage, lifecycle/error semantics, or
  compatibility names must update Stage docs and the `agently-stage` guidance in
  Agently-Skills in the same work item.
- RuntimeEvent, observation payload, or run-lineage changes additionally require
  an Agently-Devtools compatibility review. Ordinary Stage mechanism changes do
  not imply a DevTools change.

## Branch And Release Flow

- Use task-scoped branches such as `feature/<scope>`, `bug-fix/<scope>`,
  `update/<scope>`, or `refactor/<scope>`, then merge accepted work to `main`.
- Stage versions do not move in lockstep with Agently versions. Within the 0.3
  line, preserve documented compatibility. Use 0.4.0 for the already-announced
  removal of 0.3 compatibility surfaces or other breaking changes.
- Release from an immutable `v<version>` tag. The tag version,
  `pyproject.toml`, and built distribution metadata must match.
- Publish Stage before merging an Agently change that raises the minimum Stage
  version. After publication, verify PyPI metadata and a clean install before
  updating Agently's lock and compatibility manifest.
- Never move or recreate an existing public tag to repair a release. If an
  uploaded version is wrong, prepare a new version.
