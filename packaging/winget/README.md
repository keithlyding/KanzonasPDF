# winget manifests

Manifests for the Windows Package Manager (`winget install KanzonasPDF.KanzonasPDF`), in the
layout of https://github.com/microsoft/winget-pkgs (`manifests/k/KanzonasPDF/KanzonasPDF/<version>/`).

The Windows build writes the manifests for each release and attaches them to the release
(`winget-manifests.zip`). To publish a version:

1. Download `winget-manifests.zip` from the release and unzip it (or use this folder for
   the version it holds).
2. Check them: `winget validate --manifest manifests\k\KanzonasPDF\KanzonasPDF\<version>`
   and `winget install --manifest manifests\k\KanzonasPDF\KanzonasPDF\<version>` (needs
   `winget settings --enable LocalManifestFiles` once, as administrator).
3. Submit them to winget-pkgs: `wingetcreate submit --token <GitHub token> manifests\k\KanzonasPDF\KanzonasPDF\<version>`,
   or copy the folder into a fork of winget-pkgs and open a pull request. The first version
   of a package is reviewed by hand; later versions are mostly automatic.

The installer is Inno Setup (`installer/KanzonasPDF.iss`): user scope, no administrator
rights, product code `{8F4C2A61-5B7E-4D3A-9C1F-2E6B7A9D4C11}_is1`.
