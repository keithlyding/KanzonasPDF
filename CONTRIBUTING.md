# Contributing to KanzonasPDF

Thanks for your interest. KanzonasPDF is a free, open-source PDF reader and editor for
Windows, Linux and macOS, maintained by one person in their spare time, so reviews may take a
while.

## Reporting bugs and ideas

Open an issue with the **Bug report** or **Feature request** form. For anything that could
leak or expose data (redaction, passwords, signatures), follow [SECURITY.md](SECURITY.md)
instead of opening a public issue. **Never attach confidential PDFs**: make a sample with fake
data that shows the problem.

## Code changes

1. Talk first: for anything bigger than a small fix, open an issue describing what you'd like
   to change, so time isn't spent on something that won't be merged.
2. Work on a branch and open a pull request into `main`.
3. Follow the rules in [AGENTS.md](AGENTS.md). In short, every user-facing change updates the
   user manual in the same pull request (`kanzonas/manual.py`, Help > User manual, and its
   Spanish and Italian versions, `manual_es.py` and `manual_it.py`, with the translations in
   `kanzonas/locale/`).
4. **Leave the version number, `CHANGELOG.md` and `RELEASE_NOTES.md` alone.** The maintainer
   adds them when your pull request is merged, with the next free number and a credit to you
   by your GitHub handle. (Several pull requests that each set a version collide with each
   other and with the maintainer's own releases, and then have to be merged again only for
   that.) Describe your change in the pull request instead.
5. Keep your branch based on the current `main`. If `main` moves on while you wait, a small
   conflict (a list, a line next to yours) may be resolved by the maintainer when merging:
   your commits stay exactly as you wrote them, under your name. If your code and a change on
   `main` touch the same logic, you'll be asked to bring `main` in yourself.
6. Keep start-up fast: import heavy libraries (OCR, Office exports, signing...) inside the
   function that needs them. The performance check in the self-test enforces this, and the
   speed budgets in AGENTS.md ("Performance") are a condition for merging.
7. Use American spelling in all text the user sees.
8. Test on more than one system if you can: the ribbon is measured with each system's own font
   (`tests/test_ribbon_fits.py`), and Linux's and macOS's run wider than Windows'.

## Running and testing

```
pip install -r requirements.txt
python -m kanzonas                     # run the app
QT_QPA_PLATFORM=offscreen python -m kanzonas --selftest selftest.log   # must exit 0
```

On Windows, leave out `QT_QPA_PLATFORM=offscreen`. Every push to a branch of this repository
builds the Windows, Linux and macOS apps and runs the tests and the self-test in each (GitHub
Actions). The builds don't run for pull requests from forks: the maintainer copies a pull
request's commits to a review branch here to run them, and posts the results. A pull request
needs green builds to be merged. Merging into `main` publishes a release automatically.

## Free releases

Official KanzonasPDF releases stay free of charge for personal and commercial use: no subscriptions, trial expiration, paid feature tiers, required account or required paid cloud service. Optional donations never unlock features. Contributions must keep it that way: no license checks,
activation, paid-only features or required paid services.

## License

KanzonasPDF is licensed under the GNU AGPL 3.0 (see [LICENSE](LICENSE)), because the PDF engine
it's built on, PyMuPDF, is AGPL. By contributing, you agree that your contribution is licensed
under the same terms.

## Conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
