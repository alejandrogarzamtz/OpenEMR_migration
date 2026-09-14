# Care teams

OpenRM models a patient's care team as a longitudinal, named clinical resource.
Teams use the OpenEMR/HL7 states `proposed`, `active`, `suspended`, `inactive`
and `entered-in-error` and contain participants with coded roles, optional start
dates, notes and their own lifecycle.

Participants can be practitioners, organizations/facilities, or external people
such as caregivers. A practitioner may carry a facility affiliation. The staff
workspace supports team creation and state changes, participant enrollment and
reason-required inactivation. All reads and changes are patient-scoped and
audited.

Legacy import reconciles `care_teams` and `care_team_member` after patients,
practitioners and facilities. It resolves canonical references where possible,
retains original IDs and payloads in every case, derives contact display names
from `contact` and `person`, reports inserted/existing/rejected counts, and is
idempotent by legacy team and member IDs.
