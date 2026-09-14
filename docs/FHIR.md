# FHIR R4 interface

The compatibility API is exposed below `/fhir` and advertised by
`GET /fhir/metadata`. It currently supports authenticated read/search for
Patient, Condition, AllergyIntolerance, MedicationStatement, MedicationRequest,
Immunization, Observation, Appointment, Encounter, Organization, Location,
Practitioner, Coverage, DocumentReference, Binary, CarePlan, Goal, and CareTeam
resources, plus laboratory ServiceRequest and DiagnosticReport. Observation
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
MIME type plus the `eq`, `gt`, `ge`, `lt`, and `le` FHIR date prefixes. The
legacy `$docref` clinical-document generation operation remains separate parity
work; it is not claimed by the read-only document surface.

Each relational laboratory order is exposed as a ServiceRequest with normalized
status and priority, LOINC code, authored time, instructions, patient and
encounter. A DiagnosticReport is exposed only after at least one result exists;
it links back to the originating ServiceRequest and forward to resolvable
Observation resources. Diagnostic searches support patient, normalized status,
LOINC code and FHIR date prefixes. The current model does not retain specimen
identity, collection container or accession details, so Specimen remains
explicitly outside the verified surface rather than being synthesized.

The development JWT is used as a bearer token. Production rollout must replace
it with SMART on FHIR authorization, asymmetric token signing, scopes, launch
context, and conformance/Inferno validation before connecting third parties.
