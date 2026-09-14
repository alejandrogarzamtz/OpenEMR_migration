# Clinical form evidence links

OpenRM can associate a clinical form with patient documents and individual
procedure or laboratory results. The relationship is explicit and searchable;
the binary document or result remains in its canonical clinical table.

The staff workspace lists current evidence, allows same-patient targets to be
linked or unlinked while the form is editable, and prevents all relationship
changes once the form or encounter is electronically locked. Every read, link
and unlink operation is audited. Linked target UUIDs are included in form and
encounter signature hashes, so verification detects relationship tampering.

Legacy migration imports both `clinical_notes_documents` and
`clinical_notes_procedure_results`. It preserves the source link ID, the exact
`form_clinical_notes.id`, creation timestamp and creator name. The importer
resolves the containing `forms` record and canonical modern document or result,
rejects cross-patient or unresolved relationships, reports reconciliation
counts, and is idempotent by source link ID.
