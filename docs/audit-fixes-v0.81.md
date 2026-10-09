# v0.81 audit fixes

This revision addresses the twelve consolidated findings from the independent v0.80 audit. It does not constitute an exhaustive security certification or a production-readiness declaration.

| Finding | Change |
|---|---|
| KZ80-001 | Applied redaction removes vector paths touching a mark, including crossing paths. |
| KZ80-002 | Search redaction removes matching annotations and private stamp dictionaries; selected-redaction application also scrubs its selected search terms. |
| KZ80-003 | Saving encrypted edits keeps the file's own encryption (`PDF_ENCRYPT_KEEP`): the original open and owner passwords and permissions are preserved without being re-entered, and no password is ever invented. Undo copies keep the encryption too. Only if it can't be carried over are the original passwords asked for. |
| KZ80-004 | New protection deletes the document's existing recovery copy and excludes protected documents from both scheduled and direct backup paths. |
| KZ80-005 | Recovery filenames include UUIDs so equal basenames and timestamps remain distinct. |
| KZ80-006 | Selected-page flattening restores outgoing links, labels and stored measurement scale. |
| KZ80-007 | Form filling and annotation transactions use their own permission flags. |
| KZ80-008 | Copy, capture, extraction, export and printing paths enforce the corresponding permissions; undo retains original restrictions. Signed read-only files remain viewable/copyable/printable where permitted. |
| KZ80-009 | Excel exports store PDF-derived strings as literal text, not formulas. |
| KZ80-010 | README describes the 13,000-pixel OCR cap and tiling. |
| KZ80-011 | README reflects implemented Windows certificate-store signing and provider-dependent token support. |
| KZ80-012 | Self-test skips are logged as SKIP rather than PASS. |

OCR explicitly disables ONNX Runtime telemetry before recognition engine/session construction. The user manual and changelog describe changed behavior, and the version is bumped to 0.81.

## Review follow-up

A review of this change found and fixed three problems, each with a regression test that fails on the first version:

- Saving required the owner password, so a form protected only by an unknown permissions password (common for official forms) could no longer be saved after filling it in. Fixed by keeping the original encryption instead.
- Search redaction also searched the private markup data's structure, so a term such as "rect" or "fill" deleted unrelated markups. It now matches only the text people see.
- Flattening selected pages put links back in the wrong place on rotated pages (displayed vs unrotated coordinates); the same mistake in restoring incoming links is fixed too.

## Verification

- Eighteen automated audit regression tests pass on the recorded Linux/Python/Qt environment.
- The built-in self-test reports 36 passes and one Windows certificate-store skip.
- The repository CAD campaign completed on ordinary and rotated floor plans, a layered DXF plot, a heavy site plan and a scanned plan, without failed operations.
- The Windows workflow now runs the audit regression tests before packaging. Windows executable/installer and certificate-store verification have not run locally.

Run the regressions from the repository root:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p test_audit_regressions.py
```

On PowerShell, set `$env:QT_QPA_PLATFORM = "offscreen"` first, then run the Python command without the environment assignment prefix.

## Behavior reviewers should examine

Secure redaction now removes complete vector paths touching a mark. Long lines or grouped paths may disappear beyond the marked region; inspect the drawing before saving. This favors removing confidential geometry over preserving crossing paths behind a visual cover.

Search redaction removes matching annotations completely, including appearances and private properties, rather than merely changing their visible comment text.

Encrypted edits keep the file's own encryption, so no password prompt is normally needed (a form protected only by an unknown permissions password can still be filled in and saved). Credentials are never invented or silently equated.

Native Windows testing, additional PDF standards/compatibility corpora, accessibility and other previously untested audit areas remain outstanding.
