# Code signing policy

KanzonasPDF's downloads are **not code-signed yet**. A free certificate from the SignPath
Foundation was applied for and declined (the project is too new and has too few users); a
certificate will be bought or applied for again once the project has grown. Until then:

- KanzonasPDF's Windows program (`KanzonasPDF.exe`), installer
  (`KanzonasPDF-v<version>-setup.exe`), portable download (`KanzonasPDF-portable.zip`) and
  PortableApps.com package are built from this repository's source code by the automated
  GitHub Actions build (`.github/workflows/build-windows.yml`), never on a developer's own
  computer, and only after the build's tests pass.
- Every release lists the SHA-256 checksum of each download (in the release notes and in
  `SHA256SUMS.txt`), so a download can be checked against what the build produced.
- Windows SmartScreen may warn the first time an unsigned program runs; the README says what
  that means and when it's safe to continue.

When signing is in place, it will happen only from that automated build, and this policy will
say which certificate is used.

## Team roles

- **Committers and reviewers:** [@keithlyding](https://github.com/keithlyding) (project owner).
  Some changes are prepared with AI coding assistants. Every change goes through a pull request
  to `main` and must pass the automated Windows build (unit tests and the program's self-test)
  before it is merged.
- **Approvers:** [@keithlyding](https://github.com/keithlyding). Every release is approved by
  the owner before it is signed and published.

## Privacy policy

This program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it, with these exceptions, which
the user controls:

- **Update check:** with Help > *Check for updates automatically* ticked (the default), the
  program asks GitHub (api.github.com) for the list of KanzonasPDF releases at most once a day.
  No document or personal information is sent. Untick it to turn the check off; Help > *Check
  for updates* then asks only when you choose it.
- **Updates:** a new version is downloaded from GitHub only when you choose *Update now*.
- **Timestamps:** when you choose to timestamp a document or a signature, a fingerprint (hash)
  of the document is sent to a public timestamp server (DigiCert, Sectigo or FreeTSA). The
  document itself is not sent.
- **Links:** web and email links in a PDF open in your browser or email program only after the
  program asks you.

Text recognition (OCR), conversion, signing and every other feature work entirely on your
computer. Third-party services named above have their own privacy policies:
[GitHub](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement),
[DigiCert](https://www.digicert.com/digicert-privacy-policy),
[Sectigo](https://www.sectigo.com/privacy-policy), [FreeTSA](https://freetsa.org).
