# Implementation Plan: ReBridge Backend (v1)

## Overview

This plan implements the ReBridge_Backend v1 slice as a Python monorepo with three independently-installable packages following the strict one-way dependency `api → service → data`:

- `rebridge_data` — abstract interfaces + boto3-backed concrete implementations (DynamoDB, S3, SQS, KMS, EventBridge, Bedrock).
- `rebridge_service` — pure business logic (grading pipeline, routing, health cards, demand matching, review, eventing) programmed against interfaces.
- `rebridge_api` — FastAPI routers, Lambda HTTP adapter, SQS worker entrypoint, Cognito JWT auth, composition root.

Work is sequenced bottom-up: domain models and interfaces first, then the pure service layer (with property-based tests against in-memory fakes), then the boto3 data layer, then the API/worker adapters and wiring, ending with integration and smoke tests. Property tests use **Hypothesis** (minimum 100 iterations each), live in `rebridge_service/tests`, and run against in-memory fakes with no AWS calls.

## Tasks

- [x] 1. Set up monorepo structure and tooling
  - [x] 1.1 Create three-package monorepo and test harness
    - Create `rebridge_data/`, `rebridge_service/`, `rebridge_api/` packages each with `pyproject.toml`, `src/`, and `tests/` directories
    - Configure the one-way dependency: `rebridge_service` depends on `rebridge_data` interfaces; `rebridge_api` depends on `rebridge_service`
    - Add `pytest` and `hypothesis` as test dependencies; configure a shared test runner that can run each package's suite
    - Add `boto3` only to `rebridge_data` dependencies
    - _Requirements: 18.1_

- [x] 2. Define domain models, interfaces, and grade schema
  - [x] 2.1 Implement service-layer domain models
    - Add framework-free dataclasses/enums in `rebridge_service`: `ItemStatus`, `Grade`, `Defect`, `CompletenessResult`, `GradeAssessment`, `Disposition`, `RoutingDecision`, `HealthCard`, `ListingRecord`, `ReviewQueueEntry`, `BuyerPersona`, `LifecycleEvent`
    - Enforce `Grade` enum has exactly the five allowed values and confidence is a float in [0,1]
    - _Requirements: 1.6, 5.1, 5.4, 10.4, 11.1_

  - [x] 2.2 Define data-layer abstract interfaces
    - Add ABCs/Protocols in `rebridge_data`: `ItemRepository` (incl. `put_grade_if_absent`), `ReviewQueueRepository`, `ObjectStore`, `QueueClient`, `CardSigner`, `EventPublisher`, `GradingProvider`, `BuyerPersonaRepository`
    - No boto3 imports in the interface module
    - _Requirements: 1.6, 8.4_

  - [x] 2.3 Implement grade-assessment JSON schema and strict parser
    - Define the canonical JSON schema mirroring `GradeAssessment`
    - Implement a strict parser that serializes/deserializes and rejects non-conforming JSON
    - _Requirements: 5.6_

  - [x]* 2.4 Write property test for grade-assessment schema round-trip
    - **Property 7: Grade-assessment schema invariant and parse round-trip**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

- [x] 3. Build in-memory fakes for the data-layer interfaces
  - [x] 3.1 Implement in-memory fakes for all data-layer interfaces
    - Provide in-memory implementations of `ItemRepository`, `ReviewQueueRepository`, `ObjectStore`, `CardSigner`, `EventPublisher`, `GradingProvider`, `BuyerPersonaRepository` in `rebridge_service/tests`
    - Fakes back property and unit tests without AWS calls
    - _Requirements: 1.6, 8.4_

- [x] 4. Implement ItemService (items, presign, listings)
  - [x] 4.1 Implement item creation and retrieval
    - Create items from order-scan or manual context with a unique id and status CREATED
    - Reject creation requests with missing required fields, naming the field
    - Aggregate-retrieve an item with status and exactly the persisted GRADE/CARD/DECISION/LISTING facets; not-found error for unknown ids
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x]* 4.2 Write property test for item creation invariant
    - **Property 1: Item creation invariant**
    - **Validates: Requirements 1.1, 1.2**

  - [x]* 4.3 Write property test for missing-field rejection
    - **Property 2: Missing required field is rejected with field identified**
    - **Validates: Requirements 1.3**

  - [x]* 4.4 Write property test for facet retrieval
    - **Property 3: Item retrieval returns exactly the persisted facets**
    - **Validates: Requirements 1.4**

  - [x] 4.5 Implement presigned photo-upload URL request validation
    - Issue one presigned S3 PUT URL per requested slot with a 5-minute TTL via `ObjectStore`
    - Never proxy photo bytes through the API; reject counts outside the 2–4 range with a range error
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x]* 4.6 Write property test for presigned URL count
    - **Property 4: Presigned URL count matches valid request and rejects out-of-range counts**
    - **Validates: Requirements 2.1, 2.4**

  - [x] 4.7 Implement listing CRUD with grade-required guard
    - Create/update/get/delete a LISTING facet; reject listing creation for an item with no grade
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 4.8 Write property test for listing round-trip and grade guard
    - **Property 5: Listing round-trip and grade-required guard**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

- [x] 5. Implement Quality Precheck
  - [x] 5.1 Implement blur and lighting assessment
    - Assess each photo for blur (variance-of-Laplacian) and exposure before grading
    - On failure, set status RETAKE_REQUIRED and return a retake prompt identifying the failing photo
    - _Requirements: 4.1, 4.2, 4.3_

  - [x]* 5.2 Write property test for quality precheck gating
    - **Property 6: Quality precheck gates grading**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 6. Implement Grading Engine and Model Cascade
  - [x] 6.1 Implement GradingEngine with cascade, timeout, and JSON retry
    - Invoke the injected `GradingProvider` list in order (Nova Lite → Claude vision), enforcing a per-call timeout
    - Parse responses with the strict schema parser; retry invalid JSON up to 2×; fall through to the next provider on timeout/error; return the first schema-conforming result
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 8.1, 8.2, 8.4_

  - [x]* 6.2 Write property test for cascade ordering and fallback
    - **Property 13: Model cascade ordering and fallback**
    - **Validates: Requirements 8.1, 8.2**

  - [x]* 6.3 Write property test for provider seam substitutability
    - **Property 15: Provider seam substitutability**
    - **Validates: Requirements 8.4**

- [x] 7. Implement Confidence Gate
  - [x] 7.1 Implement confidence gate decision
    - Compare `Confidence_Score` against the configured `Confidence_Threshold`; read threshold from config with default 0.80
    - Return auto-continue vs review decision
    - _Requirements: 6.1, 6.2, 6.3_

  - [x]* 7.2 Write unit tests for confidence threshold configuration
    - Test default threshold value of 0.80 and exact boundary behavior at the threshold
    - _Requirements: 6.3_

- [x] 8. Implement idempotency-key derivation
  - [x] 8.1 Implement deterministic idempotency-key derivation
    - Derive the key from item identifier and photo-set hash
    - _Requirements: 7.2_

  - [x]* 8.2 Write property test for idempotency-key determinism
    - **Property 10: Idempotency-key determinism**
    - **Validates: Requirements 7.2**

- [x] 9. Implement the GradingPipeline orchestration
  - [x] 9.1 Implement GradingPipeline run flow
    - Orchestrate: idempotency check (`put_grade_if_absent`) → fetch images → QualityPrecheck → catalog context → GradingEngine → strict parse → ConfidenceGate → persist GRADE → branch (make card + invoke router, or enqueue review with priority `est_value * (1 - confidence)`)
    - On confidence ≥ threshold persist and continue to event emission; on confidence < threshold set PENDING_REVIEW and enqueue review
    - On non-conforming JSON after retries, set review state; on total cascade failure set PENDING_REVIEW
    - _Requirements: 5.7, 6.1, 6.2, 7.3, 8.3_

  - [x]* 9.2 Write property test for confidence gate persistence/enqueue
    - **Property 9: Confidence gate decision boundary**
    - **Validates: Requirements 6.1, 6.2**

  - [x]* 9.3 Write property test for pipeline idempotency
    - **Property 11: Pipeline processing is idempotent**
    - **Validates: Requirements 7.3**

  - [x]* 9.4 Write property test for non-conforming response routing
    - **Property 8: Non-conforming model response routes to review**
    - **Validates: Requirements 5.7**

  - [x]* 9.5 Write property test for total cascade failure routing
    - **Property 14: Total cascade failure routes to review**
    - **Validates: Requirements 8.3**

- [x] 10. Implement the Routing Agent
  - [x] 10.1 Implement routing tools (PriceEstimator, CostModel, DemandProbe)
    - Price band from a category/grade/age CSV table; per-route handling costs; seeded neighborhood demand index
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 10.2 Implement RoutingAgent strategies and disposition selection
    - Implement a `RoutingStrategy` interface with `AgentRoutingStrategy` and `PureFunctionRoutingStrategy` producing identical output structure
    - Select argmax-margin disposition among {RESELL, REFURB, P2P, DONATE} with value > cost; tie-break toward faster customer outcome (P2P over RESELL); select DONATE when no non-donate path has value > cost
    - Persist DECISION with disposition, price, and a rationale stating value, cost, and margin
    - _Requirements: 10.4, 10.5, 10.6, 10.7, 10.8_

  - [x]* 10.3 Write property test for optimal disposition selection
    - **Property 16: Optimal disposition selection**
    - **Validates: Requirements 10.4, 10.5, 10.6**

  - [x]* 10.4 Write property test for decision rationale contents
    - **Property 17: Decision rationale exposes the unit economics**
    - **Validates: Requirements 10.7**

  - [x]* 10.5 Write property test for agent/pure-function equivalence
    - **Property 18: Agent and pure-function routing equivalence**
    - **Validates: Requirements 10.8**

- [x] 11. Implement the Health Card Service
  - [x] 11.1 Implement card render, sign, persist, and verify
    - Render the card (grade, annotated photos, plain-language defect summary, verification date, warranty stance)
    - Sign canonical payload `card_id | item_id | grade | graded_at` with HMAC-SHA256 via `CardSigner`; persist CARD with signature + QR target
    - Verify by recompute-and-compare, returning verified (with contents) or tampered
    - _Requirements: 11.1, 11.2, 11.3, 12.1, 12.2, 12.3_

  - [x]* 11.2 Write property test for sign/verify round-trip
    - **Property 19: Health Card sign/verify round-trip**
    - **Validates: Requirements 11.1, 11.2, 11.3, 12.1, 12.2**

  - [x]* 11.3 Write property test for tampered card detection
    - **Property 20: Tampered card detection**
    - **Validates: Requirements 12.3**

- [x] 12. Implement the Demand Matching Engine
  - [x] 12.1 Implement candidate filtering, scoring, and ranking
    - Retrieve candidates from `BuyerPersonaRepository` filtered by geo radius + category + wishlist/cart signal
    - Score with weighted (intent, lifecycle, geo, price-sensitivity); rank descending; apply anti-cannibalization weighting favoring deal-seeker/price-balker personas
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.6_

  - [x] 12.2 Implement top-N push, PDP shelf upsert, and MATCHED emission
    - Notify exactly the top min(N, count) buyers; upsert the item onto the Second-Chance PDP shelf; emit MATCHED
    - _Requirements: 13.5, 15.4_

  - [x]* 12.3 Write property test for candidate filtering
    - **Property 21: Demand candidate filtering**
    - **Validates: Requirements 13.1**

  - [x]* 12.4 Write property test for score-ordered ranking with bias
    - **Property 22: Ranking is a score-ordered permutation with anti-cannibalization bias**
    - **Validates: Requirements 13.2, 13.3, 13.4**

  - [x]* 12.5 Write property test for top-N push and placement
    - **Property 23: Top-N push and placement**
    - **Validates: Requirements 13.5, 15.4**

- [x] 13. Implement the Review Console Service
  - [x] 13.1 Implement review queue listing and confirm/override actions
    - List pending grades ordered by value × uncertainty (value × (1 − confidence)) descending
    - Confirm persists grade as confirmed and sets status GRADED; override persists the overriding grade, sets GRADED, and stores a training signal; both remove the item from the queue
    - Reject confirm/override for items not in the queue with a not-pending-review error
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x]* 13.2 Write property test for review queue priority ordering
    - **Property 24: Review queue priority ordering**
    - **Validates: Requirements 14.1**

  - [x]* 13.3 Write property test for confirm/override transitions
    - **Property 25: Review confirm and override transitions**
    - **Validates: Requirements 14.2, 14.3**

  - [x]* 13.4 Write property test for non-pending review rejection
    - **Property 26: Review action on non-pending item is rejected**
    - **Validates: Requirements 14.4**

- [x] 14. Implement the Eventing Service
  - [x] 14.1 Implement lifecycle event emission
    - Emit GRADED, ROUTED, LISTED, MATCHED, SOLD through `EventPublisher`, each identifying the item (and disposition for ROUTED)
    - Wire emission points into item grading-confirm, routing persist, listing create, demand push, and sale
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x]* 14.2 Write property test for lifecycle event emission
    - **Property 27: Lifecycle transitions emit their events**
    - **Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5**

- [x] 15. Checkpoint - service layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Implement the boto3 data layer (`rebridge_data` concretes)
  - [x] 16.1 Implement DynamoItemRepository with single-table model and GSIs
    - Single-table `PK`/`SK` with META/GRADE/CARD/DECISION/LISTING facets; `put_grade_if_absent` as a conditional write; GSI1 marketplace, GSI2 geo, GSI3 review queue
    - _Requirements: 1.6, 3.3, 7.3, 13.1_

  - [x] 16.2 Implement DynamoReviewQueueRepository
    - Enqueue with priority value × (1 − confidence); list pending ordered by priority desc; get/resolve
    - _Requirements: 14.1_

  - [x] 16.3 Implement S3ObjectStore presign and get
    - Presigned PUT URLs with 300-second TTL; object byte retrieval
    - _Requirements: 2.1, 2.2_

  - [x] 16.4 Implement SqsQueueClient
    - Send grading messages to the SQS grading queue
    - _Requirements: 7.1_

  - [x] 16.5 Implement KmsCardSigner
    - HMAC-SHA256 sign/verify using a KMS-managed key
    - _Requirements: 11.2_

  - [x] 16.6 Implement EventBridgePublisher
    - Publish lifecycle events to the configured EventBridge bus
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 16.7 Implement SeededBuyerPersonaRepository
    - Seeded buyer personas as the only demand source in v1
    - _Requirements: 13.6, 18.2_

  - [x] 16.8 Implement Bedrock Nova Lite and Claude vision GradingProviders
    - Two `GradingProvider` implementations behind the cascade seam, returning raw model responses for strict parsing
    - _Requirements: 8.1, 8.2, 8.4_

  - [x] 16.9 Implement Geohash5 location encoding helper
    - Encode location inputs to a five-character geohash; persist no precision finer than Geohash5
    - _Requirements: 17.1, 17.2_

  - [x]* 16.10 Write property test for location precision bound
    - **Property 29: Location precision is bounded to Geohash5**
    - **Validates: Requirements 17.1, 17.2**

  - [x]* 16.11 Write data-layer integration tests with moto/local DynamoDB
    - Verify single-table reads/writes, GSI queries, conditional idempotent write, presign TTL, and KMS sign/verify smoke
    - _Requirements: 1.6, 2.2, 7.3, 11.2_

- [x] 17. Implement the API layer (`rebridge_api`)
  - [x] 17.1 Implement Pydantic models and FastAPI routers
    - Map HTTP routes to service calls per the API contract: `/items`, `/items/{id}/photos:presign`, `/items/{id}/grade` (202 + Idempotency-Key), `/items/{id}`, `/items/{id}/route`, listing CRUD, `/marketplace`, `/listings/{id}/buy` (simulated checkout emitting SOLD)
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 3.1, 3.2, 3.3, 3.4, 7.1, 10.1, 15.3, 15.5, 18.4_

  - [x] 17.2 Implement Cognito JWT auth dependency for private routes
    - Require a valid Cognito-issued JWT on private routes; reject missing/invalid tokens with 401
    - _Requirements: 16.1, 16.2_

  - [x]* 17.3 Write property test for private-route JWT enforcement
    - **Property 28: Private routes require a valid JWT**
    - **Validates: Requirements 16.1, 16.2**

  - [x] 17.4 Implement the public card verification route
    - Serve `GET /cards/{card_id}/verify?sig=` without authentication; return verified/tampered
    - _Requirements: 12.4, 16.3_

  - [x] 17.5 Implement the Lambda HTTP adapter
    - Host FastAPI on Lambda (Mangum-style) behind API Gateway
    - _Requirements: 16.1_

  - [x] 17.6 Implement the SQS grading worker entrypoint with retry/DLQ
    - Parse the SQS record and call `GradingPipeline.run(...)`; retry transient failures up to 2× with jittered backoff before routing to the DLQ
    - _Requirements: 7.1, 7.4_

  - [x]* 17.7 Write property test for retry-then-DLQ bound
    - **Property 12: Retry-then-DLQ bound**
    - **Validates: Requirements 7.4**

  - [x] 17.8 Implement the composition root (wiring.py)
    - Construct concrete data-layer implementations once and inject them into service classes; read config (confidence threshold default 0.80, model timeout, top-N, table name, KMS key id, queue url, bucket)
    - _Requirements: 6.3, 8.4_

  - [x]* 17.9 Write API-layer unit/smoke tests
    - Use FastAPI `TestClient` with a container wired to in-memory fakes: not-found on unknown item (1.5), public verify reachable without auth (16.3), grade-required guard (3.5), config defaults (6.3)
    - _Requirements: 1.5, 3.5, 6.3, 16.3_

- [x] 18. Final integration, smoke, and scope-boundary tests
  - [x]* 18.1 Write S3→SQS→Lambda trigger integration test
    - Verify upload-completion triggers grading through the S3 event → SQS → worker path
    - _Requirements: 7.1_

  - [x]* 18.2 Write DLQ→alarm integration test
    - Verify messages exceeding max-receive route to the DLQ and raise a CloudWatch alarm
    - _Requirements: 7.4, 7.5_

  - [x]* 18.3 Write grading-latency p99 measurement test
    - Measure end-to-end persisted-grade latency against the 4-second p99 budget for passed photo sets
    - _Requirements: 9.1_

  - [x]* 18.4 Write scope-boundary smoke tests
    - Assert seeded buyer repository is the only demand source, prevention is data-capture shape only, and fraud ML / donation logistics / live payments are absent (buy is simulated)
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

- [x] 19. Final checkpoint - ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirement sub-clauses for traceability.
- Property tests use Hypothesis (minimum 100 iterations), live in `rebridge_service/tests`, run against in-memory fakes, and each correctness property is implemented by exactly one property-based test tagged `# Feature: rebridge-backend, Property {number}: {property_text}`.
- Data/infrastructure concerns (DynamoDB, S3, SQS, KMS, EventBridge wiring, p99 latency) are validated with integration/smoke tests rather than property tests.
- Checkpoints (tasks 15 and 19) ensure incremental validation at the service-layer and full-system boundaries.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["3.1", "2.4"] },
    { "id": 3, "tasks": ["4.1", "5.1", "6.1", "7.1", "8.1", "10.1", "11.1", "13.1", "14.1"] },
    { "id": 4, "tasks": ["4.5", "9.1", "10.2", "12.1", "4.2", "4.4", "5.2", "6.2", "6.3", "7.2", "8.2", "11.2", "11.3", "13.2", "14.2"] },
    { "id": 5, "tasks": ["4.7", "12.2", "9.2", "9.3", "9.4", "9.5", "10.3", "10.4", "10.5", "13.3", "13.4"] },
    { "id": 6, "tasks": ["4.3", "4.6", "4.8", "12.3", "12.4", "12.5"] },
    { "id": 7, "tasks": ["16.1", "16.2", "16.3", "16.4", "16.5", "16.6", "16.7", "16.8", "16.9"] },
    { "id": 8, "tasks": ["16.10", "16.11", "17.1", "17.2", "17.4", "17.5", "17.6"] },
    { "id": 9, "tasks": ["17.3", "17.7", "17.8"] },
    { "id": 10, "tasks": ["17.9", "18.1", "18.2", "18.3", "18.4"] }
  ]
}
```
