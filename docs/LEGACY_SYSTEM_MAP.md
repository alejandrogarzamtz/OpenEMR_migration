# Legacy OpenEMR system map

This document describes the preserved reference application in
`openemr-legacy/`. It is an inventory, not a claim that the replacement has
parity. The source snapshot identifies itself as OpenEMR **8.4.0-dev**, database
revision **543**, ACL revision **13**.

## Technology and runtime

| Concern | Legacy implementation |
|---|---|
| Server | PHP 8.3+, normally Apache; CLI entry points in `bin/` |
| Database | MySQL/MariaDB; 281 base tables in `sql/database.sql` |
| Data access | ADODB, raw SQL, Doctrine DBAL/ORM and service/repository classes |
| UI | Server-rendered PHP, Smarty, Twig and Mustache; Bootstrap 4, jQuery, Backbone, Knockout and isolated React 15 assets |
| APIs | Standard REST, portal REST and FHIR R4/US Core route maps; OAuth2/OIDC/SMART support |
| Authentication | PHP sessions for the application/portal; OAuth2 bearer tokens for APIs; optional LDAP, MFA and trusted-user flows |
| Authorization | phpGACL ARO/ACO/AXO tables plus service, route and patient-compartment checks |
| Files | Document metadata in MySQL; local/flysystem storage, categories, versions and legal-signature metadata |
| Packaging | Composer and npm/webpack; PHPUnit/Jest/Playwright-style acceptance suites; Docker images and install/upgrade scripts |

## Source layout

| Path | Responsibility |
|---|---|
| `interface/` | Primary server-rendered application: patient chart, forms, billing, reports, scheduling and administration |
| `src/` | Namespaced domain services, REST/FHIR controllers, events, commands, modules and infrastructure |
| `apis/routes/` | Standard, portal and FHIR route registries |
| `portal/` | Patient portal UI and workflows |
| `oauth2/` | OAuth2/OIDC authorization and SMART launch surfaces |
| `gacl/` | Generalized role/group/access-control implementation |
| `sql/`, `db/` | Baseline schema, upgrade patches, migrations and database tooling |
| `library/` | Shared clinical, billing, document, communication, report and utility code |
| `interface/forms/` | 35 shipped encounter/assessment form modules |
| `templates/` | Email, document and presentation templates |
| `ccdaservice/`, `ccr/` | C-CDA/CCR generation, import and validation |
| `bin/`, `src/Common/Command/` | Installation, imports, notifications and background services |
| `custom/`, `interface/modules/` | Site customization and extension/module hooks |

## Major functional modules

The product covers identity and ACL administration; facilities and providers;
patient demographics and contacts; scheduling and patient flow; encounters and
35 clinical form families; problems, allergies, medication, prescriptions,
immunization and vitals; procedures, laboratories, imaging and documents;
care plans, questionnaires and decision support; insurance, eligibility, fee
sheets, claims, X12, payments, statements and inventory; portal, messaging and
notifications; operational/clinical/financial/quality reports; FHIR, SMART,
standard and portal APIs; C-CDA/CCR/EHI export; localization, configuration,
modules, audit, background services and maintenance commands.

## Key workflows and rules

- Patient access is controlled by role, facility, patient-compartment and
  optionally record-specific policy. Sensitive reads and mutations are audited.
- Encounters bind a patient, facility, provider, date and form registry entries;
  form data may live in a specialized `form_*` table or layout-based form data.
- Clinical issues use coded vocabularies and lifecycle state; encounter linkage,
  reconciliation, signing and amendment rules affect legal record semantics.
- Billing derives charges from encounter/fee-sheet rows, diagnoses, insurance
  priority and fee schedules; claim/payment state must reconcile exactly.
- Documents have categories, patient/encounter links, storage metadata and legal
  signing. Paths and content must be treated as protected health information.
- Jobs are configured in `background_services` and run through the CLI command;
  notification, email, import, mapping and reporting behavior is not UI-only.

## Known architectural risks

Global mutable configuration, mixed raw SQL/data-access styles, direct-entry PHP
pages, implicit session state, table-polymorphic forms, extension hooks, and
configuration-dependent behavior make a table-by-table rewrite unsafe. The new
system therefore needs compatibility import/reconciliation, explicit policy
checks, immutable audit evidence, and contract tests against representative
legacy fixtures.

