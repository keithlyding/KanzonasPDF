"""The nightly battery (.github/workflows/nightly-battery.yml): every night at midnight
Eastern, the random editing battery on main with seeds new each night, on Linux, Windows and
macOS; a failure goes into one open issue labeled "battery" (the owner, 23 Nov 2026).

    python -m unittest tests.test_nightly_battery
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "nightly-battery.yml")

try:
    import yaml
except ImportError:
    yaml = None

BASH = shutil.which("bash") if os.name != "nt" else None


def fill(script, values):
    """The step's script with its ${{ ... }} expressions replaced, as Actions does."""
    def one(m):
        return values[m.group(1).strip()]
    return re.sub(r"\$\{\{([^}]*)\}\}", one, script)


@unittest.skipIf(yaml is None, "PyYAML isn't installed")
class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.wf = yaml.safe_load(f)
        cls.on = cls.wf[True]           # (YAML reads the key "on" as true)
        cls.jobs = cls.wf["jobs"]
        cls.steps = {s.get("name"): s for s in cls.jobs["battery"]["steps"]}

    def test_every_night_at_midnight_eastern_and_by_hand(self):
        self.assertEqual(self.on["schedule"], [{"cron": "0 5 * * *"}])     # (05:00 UTC)
        self.assertIn("seed", self.on["workflow_dispatch"]["inputs"])

    def test_linux_windows_and_macos_each_with_its_own_seed(self):
        runs = self.jobs["battery"]["strategy"]["matrix"]["include"]
        self.assertFalse(self.jobs["battery"]["strategy"]["fail-fast"])    # (all run)
        self.assertEqual(sorted(r["os"] for r in runs),
                         ["macos-15", "ubuntu-22.04", "ubuntu-22.04", "ubuntu-22.04",
                          "windows-latest"])
        self.assertEqual(len({r["n"] for r in runs}), len(runs))
        self.assertEqual([r["flags"] for r in runs].count("--tagged"), 1)

    def test_the_full_battery_on_mains_files(self):
        run = [s["run"] for n, s in self.steps.items() if n and n.startswith("Random editing")]
        self.assertEqual(len(run), 1)
        self.assertIn("python tests/battery_random.py battery-out --ops 2000", run[0])
        self.assertIn("--seed ${{ steps.seed.outputs.seed }} ${{ matrix.flags }}", run[0])
        self.assertEqual(self.jobs["battery"]["env"]["QT_QPA_PLATFORM"], "offscreen")
        install = self.steps["Install dependencies"]["run"]
        self.assertIn("-r requirements.txt -c constraints.txt", install)

    def test_only_the_report_may_write_and_only_issues(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        self.assertNotIn("permissions", self.jobs["battery"])
        report = self.jobs["report"]
        self.assertEqual(report["permissions"],
                         {"contents": "read", "actions": "read", "issues": "write"})
        self.assertEqual(report["needs"], "battery")
        text = str(report["steps"])
        self.assertIn("--label battery", text)
        self.assertIn("gh issue comment", text)         # (one open issue, commented on)

    def test_reported_when_another_job_was_cancelled(self):
        # (25 Nov 2026: the macOS job got no runner and was cancelled; with failure() the
        # report was skipped and Linux's failure never reached the issue)
        report = self.jobs["report"]
        self.assertIn("always()", report["if"])
        self.assertIn("needs.battery.result != 'success'", report["if"])
        download = next(s for s in report["steps"] if "download-artifact" in s.get("uses", ""))
        self.assertTrue(download.get("continue-on-error"))
        run = next(s for s in report["steps"] if s.get("name") == "Report in an issue")["run"]
        self.assertIn("cancelled", run)                 # (the jobs with no result named)
        self.assertIn("exit 0", run)                    # (none failed: no issue)

    def test_a_failures_output_is_kept(self):
        kept = [s for s in self.jobs["battery"]["steps"]
                if "upload-artifact" in s.get("uses", "")]
        self.assertEqual({s["with"]["path"] for s in kept}, {"battery-out", "summary"})
        for s in kept:
            self.assertEqual(s["if"], "failure()")

    @unittest.skipUnless(BASH, "needs bash")
    def test_the_seed_from_the_date_or_given(self):
        script = fill(self.steps["Seed"]["run"], {"matrix.n": "3"})
        for first, want in (("", None), ("500", "503")):
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "out")
                env = dict(os.environ, GITHUB_OUTPUT=out, FIRST=first)
                subprocess.run([BASH, "-e", "-c", script], env=env, check=True)
                with open(out, encoding="utf-8") as f:
                    seed = f.read().strip()
            if want is None:
                self.assertRegex(seed, r"^seed=20\d{6}03$")     # (yyyymmdd and the run's 0n)
            else:
                self.assertEqual(seed, "seed=" + want)

    @unittest.skipUnless(BASH, "needs bash")
    def test_what_failed_names_the_seed_and_the_step(self):
        script = fill(self.steps["What failed (for the issue)"]["run"],
                      {"matrix.os": "ubuntu-22.04", "matrix.n": "2", "matrix.flags": "",
                       "steps.seed.outputs.seed": "2026112402"})
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "battery-out"))
            with open(os.path.join(d, "battery-out", "battery_random.log"), "w",
                      encoding="utf-8") as f:
                f.write("KanzonasPDF random editing battery\nstep 913 ok\n"
                        "FAIL seed 2026112402, step 914 (text_style): strike read back False\n"
                        "1 failure(s) in 800 s\n")
            subprocess.run([BASH, "-e", "-c", script], cwd=d, check=True)
            with open(os.path.join(d, "summary", "battery-2.md"), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("seed 2026112402", text)
            self.assertIn("step 914 (text_style)", text)
            self.assertIn("--ops 2000 --seed 2026112402", text)
            # (no log at all: said so)
            shutil.rmtree(os.path.join(d, "battery-out"))
            subprocess.run([BASH, "-e", "-c", script], cwd=d, check=True)
            with open(os.path.join(d, "summary", "battery-2.md"), encoding="utf-8") as f:
                self.assertIn("the battery didn't start", f.read())


if __name__ == "__main__":
    unittest.main()
