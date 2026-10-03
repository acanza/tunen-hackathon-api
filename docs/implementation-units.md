# Verifiable Implementation Units

Date: 2026-10-03

Status: Planning only. All units below are planned, not implemented or verified.
This document does not authorize implementation, deployment, or scope expansion.

The [architecture and milestones](implementation-plan.md) define the shared
design and delivery gates. This document defines the smallest planned units of
work. The [acceptance criteria](../skills/soil-api-engineer/references/acceptance.md)
remain the overall validation baseline.

## Execution and verification rules

- Start a unit only when its dependencies and relevant data decisions are
  resolved. Work on unrelated unblocked units may continue.
- Keep each unit to its stated behavior. If feasibility reveals another adapter,
  protocol, or independent processing method, add a separately scoped unit before
  incorporating that work; record which milestone requires it.
- Each integration updates capabilities, provenance, limitations, and the runnable
  example. Every successful layer retains the full metadata and artifact contract.
- Use small deterministic fixtures with independently calculated expected values
  for local logic. Label synthetic and recorded fixtures with their provenance.
- Keep live checks separate: record the request, date, source, result, and relevant
  metadata without secrets. Mocks and skipped network tests do not prove access.
- Include relevant earlier regression checks. Do not repeat all live queries for
  unrelated changes; identify the evidence being reused and recheck changed access
  assumptions or stale availability evidence before relying on a provider.
- Close a unit only with the evidence below. An unavailable required input leaves
  the unit blocked or verification pending; documenting the gap is not completion.

## M0: Initial feasibility

### 0A — First real spatial sample

**Dependencies:** None.

**Scope:** One reference field, SoilGrids clay, and the intervals needed for the
initial depth representation. Establish access before writing the adapter.
Exclude other parameters, API code, cache, and exhaustive provider discovery.

**Deliverable:** A reproducible bounded retrieval and feasibility record containing
field provenance, access method, sample values, units, depth intervals, CRS,
resolution, nodata convention, dataset version/date when supplied, retrieval date,
coverage, service limits, and attribution/use restrictions.

**Verification and closure:** Retrieve real underlying spatial values for the
field, not just a rendered map. Record how they can produce a clipped grid within
the proposed workload budget. Confirm a defensible depth method. If access or
necessary metadata is missing, record the blocker; do not silently switch to demo
data or claim M0 complete.

### 0B — Feasibility gate for one expansion

**Dependencies:** The candidate source/parameter for a specific downstream unit
has been identified. This check may run before or after M1.

**Scope:** Repeat 0A's evidence requirements for one additional source/parameter
combination, including all inputs needed for a derived parameter. Reuse relevant
verified metadata, but identify precisely which combinations it supports.

**Deliverable:** One named record per combination, linked from its dependent unit,
with outcome `viable`, `blocked`, or `unsupported` and the reason.

**Verification and closure:** Demonstrate a usable spatial retrieval strategy and
its cost. A point query alone does not establish field-wide support: document and
verify sampling/rasterization, spatial meaning, approximation labels, and call
budget where applicable. Only `viable` unlocks the dependent integration.
Unavailable required parameters keep M2 incomplete. Check pH methodology, nFK
input compatibility and depth, and actual Bodenzahl attributes before coding them.

## M1: First end-to-end integration

### 1A — Minimal contract and validation

**Dependencies:** 0A.

**Scope:** FastAPI skeleton, health, request/response/error models, and validation
for one field and clay. Decide Polygon/MultiPolygon support, field identifiers,
coordinate validation, depth policy, grid orientation/transform, status codes,
and the representation of unsupported, uncovered, empty, and failed results.
Exclude provider integration and rendering.

**Deliverable:** OpenAPI contract and minimal startup instructions. Specify numeric
limits for fields, area, vertices, pixels, provider calls, concurrency, retries,
and timeouts; initially accept only the bounded single-field workload.

**Verification and closure:** Accepted geometry and invalid geometry/coordinates,
duplicate or absent identifiers under the chosen policy, unsupported requests,
and excessive requests have expected outcomes. Boundary-limit cases reject work
before provider calls or large raster allocation. A contract example unambiguously
defines `[west, south, east, north]`, row/column orientation, and null values.

### 1B — One complete real layer

**Dependencies:** 1A.

**Scope:** One SoilGrids adapter and its registration; single-field coordination;
clay normalization and depth handling; clipping, statistics, legend, PNG and JSON
storage/retrieval. Include capabilities and complete provenance from this unit.
Exclude additional parameters, multi-field processing, and cache reuse.

**Deliverable:** An executable request returning a real layer with working artifact
URLs. Enforce 1A's budgets, bounded transient retries, and timeouts. Keep intensive
raster work outside the asynchronous event loop.

**Verification and closure:** A small known grid checks conversion/depth math,
axis order, transform, a polygon hole, exterior transparency, nodata exclusion,
all-nodata behavior, and agreement among JSON, PNG, statistics, and legend. A live
request downloads both artifacts and records their metadata. A simulated timeout
produces the contracted error rather than empty success; a bounded processing
check confirms health requests remain responsive under the documented budget.

## M2: Functional backend MVP

### 2A — Multiple fields and isolated failures

**Dependencies:** 1B.

**Scope:** Extend coordination to multiple fields, initially with clay. Enforce
request-wide budgets before increasing workload. Exclude new parameter adapters.

**Deliverable:** Per-field/parameter/source results with isolated artifacts and
bounded concurrency, timeouts, and provider calls.

**Verification and closure:** Two fields retain distinct IDs and outputs. Inject
one success and one failure, then total provider failure. Verify partial results,
the total-failure status, missing coverage versus missing data, and no artifact
collisions. Check aggregate limits, not just per-field limits. Exercise source
failure isolation again when the real LBEG adapter becomes available in 2E.

### 2B — Complete numeric texture

**Dependencies:** 1B and viable 0B records for sand and silt.

**Scope:** Extend the existing adapter to clay/sand/silt and expand `texture`.
Exclude categorical-to-percentage estimation and new providers.

**Deliverable:** Three numeric layers with documented units, original intervals,
depth method, and explicit statuses for missing components.

**Verification and closure:** Known inputs establish unit conversion and thickness
weighting where applicable. Missing depth intervals do not silently masquerade as
complete 0–30 cm coverage. A live request verifies all three returned components.

### 2C — Soil organic carbon

**Dependencies:** 1B and a viable SOC 0B record.

**Scope:** SOC only, using the established adapter and rendering pipeline.

**Deliverable:** A SOC layer with traceable conversion and depth method.

**Verification and closure:** Known values check conversion, applicable depth
weighting, and incomplete inputs. A live request confirms the layer metadata and
underlying values match the verified source semantics.

### 2D — pH

**Dependencies:** 1B and a viable pH 0B record, including the chosen depth method.

**Scope:** pH only. Do not introduce an undocumented arithmetic depth average.

**Deliverable:** A pH layer with method, assumptions, represented depth, and limits.

**Verification and closure:** Independently calculated examples check the selected
conversion and depth method, including missing intervals. A live request verifies
the source values and metadata used in the result.

### 2E — LBEG Bodenzahl

**Dependencies:** 2A and a viable LBEG Bodenzahl 0B record.

**Scope:** One verified LBEG adapter and registration for actual Bodenzahl. Exclude
Ertragsfähigkeit substitution, additional LBEG datasets, and texture estimation.

**Deliverable:** A spatial layer exposing its actual support, retrieval/sampling
method, limits, and provenance. Do not imply that Bodenzahl measures a 0–30 cm
interval if the source does not define that meaning.

**Verification and closure:** Recorded responses check parsing and spatial
assignment against known values. Live retrieval confirms real attributes and
coverage. A request using SoilGrids and LBEG preserves valid layers when either
provider fails in a controlled test. Adding this adapter requires registration
and adapter code, not provider conditionals in existing routes or coordination.

### 2F — Plant-available water (nFK)

**Dependencies:** 1B and viable 0B records for all required inputs and their method.

**Scope:** One justified nFK derivation for the target depth, initially from the
candidate SoilGrids inputs. Exclude cross-source averaging and equating root-zone
nFK with 0–30 cm. A required additional LBEG adapter becomes its own unit.

**Deliverable:** Formula, compatible input units/depths/spatial support, conversions,
output unit, approximation labels where applicable, and traceable layer metadata.

**Verification and closure:** A hand-calculated example checks the full derivation
and thickness handling. Missing or incompatible inputs yield an explicit status;
nonphysical results follow a documented policy rather than silent correction.
A live request confirms the actual inputs needed for the derived layer.

**M2 closure:** After 2A–2F, run a multi-field request for all five parameters using
SoilGrids and the necessary LBEG sources. Check texture expansion, capabilities,
artifact retrieval, provenance, and explicit unavailable combinations. Preserve
unit evidence and report any missing requirement; passing units individually is
not a substitute for this assembled-contract check.

## M3: Reproducible demo and freshness

### 3A — Disk cache reuse

**Dependencies:** M2.

**Scope:** Cache successful artifacts and metadata. Exclude refresh and remote
storage. Define invalidation, atomic publication, and incomplete-entry behavior.

**Deliverable:** A cache key covering geometry, parameter, source, depth, resolution,
and processing method/version; preserve original retrieval metadata on hits.

**Verification and closure:** Repeated equivalent requests reuse results without
provider calls. Vary each key component independently and verify separation.
An incomplete entry is not served as success; concurrent equivalent requests do
not publish mismatched PNG, JSON, and metadata.

### 3B — Explicit refresh

**Dependencies:** 3A.

**Scope:** `refresh: true` on the layer request, affected-entry replacement, and
failure behavior. Exclude scheduling and background jobs.

**Deliverable:** Documented semantics for successful, partial, and failed refresh,
including whether old artifacts remain retrievable and how they are identified.

**Verification and closure:** A controlled provider returns changed values on the
second call: refresh invokes it again and replaces coherent results. Failed
refresh stays visible and never labels old data as fresh. Unrelated entries are
preserved. Record a live refresh query; real values need not change to prove that
the upstream was contacted again.

### 3C — Reproducible demo

**Dependencies:** 3B and M2 evidence.

**Scope:** Complete the existing startup guide, dependencies/configuration, known
coverage fields, example requests, and limitation report. Exclude UI/deployment.

**Deliverable:** Clean-environment instructions and a recorded backend demonstration.

**Verification and closure:** Install and start from the documented environment;
execute the multi-field example, retrieve artifacts, observe cache reuse, and
refresh. Record commands, outcomes, and provider availability. Label any offline
fixture demonstration separately; it cannot replace pending live verification.

## M4: Cross-source derived layers

### 4A — Compatible aggregation and source counts

**Dependencies:** M2 and verified compatibility rules for participating layers.

**Scope:** One documented aggregation method with alignment, weights, valid masks,
participating sources, and source counts per cell. Exclude spread and uncertainty.

**Deliverable:** Derived layers with formula, method version, provenance, and
explicit behavior for zero or one compatible source.

**Verification and closure:** Small grids with known weighted results check
alignment, nodata, zero/one/multiple contributors, and incompatible units, depth,
support, or meaning. Categorical data is not continuously interpolated. Use at
least two verified compatible real layers to demonstrate multi-source behavior;
if none exist, record that verification as pending, not achieved by fixtures.

### 4B — Between-source spread

**Dependencies:** 4A.

**Scope:** One documented dispersion formula using compatible contributors.

**Deliverable:** Spread layer with unit, source count, and limitations, explicitly
distinguished from confidence intervals and provider uncertainty.

**Verification and closure:** Known grids verify the formula; fewer than two valid
sources yield unavailable spread, not zero agreement. Verify masks and source
counts match the aggregation inputs in an integrated request.

### 4C — Provider uncertainty

**Dependencies:** M2 and a viable 0B record for the provider uncertainty inputs.
This unit does not depend on 4A or 4B.

**Scope:** One provider's documented uncertainty representation. Exclude combining
providers' percentiles or depths without a separately justified method.

**Deliverable:** A separately identified layer retaining its actual depth,
statistical meaning, units, and provenance. Expose unavailable target-depth
uncertainty explicitly if no valid transformation is established.

**Verification and closure:** Known inputs check the documented representation and
missing-data behavior. A live check verifies uncertainty metadata and inputs.
Unsupported combinations remain explicit; missing required evidence prevents
closure rather than being replaced by source spread.

**M4 closure:** Exercise the derived response alongside per-source results. Report
verified multi-source behavior and any unavailable combinations. If M3 is present,
verify derived cache keys include method and participating-input identity/version,
and refreshing inputs invalidates affected derived outputs.

## Completion record

When work starts, create one record per unit (and one per 0B combination) under
`docs/verification/`. This directory and its records are future deliverables;
their mention here is not evidence that checks ran. Use this template:

```text
Unit / source-parameter combination:
Status: planned | in_progress | blocked | verification_pending | complete
Dependencies and feasibility evidence:
Implemented scope / explicit exclusions:
Decisions, formulas, and limitations:
Deterministic checks: command, expected result, actual result, evidence path
Live checks: date, request, source/version, outcome, evidence path
Regression checks and any reused evidence:
Pending checks / blockers / impact on milestone:
Acceptance decision and supporting evidence:
```

Record milestone acceptance only after required units and the milestone's
integration gate pass. Do not treat dates, plans, mock results, or the existence
of these documents as proof of completion.
