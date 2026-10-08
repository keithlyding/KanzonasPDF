# Security policy

KanzonasPDF handles sensitive work: redaction, passwords and permissions, digital signatures.
If you find a way it leaks, exposes or mishandles data, please report it privately so it can
be fixed before it's public.

## How to report

Use GitHub's private reporting: open this repository's **Security** tab and click
**Report a vulnerability**. Only the maintainer can see the report.

Please include:

- the KanzonasPDF version (Help > About) and your Windows version;
- what you did, what you expected, and what happened;
- if possible, a small test PDF that shows the problem. **Never send a real confidential
  document**: make a sample with fake data (for example a made-up number like 123-45-6789).

Please don't open a public issue for security problems.

## What to expect

KanzonasPDF is maintained by one person in their spare time. You can expect an
acknowledgement within about a week, and a fix as a new release as soon as practical. You'll be
credited in the changelog unless you'd rather not be.

## Supported versions

Only the newest release gets fixes. The app tells you when a newer one is out
(Help > Check for updates).

## Examples of security problems

- Redacted text still present in the saved file (page content, form fields, notes, bookmarks,
  metadata).
- A password-protected or restricted file saved without its protection.
- A digital signature reported as valid when the document was changed.
- Opening a crafted PDF causes the app to run code, write files elsewhere, or contact a server.
