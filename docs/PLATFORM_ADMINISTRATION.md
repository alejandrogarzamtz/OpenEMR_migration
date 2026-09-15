# Platform administration, localization, and templates

OpenRM keeps application-owned administration data in explicit, versioned
models instead of exposing arbitrary process environment values or the legacy
global key/value store. All mutation endpoints require the existing
`admin:users:write` grant and write an audit event.

## Staff accounts

`GET /api/v1/admin/users` lists application accounts without password or token
material. `POST /api/v1/admin/users/invitations` creates an account with an
unusable random password and queues a one-time password-setup link through the
durable delivery outbox. `PATCH /api/v1/admin/users/{uuid}` changes role,
explicit grants, or active state. Disabling an account revokes its active
sessions. OpenRM prevents self-disable and removal of the last active
administrator.

## Safe configuration

The settings API deliberately accepts only these reviewed keys:

- `organization.name`
- `organization.timezone`
- `localization.default_locale`
- `localization.date_format`
- `ui.default_page_size`

Each key has type-specific validation, an update counter, actor attribution,
and a timestamp. Secrets, filesystem paths, executable values, and unknown
legacy globals cannot be written through this API. Deployment secrets remain
environment or secret-manager configuration.

The legacy importer follows the same boundary. It reads only an explicit map
for application name, IANA timezone, default language, and display date format. Other `globals`
records—including credentials and integration keys—are intentionally omitted.

## Localization

Locale catalogs record language code, display name, active state, and text
direction. Translation keys are unique within a locale and may be customized
through audited administration endpoints. A public, read-only bootstrap
endpoint returns only the organization display name, active locales, direction,
and selected translations. It never exposes administrative settings as a
general-purpose configuration object.

The React application uses this bootstrap for its primary navigation, language
selector, document language, and LTR/RTL direction. English and Spanish core
navigation strings are seeded idempotently. Legacy language catalogs,
definitions, and custom overrides are imported with source identifiers and raw
metadata for reconciliation.

## Versioned content templates

Templates are identified by a stable key and locale. Creating a template starts
version 1; updating it creates a new active version and retains the previous
version as immutable history. Supported categories are clinical, document,
email, and SMS, with plain-text or HTML content.

Variables use `{{variable.name}}`. Every placeholder must be declared by the
template, preview requests must provide every used variable, and undeclared
input is rejected. HTML previews escape substituted values to prevent variable
content from becoming markup. Previewing does not send or persist a rendered
document.

Legacy `document_templates` content is decoded with explicit replacement for
invalid UTF-8, and its source metadata plus a content checksum is retained for
reconciliation. Imported legacy
placeholder syntax remains source content; it is not silently reinterpreted as
the modern rendering contract.

## Boundaries

Module lifecycle and integration hooks are provided through the separate,
out-of-process [extension and webhook contract](EXTENSIONS.md). Production
secret management, backup and restore, disaster recovery, and operational
acceptance remain deployment and security work. Template preview is not a
legal-signature or document-delivery claim.
