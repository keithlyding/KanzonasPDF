"""On main, the regression tests are skipped only for files that passed them on their pull
request (tools/tested_on_pr.py, the workflow's `tested` job; the owner, 23 Nov 2026).

    python -m unittest tests.test_tested_on_pr
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")

import tested_on_pr  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

REPO = "keithlyding/KanzonasPDF"
MAIN, HEAD = "a" * 40, "b" * 40
TEST_STEP = "Regression tests (security, document preservation, efficiency budgets)"


def job(name, conclusion="success", tests="success"):
    steps = [{"name": "Set up job", "conclusion": "success"}]
    if tests is not None:
        steps.append({"name": TEST_STEP, "conclusion": tests})
    return {"name": name, "conclusion": conclusion, "steps": steps}


class Fake:
    """GitHub's answers for one merged pull request (changed by each test)."""

    def __init__(self):
        self.trees = {MAIN: "t1", HEAD: "t1"}
        self.pulls = [{"number": 127, "merged_at": "2026-11-23T19:35:00Z",
                       "base": {"ref": "main"}, "head": {"sha": HEAD}}]
        self.runs = [{"id": 7, "head_sha": HEAD, "status": "completed",
                      "created_at": "2026-11-23T17:45:00Z"}]
        self.jobs = [job("build"), job("linux"), job("macos (arm64)")]
        self.other_runs = {}            # {run id: its jobs}
        self.asked = []

    def __call__(self, path):
        self.asked.append(path)
        if path.startswith("repos/%s/git/commits/" % REPO):
            return {"tree": {"sha": self.trees[path.rsplit("/", 1)[1]]}}
        if path == "repos/%s/commits/%s/pulls" % (REPO, MAIN):
            return self.pulls
        if path.startswith("repos/%s/actions/workflows/build-windows.yml/runs?head_sha=%s"
                           % (REPO, HEAD)):
            return {"workflow_runs": self.runs}
        if path.startswith("repos/%s/actions/runs/7/jobs?filter=latest" % REPO):
            return {"jobs": self.jobs}
        for run, jobs in self.other_runs.items():
            if path.startswith("repos/%s/actions/runs/%s/jobs?filter=latest" % (REPO, run)):
                return {"jobs": jobs}
        raise AssertionError("not expected: " + path)


ALL = {"windows": True, "linux": True, "macos": True}
NONE = {"windows": False, "linux": False, "macos": False}


class Decide(unittest.TestCase):
    def setUp(self):
        self.gh = Fake()

    def decide(self):
        return tested_on_pr.decide(self.gh, REPO, MAIN)

    def test_the_same_files_tested_green_skip_every_platforms_tests(self):
        self.assertEqual(self.decide(), ALL)

    def test_main_moved_on_after_the_branch_was_tested(self):
        self.gh.trees[MAIN] = "t2"
        self.assertEqual(self.decide(), NONE)

    def test_not_from_a_pull_request(self):
        self.gh.pulls = []
        self.assertEqual(self.decide(), NONE)
        self.gh.pulls = [{"number": 5, "merged_at": None, "base": {"ref": "main"},
                          "head": {"sha": HEAD}}]
        self.assertEqual(self.decide(), NONE)          # (open, not merged)

    def test_a_pull_request_into_another_branch(self):
        self.gh.pulls[0]["base"]["ref"] = "release"
        self.assertEqual(self.decide(), NONE)

    def test_no_finished_build(self):
        self.gh.runs = []
        self.assertEqual(self.decide(), NONE)
        self.gh.runs = [{"id": 7, "head_sha": HEAD, "status": "in_progress",
                         "created_at": "2026-11-23T17:45:00Z"}]
        self.assertEqual(self.decide(), NONE)

    def test_a_mac_that_never_ran_tests_only_the_mac(self):
        # (GitHub had no Mac for the branch: the release may go out without the Mac version,
        # but a Mac build on main runs every test)
        self.gh.jobs[2] = {"name": "macos (arm64)", "conclusion": "cancelled", "steps": []}
        self.assertEqual(self.decide(), {"windows": True, "linux": True, "macos": False})

    def test_a_failed_or_skipped_test_step(self):
        self.gh.jobs[0] = job("build", conclusion="failure", tests="failure")
        self.gh.jobs[1] = job("linux", tests="skipped")
        self.gh.jobs[2] = job("macos (arm64)", tests=None)
        self.assertEqual(self.decide(), NONE)

    def test_the_latest_build_counts(self):
        # (a newer build of the same commit, its Linux tests failed: the older green one
        # doesn't count for Linux)
        self.gh.runs.append({"id": 8, "head_sha": HEAD, "status": "completed",
                             "created_at": "2026-11-23T18:45:00Z"})
        self.gh.other_runs[8] = [job("build"), job("linux", "failure", "failure"),
                                 job("macos (arm64)")]
        self.assertEqual(self.decide(), {"windows": True, "linux": False, "macos": True})

    def test_github_not_answering_runs_every_test(self):
        out = os.path.join(tempfile.mkdtemp(), "out")
        env = {"GITHUB_TOKEN": "x", "GITHUB_REPOSITORY": REPO, "GITHUB_SHA": MAIN,
               "GITHUB_OUTPUT": out}

        def down(*_a, **_k):
            raise OSError("no network")
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(tested_on_pr.urllib.request, "urlopen", down), \
                mock.patch.object(sys, "stdout"):
            self.assertEqual(tested_on_pr.main(), 0)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "windows=false\nlinux=false\nmacos=false\n")

    def test_written_for_the_workflow(self):
        out = os.path.join(tempfile.mkdtemp(), "out")
        env = {"GITHUB_TOKEN": "x", "GITHUB_REPOSITORY": REPO, "GITHUB_SHA": MAIN,
               "GITHUB_OUTPUT": out}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(tested_on_pr, "github_api", lambda *_a: self.gh), \
                mock.patch.object(sys, "stdout"):
            tested_on_pr.main()
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "windows=true\nlinux=true\nmacos=true\n")


@unittest.skipIf(yaml is None, "PyYAML isn't installed")
class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.jobs = yaml.safe_load(f)["jobs"]

    def test_only_on_a_push_to_main_and_only_reading(self):
        t = self.jobs["tested"]
        self.assertEqual(t["if"], "github.ref == 'refs/heads/main' && github.event_name == 'push'")
        self.assertEqual(t["permissions"], {"contents": "read", "actions": "read",
                                            "pull-requests": "read"})
        self.assertIn("python3 tools/tested_on_pr.py", [s.get("run") for s in t["steps"]])

    def test_each_platform_skips_only_its_own_tests(self):
        for name, platform in (("build", "windows"), ("linux", "linux"), ("macos", "macos")):
            j = self.jobs[name]
            self.assertEqual(j["needs"], "tested")
            # (run when `tested` is skipped, off main, or failed: then every test runs)
            self.assertEqual(j["if"], "${{ !cancelled() }}")
            tests = [s for s in j["steps"] if s.get("name") == TEST_STEP]
            self.assertEqual(len(tests), 1, name)
            self.assertEqual(tests[0]["if"], "needs.tested.outputs.%s != 'true'" % platform)
            self.assertEqual(tested_on_pr.JOBS[platform],
                             j.get("name", name))           # (the names the script reads)
            # (nothing else is skipped: the apps are built, self-tested and packaged)
            others = [s for s in j["steps"] if "needs.tested" in str(s.get("if", ""))]
            self.assertEqual(others, tests, name)

    def test_the_step_name_the_script_reads(self):
        self.assertTrue(TEST_STEP.startswith(tested_on_pr.TEST_STEP))


if __name__ == "__main__":
    unittest.main()
