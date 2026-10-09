# Contributing to KanzonasPDF

Thanks for your interest. KanzonasPDF is a free, open-source PDF reader and editor for
Windows, maintained by one person in their spare time, so reviews may take a while.

## Reporting bugs and ideas

Open an issue with the **Bug report** or **Feature request** form. For anything that could
leak or expose data (redaction, passwords, signatures), follow [SECURITY.md](SECURITY.md)
instead of opening a public issue. **Never attach confidential PDFs**: make a sample with fake
data that shows the problem.

## Code changes

1. Talk first: for anything bigger than a small fix, open an issue describing what you'd like
   to change, so time isn't spent on something that won't be merged.
2. Work on a branch and open a pull request into `main`.
3. Follow the rules in [CLAUDE.md](CLAUDE.md). In short, every user-facing change updates in the
   same pull request:
   - the user manual in `kanzonas/manual.py` (Help > User manual);
   - the version in `kanzonas/__init__.py`;
   - a row in `CHANGELOG.md`.
4. Keep start-up fast: import heavy libraries (OCR, Office exports, signing...) inside the
   function that needs them. The performance check in the self-test enforces this.
5. Use American spelling in all text the user sees.

## Running and testing

```
pip install -r requirements.txt
python -m kanzonas                     # run the app
QT_QPA_PLATFORM=offscreen python -m kanzonas --selftest selftest.log   # must exit 0
```

On Windows, leave out `QT_QPA_PLATFORM=offscreen`. Every push builds the Windows app and runs
the self-test inside it (GitHub Actions); a pull request needs a green build. Merging a new
version into `main` publishes it as a release automatically.

## Free releases

Official KanzonasPDF releases stay free of charge for personal and commercial use: no subscriptions, trial expiration, paid feature tiers, required account or required paid cloud service. Optional donations never unlock features. Contributions must keep it that way: no license checks,
activation, paid-only features or required paid services.

## License

KanzonasPDF is licensed under the GNU AGPL 3.0 (see [LICENSE](LICENSE)), because the PDF engine
it's built on, PyMuPDF, is AGPL. By contributing, you agree that your contribution is licensed
under the same terms.

## Conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
