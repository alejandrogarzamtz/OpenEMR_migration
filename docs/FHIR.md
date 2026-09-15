# FHIR R4 interface

The compatibility API is exposed below `/fhir` and advertised by
`GET /fhir/metadata`. It currently supports authenticated read/search for
Patient, Condition, AllergyIntolerance, MedicationStatement, MedicationRequest,
Immunization, Observation, Appointment, Encounter, Organization, Location,
Practitioner, Coverage, DocumentReference, Binary, CarePlan, Goal, and CareTeam
resources, plus laboratory ServiceRequest/DiagnosticReport and scored
Questionnaire/QuestionnaireResponse. Observation
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

Staff sessions remain valid for first-party use. Pre-authorized third-party
backend integrations use SMART App Launch 2.2 asymmetric client authentication,
short-lived scope-bounded tokens, persistent assertion replay protection,
introspection and revocation. SMART tokens are restricted to `/fhir/*` and are
also bounded by the registered owner user's OpenRM permissions. See
`SMART_BACKEND_SERVICES.md`. Interactive app launch, PKCE/OpenID Connect,
patient/user context, Bulk Data export and formal Inferno validation remain.
