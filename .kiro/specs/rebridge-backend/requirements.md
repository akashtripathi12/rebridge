# Requirements Document

## Introduction

ReBridge is an AI grading, smart routing, and Product Health Card engine for returned and pre-owned items. This document specifies the **backend feature** for v1 (the 48-hour build), covering the fully-built core slice of grading → Product Health Card → smart routing, plus demand matching over seeded buyer data, eventing, and a human review console.

The backend exposes a FastAPI service (deployed on AWS Lambda) that manages the item lifecycle, runs an asynchronous grading pipeline backed by a vision language model cascade, signs and verifies tamper-evident Product Health Cards, computes unit-economics-driven routing decisions, ranks candidate buyers from seeded demand signals, and emits lifecycle events.

**v1 scope discipline:**
- The grading → Health Card → routing slice is the fully-built core.
- Demand Matching operates on seeded/mocked buyer personas (ranking intelligence demonstrated, not live integration).
- Out of scope for v1: fraud detection ML, the prevention model (Pillar 5), donation logistics execution, and live payment processing. Where Pillar 5 prevention data capture is referenced, only the data-capture shape is designed, not built.

## Glossary

- **ReBridge_Backend**: The complete backend system comprising the API service and asynchronous workers described in this document.
- **Item_API**: The component that manages item lifecycle operations, presigned upload URL issuance, status/grade/card/decision retrieval, and listing CRUD.
- **Grading_Pipeline**: The asynchronous component that performs image-quality precheck, vision language model grading, strict-JSON parsing, confidence gating, persistence, and event emission.
- **Quality_Precheck**: The sub-component of the Grading_Pipeline that assesses photo blur and lighting before grading.
- **Grading_Engine**: The vision language model invocation component that produces a grade assessment from item photos (Engine A).
- **Model_Cascade**: The ordered set of vision models invoked by the Grading_Engine, beginning with Bedrock Nova Lite and falling back to Claude vision.
- **Routing_Agent**: The component that computes unit economics and selects a disposition decision (Pillar 2).
- **Price_Estimator**: The Routing_Agent tool that estimates a recoverable price band from category, grade, and age.
- **Cost_Model**: The Routing_Agent tool that estimates grading, logistics, and relist costs.
- **Demand_Probe**: The Routing_Agent tool that returns a seeded neighborhood demand index.
- **Health_Card_Service**: The component that renders, signs, and verifies Product Health Cards (Pillar 3).
- **Demand_Matching_Engine**: The component that scores and ranks seeded candidate buyers and updates buyer-facing placement (Engine B, Pillar 4).
- **Review_Console_API**: The component that exposes the human review queue and records confirm/override actions.
- **Event_Publisher**: The component that emits lifecycle events (GRADED, ROUTED, LISTED, MATCHED, SOLD).
- **Item**: A returned or pre-owned product record identified by an item identifier, persisted with META, GRADE, CARD, DECISION, and LISTING facets.
- **Product_Health_Card**: A QR-verifiable record containing the grade, annotated photos, plain-language defect summary, verification date, and warranty stance.
- **Grade**: A condition classification with one of the values: Like New, Very Good, Good, Acceptable, Unsellable.
- **Confidence_Score**: A numeric value between 0 and 1 inclusive representing the Grading_Engine's certainty in a grade assessment.
- **Confidence_Threshold**: The configurable boundary value (default 0.80) used to gate auto-continue versus human review.
- **Idempotency_Key**: A deterministic key derived from the item identifier and photo-set hash used to deduplicate pipeline processing.
- **Review_Queue**: The ordered set of low-confidence grade records awaiting human action, ordered by value multiplied by uncertainty in descending order.
- **JWT**: A JSON Web Token issued by Cognito used to authenticate private routes.
- **Geohash5**: A five-character geohash used to represent approximate location without exact address.

## Requirements

### Requirement 1: Item Creation and Lifecycle

**User Story:** As a seller or returns agent, I want to create item records from an order scan or manual context, so that each returned or pre-owned item can be tracked through grading, carding, and routing.

#### Acceptance Criteria

1. WHEN a client submits a valid item creation request with order-scan context, THE Item_API SHALL create an Item record with a unique item identifier and an initial status of CREATED.
2. WHEN a client submits a valid item creation request with manual context, THE Item_API SHALL create an Item record with a unique item identifier and an initial status of CREATED.
3. IF an item creation request omits a required field, THEN THE Item_API SHALL reject the request with a validation error identifying the missing field.
4. WHEN a client requests an Item by item identifier, THE Item_API SHALL return the Item status, and the grade, card, decision, and listing facets that exist for that Item.
5. IF a client requests an Item by an item identifier that does not exist, THEN THE Item_API SHALL return a not-found error.
6. THE Item_API SHALL persist each Item using the single-table model with partition key ITEM#<item_identifier> and the META, GRADE, CARD, DECISION, and LISTING sort-key facets.

### Requirement 2: Presigned Photo Upload

**User Story:** As an item owner, I want to upload item photos directly to storage, so that I can submit 2 to 4 photos for grading without the API handling the image bytes.

#### Acceptance Criteria

1. WHEN a client requests photo upload URLs for an existing Item, THE Item_API SHALL return a presigned S3 upload URL for each requested photo slot.
2. THE Item_API SHALL issue presigned upload URLs that expire 5 minutes after issuance.
3. THE Item_API SHALL NOT proxy photo bytes through the API request or response path.
4. IF a client requests fewer than 2 or more than 4 photo upload URLs for a single grading submission, THEN THE Item_API SHALL reject the request with a validation error stating the allowed range of 2 to 4 photos.

### Requirement 3: Listing Management

**User Story:** As a small seller, I want to create and manage listings for graded items, so that recoverable inventory becomes available to buyers.

#### Acceptance Criteria

1. WHEN a client submits a valid listing creation request for an Item, THE Item_API SHALL create a LISTING facet associated with that Item.
2. WHEN a client submits a valid listing update request for an existing listing, THE Item_API SHALL apply the requested changes to the LISTING facet.
3. WHEN a client requests a listing by item identifier, THE Item_API SHALL return the current LISTING facet for that Item.
4. WHEN a client submits a listing deletion request for an existing listing, THE Item_API SHALL remove the LISTING facet for that Item.
5. IF a client submits a listing creation request for an Item that has no grade, THEN THE Item_API SHALL reject the request with an error stating that a grade is required before listing.

### Requirement 4: Image Quality Precheck

**User Story:** As an item owner, I want unusable photos flagged before grading, so that I can retake them and receive an accurate grade.

#### Acceptance Criteria

1. WHEN a photo set is submitted for grading, THE Quality_Precheck SHALL assess each photo for blur and lighting adequacy before invoking the Grading_Engine.
2. IF a photo fails the blur or lighting assessment, THEN THE Quality_Precheck SHALL set the Item status to RETAKE_REQUIRED and return a retake prompt identifying the failing photo.
3. WHILE all photos in a submitted set pass the blur and lighting assessment, THE Grading_Pipeline SHALL proceed to invoke the Grading_Engine.

### Requirement 5: AI Grading

**User Story:** As an item owner, I want an instant condition assessment from my photos, so that I get a grade, defect list, and completeness check without manual inspection.

#### Acceptance Criteria

1. WHEN the Grading_Engine assesses a photo set that passed the Quality_Precheck, THE Grading_Engine SHALL produce a Grade with one of the values Like New, Very Good, Good, Acceptable, or Unsellable.
2. WHEN the Grading_Engine produces a grade assessment, THE Grading_Engine SHALL include a defect list in which each defect has a location and a severity.
3. WHEN the Grading_Engine produces a grade assessment, THE Grading_Engine SHALL include a completeness result comparing the observed item against the catalog.
4. WHEN the Grading_Engine produces a grade assessment, THE Grading_Engine SHALL include a Confidence_Score between 0 and 1 inclusive.
5. WHEN the Grading_Engine produces a grade assessment, THE Grading_Engine SHALL include a plain-language summary of the item condition.
6. WHEN the Grading_Engine returns a model response, THE Grading_Pipeline SHALL parse the response as strict JSON conforming to the grade assessment schema.
7. IF the Grading_Engine returns a response that does not parse as schema-conforming JSON, THEN THE Grading_Pipeline SHALL set the Item to a review state.

### Requirement 6: Confidence Gating

**User Story:** As an operations owner, I want low-confidence grades routed to human review, so that only sufficiently certain grades auto-continue.

#### Acceptance Criteria

1. WHEN a grade assessment has a Confidence_Score greater than or equal to the Confidence_Threshold, THE Grading_Pipeline SHALL persist the grade and continue to event emission automatically.
2. IF a grade assessment has a Confidence_Score less than the Confidence_Threshold, THEN THE Grading_Pipeline SHALL set the Item status to PENDING_REVIEW and add the grade to the Review_Queue.
3. THE Grading_Pipeline SHALL read the Confidence_Threshold from configuration with a default value of 0.80.

### Requirement 7: Asynchronous Pipeline Processing and Idempotency

**User Story:** As an operations owner, I want grading processed asynchronously and reliably, so that uploads trigger grading without blocking and duplicate processing is prevented.

#### Acceptance Criteria

1. WHEN a photo set upload completes in S3, THE Grading_Pipeline SHALL begin processing through an S3 event to SQS to Lambda worker path.
2. THE Grading_Pipeline SHALL derive an Idempotency_Key from the item identifier and the photo-set hash for each grading submission.
3. IF a grading submission arrives with an Idempotency_Key that has already produced a persisted grade, THEN THE Grading_Pipeline SHALL skip reprocessing and retain the existing grade.
4. IF a Grading_Pipeline worker invocation fails, THEN THE Grading_Pipeline SHALL retry the invocation up to 2 times using jittered backoff before routing the message to the dead-letter queue.
5. WHEN a message is routed to the dead-letter queue, THE Grading_Pipeline SHALL raise an operational alarm.

### Requirement 8: Model Cascade and Timeout Handling

**User Story:** As an operations owner, I want the grading model to fail over gracefully, so that a single model timeout does not block grading or leave the item in an undefined state.

#### Acceptance Criteria

1. WHEN the Grading_Engine grades a photo set, THE Grading_Engine SHALL invoke the Model_Cascade beginning with Bedrock Nova Lite.
2. IF the Bedrock Nova Lite invocation times out or returns an error, THEN THE Grading_Engine SHALL fall back to the Claude vision model in the Model_Cascade.
3. IF every model in the Model_Cascade fails or times out, THEN THE Grading_Pipeline SHALL set the Item status to PENDING_REVIEW.
4. THE Grading_Engine SHALL invoke vision models through a provider seam that allows substitution of an alternate provider without changing the grade assessment schema.

### Requirement 9: Grading Performance

**User Story:** As an item owner, I want grading to complete quickly, so that I receive a near-instant result.

#### Acceptance Criteria

1. WHEN a photo set that passed the Quality_Precheck is graded, THE Grading_Pipeline SHALL produce a persisted grade within 4 seconds at the 99th percentile of grading submissions.

### Requirement 10: Smart Routing Decision

**User Story:** As a seller, I want the system to decide how to dispose of each graded item using unit economics, so that I recover the maximum value with a clear rationale.

#### Acceptance Criteria

1. WHEN an Item has a persisted grade, THE Routing_Agent SHALL compute a recoverable price band using the Price_Estimator from category, Grade, and item age.
2. WHEN the Routing_Agent evaluates an Item, THE Routing_Agent SHALL compute total handling cost using the Cost_Model including grading cost, logistics cost, and relist cost.
3. WHEN the Routing_Agent evaluates an Item, THE Routing_Agent SHALL obtain a seeded neighborhood demand index using the Demand_Probe.
4. WHEN the Routing_Agent selects a disposition, THE Routing_Agent SHALL choose the path with the maximum margin among the paths where recovered value is greater than total handling cost, selecting from resell, refurbish, peer-to-peer, and donate.
5. WHERE two or more disposition paths have equal margin, THE Routing_Agent SHALL select the path that produces the faster customer outcome.
6. IF the recovered value of every non-donate path is less than or equal to total handling cost, THEN THE Routing_Agent SHALL select the donate path.
7. WHEN the Routing_Agent produces a decision, THE Routing_Agent SHALL persist a DECISION facet containing the selected disposition, a price, and a one-line rationale stating the recovered value, total handling cost, and resulting margin.
8. THE Routing_Agent SHALL produce identical decision output structure whether executed through the agent framework or the pure-function fallback.

### Requirement 11: Product Health Card Rendering and Signing

**User Story:** As a seller, I want a tamper-evident Product Health Card generated for each graded item, so that the next buyer can trust the item condition.

#### Acceptance Criteria

1. WHEN an Item has a persisted grade, THE Health_Card_Service SHALL render a Product_Health_Card containing the Grade, annotated photos, a plain-language defect summary, a verification date, and a warranty stance.
2. WHEN the Health_Card_Service renders a Product_Health_Card, THE Health_Card_Service SHALL sign the card using HMAC-SHA256 with a key managed by KMS.
3. WHEN the Health_Card_Service signs a Product_Health_Card, THE Health_Card_Service SHALL persist the CARD facet with the signature and a QR target reference.

### Requirement 12: Product Health Card Public Verification

**User Story:** As the next buyer, I want to scan a Health Card and verify it, so that I can confirm the record is authentic and untampered.

#### Acceptance Criteria

1. WHEN a client requests verification of a Product_Health_Card at the public verification endpoint, THE Health_Card_Service SHALL recompute the HMAC-SHA256 signature and compare it against the stored signature.
2. WHEN a verification request presents a Product_Health_Card whose recomputed signature matches the stored signature, THE Health_Card_Service SHALL return a verified result with the card contents.
3. IF a verification request presents a Product_Health_Card whose recomputed signature does not match the stored signature, THEN THE Health_Card_Service SHALL return a tampered result.
4. THE Health_Card_Service SHALL serve the public verification endpoint without requiring authentication.

### Requirement 13: Demand Matching

**User Story:** As a seller, I want graded items matched and ranked against likely buyers, so that recoverable items reach interested buyers proactively.

#### Acceptance Criteria

1. WHEN a LISTED event is emitted for an Item, THE Demand_Matching_Engine SHALL retrieve candidate buyers from seeded buyer personas filtered by geo, category, and wishlist or cart signals.
2. WHEN the Demand_Matching_Engine scores a candidate buyer, THE Demand_Matching_Engine SHALL compute a score from intent, lifecycle, geo, and price-sensitivity weights.
3. WHEN the Demand_Matching_Engine has scored candidate buyers, THE Demand_Matching_Engine SHALL rank the candidate buyers in descending score order.
4. WHEN the Demand_Matching_Engine ranks candidate buyers, THE Demand_Matching_Engine SHALL apply anti-cannibalization weighting that favors deal-seeker and price-balker personas.
5. WHEN the Demand_Matching_Engine has produced a ranking, THE Demand_Matching_Engine SHALL push a proactive notification to the top-N ranked buyers and upsert the Item onto the Second-Chance PDP shelf.
6. THE Demand_Matching_Engine SHALL operate over seeded buyer persona data in v1.

### Requirement 14: Human Review Console

**User Story:** As a reviewer, I want a prioritized queue of low-confidence grades with confirm and override actions, so that uncertain high-value grades are resolved and corrections feed future training.

#### Acceptance Criteria

1. WHEN a reviewer requests the Review_Queue, THE Review_Console_API SHALL return pending grade records ordered by value multiplied by uncertainty in descending order.
2. WHEN a reviewer confirms a grade, THE Review_Console_API SHALL persist the grade as confirmed and set the Item status to GRADED.
3. WHEN a reviewer overrides a grade, THE Review_Console_API SHALL persist the overriding grade, set the Item status to GRADED, and store the override as a training signal.
4. IF a reviewer submits a confirm or override action for an Item that is not in the Review_Queue, THEN THE Review_Console_API SHALL reject the action with an error stating the Item is not pending review.

### Requirement 15: Lifecycle Eventing

**User Story:** As a downstream consumer, I want lifecycle events emitted at each stage, so that routing, matching, and analytics can react to item progress.

#### Acceptance Criteria

1. WHEN an Item grade is persisted and confirmed, THE Event_Publisher SHALL emit a GRADED event identifying the Item.
2. WHEN the Routing_Agent persists a decision, THE Event_Publisher SHALL emit a ROUTED event identifying the Item and the selected disposition.
3. WHEN a listing is created for an Item, THE Event_Publisher SHALL emit a LISTED event identifying the Item.
4. WHEN the Demand_Matching_Engine pushes to ranked buyers, THE Event_Publisher SHALL emit a MATCHED event identifying the Item.
5. WHEN an Item is sold, THE Event_Publisher SHALL emit a SOLD event identifying the Item.

### Requirement 16: Authentication and Authorization

**User Story:** As a platform owner, I want private routes protected and public verification open, so that item data is secured while buyers can still verify Health Cards.

#### Acceptance Criteria

1. WHEN a client calls a private route, THE ReBridge_Backend SHALL require a valid Cognito-issued JWT.
2. IF a private-route request presents a missing or invalid JWT, THEN THE ReBridge_Backend SHALL reject the request with an unauthorized error.
3. THE Health_Card_Service SHALL allow the public verification endpoint to be called without a JWT.

### Requirement 17: Data Minimization

**User Story:** As a privacy owner, I want location stored coarsely, so that buyer and item records never contain exact addresses.

#### Acceptance Criteria

1. WHEN the ReBridge_Backend stores a location for matching, THE ReBridge_Backend SHALL store a Geohash5 value.
2. THE ReBridge_Backend SHALL store location data at a precision no finer than Geohash5.

### Requirement 18: V1 Scope Boundaries

**User Story:** As a project owner, I want roadmap capabilities excluded from v1, so that the team builds the grading-to-routing core fully without scope creep.

#### Acceptance Criteria

1. THE ReBridge_Backend SHALL implement the grading, Product Health Card, and routing slice as fully operational v1 capabilities.
2. THE Demand_Matching_Engine SHALL operate on seeded buyer persona data and SHALL exclude live buyer-data integration in v1.
3. WHERE Pillar 5 prevention is referenced, THE ReBridge_Backend SHALL capture only the prevention data-capture shape and SHALL exclude prevention model execution in v1.
4. THE ReBridge_Backend SHALL exclude fraud detection machine learning, donation logistics execution, and live payment processing from v1.
