# FHIR R4 interface

The compatibility API is exposed below `/fhir` and advertised by
`GET /fhir/metadata`. It currently supports authenticated read/search for
Patient, Condition, AllergyIntolerance, MedicationStatement, and laboratory
Observation resources. Patient-scoped reads produce audit events.

The development JWT is used as a bearer token. Production rollout must replace
it with SMART on FHIR authorization, asymmetric token signing, scopes, launch
context, and conformance/Inferno validation before connecting third parties.
