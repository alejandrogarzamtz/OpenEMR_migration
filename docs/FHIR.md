# FHIR R4 interface

The compatibility API is exposed below `/fhir` and advertised by
`GET /fhir/metadata`. All 80 routes in the OpenEMR FHIR R4 legacy map have
modern contracts. They cover the clinical, scheduling, directory, document,
medication, laboratory, questionnaire, terminology, provenance and Bulk Data
resources recorded in the generated legacy API inventory. Observation
searches combine laboratory results and LOINC-coded vital signs. Patient-bound searches
require a patient compartment; Appointment, Encounter, and care-coordination
searches also support normalized FHIR status filtering. Individual reads,
searches, and missing-resource OperationOutcomes have contract coverage.

CarePlan resources expose encounter, period, coded activity, reason extension,
and Goal references for goals from the same encounter. Goal resources expose
lifecycle and latest achievement state plus due dates. CareTeam participants
resolve practitioners and facilities to `Practitioner` and `Organization`
references while retaining display-only external contacts. Source states that
require R4 normalization remain available through explicit extensions. All
patient-scoped reads and searches produce audit events.

Appointment resources retain the patient and service-location participants and
normalize scheduling states; facility access scopes are enforced for both
search and read. Encounter resources retain their patient and Appointment
references. The same facility record is exposed as an Organization and, when
it is a service site, as a Location with a managing-organization reference.
Practitioner resources include NPI, contact and primary-organization context.
Directory searches are bounded to 100 results and support the parameters listed
in the server CapabilityStatement.

Coverage resources retain subscriber, policy, group, plan, period and priority
and reference a resolvable payer Organization. DocumentReference resources
retain MIME type, encounter context, upload time and a standards-encoded SHA-256
attachment hash. Their authenticated Binary URL streams the original bytes with
the stored media type, ETag and safe filename. Document searches support exact
MIME type plus the `eq`, `gt`, `ge`, `lt`, and `le` FHIR date prefixes.
`POST /fhir/DocumentReference/$docref` accepts a FHIR Parameters patient value
and returns the matching document-reference bundle.

Each relational laboratory order is exposed as a ServiceRequest with normalized
status and priority, LOINC code, authored time, instructions, patient and
encounter. A DiagnosticReport is exposed only after at least one result exists;
it links back to the originating ServiceRequest and forward to resolvable
Observation resources. Diagnostic searches support patient, normalized status,
LOINC code and FHIR date prefixes. Specimen resources use preserved order
specimen type, location, volume and collection time and do not invent container
or accession details absent from the source record.

The active PHQ-9 and GAD-7 definitions are exposed as versioned Questionnaire
resources with their preserved legacy item wording, LOINC panel codes, required
integer answers, and explicit 0–3 bounds. QuestionnaireResponse retains the
patient, optional encounter, author, authored time, item answers, computed score
and clinical interpretation. Score and interpretation use named OpenRM
extensions because R4 QuestionnaireResponse has no native aggregate-score
element. Searches support definition code/title/status and response patient,
questionnaire canonical, and authored date.

RelatedPerson exposes normalized family and care contacts with patient,
relationship, name, contact points, address, gender and active period. OpenRM's
distinct contact role, primary/emergency flags, medical-decision authority and
permission to receive clinical information remain explicit named extensions;
they are not conflated with portal authorization. Searches require a patient
compartment and the demographics permission. Person represents an identity from
the practitioner directory and links to the corresponding resolvable
Practitioner resource; it supports bounded name, NPI and active-state searches.

Staff sessions remain valid for first-party use. Third-party applications use
SMART App Launch 2.2 standalone, EHR, patient or asymmetric backend launch with
PKCE, OIDC and patient/user/system scopes. SMART tokens are restricted to
`/fhir/*`, patient scopes are compartment-bound, and all access remains bounded
by the registered owner user's OpenRM permissions. See
`SMART_BACKEND_SERVICES.md`.

FHIR Bulk Data initiation is available for system, patient, and the explicit
`all-patients` Group scopes. Jobs are persisted, bound to the requesting
identity, expire after 24 hours, and expose authorized NDJSON files through the
status response. Cancellation is supported. Work currently completes during
initiation but follows the asynchronous `202`/`Content-Location` protocol so a
worker can be introduced without changing the client contract.

The implementation has route and behavior tests and does not claim external
certification. Deployment-profile validation, terminology expansion, optional
search parameters, and performance sizing remain environment-specific work.
