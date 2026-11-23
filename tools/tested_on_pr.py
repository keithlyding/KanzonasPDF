"""Were this commit's files already tested on its pull request? (the build workflow's
`tested` job, on main only)

A pull request merges by squashing its branch into one commit on main. When the branch had
main merged in first (AGENTS.md: the version is taken at merge time, after merging main),
that commit holds exactly the files of the pull request's last commit, and that commit's own
build already ran every regression test on Windows, Linux and macOS. Running them all again
on main took an hour and a half more for every release (the owner, 23 Nov 2026: "do it").

So for a commit on main this finds the pull request it was merged from and that pull
request's last commit. If both hold the same files (the same git tree) and that commit's
latest build ran a platform's regression tests to success, it says `true` for that platform,
and the job there skips its tests; the app is still built from main and self-tested,
installed and updated as before. Anything else says `false` and every test runs: main moved
on after the branch was tested, no pull request, a build cancelled or failed, a test step
skipped, or GitHub not answering.

    python tools/tested_on_pr.py      (env: GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_TOKEN,
                                       GITHUB_OUTPUT)

It writes windows=, linux= and macos= (true or false) to GITHUB_OUTPUT.
"""
import json
import os
import sys
import urllib.request

WORKFLOW = "build-windows.yml"
# the platform's job in that workflow, and its step that runs the regression tests
JOBS = {"windows": "build", "linux": "linux", "macos": "macos (arm64)"}
TEST_STEP = "Regression tests"
NONE = {p: False for p in JOBS}


def decide(api, repo, sha, log=lambda line: None):
    """{platform: True when its tests passed on these same files}. api(path) returns the
    GitHub API's answer to a GET of that path, decoded from JSON."""
    tree = api("repos/%s/git/commits/%s" % (repo, sha))["tree"]["sha"]
    merged = [p for p in api("repos/%s/commits/%s/pulls" % (repo, sha))
              if p.get("merged_at") and p.get("base", {}).get("ref") == "main"]
    if not merged:
        log("%s isn't a merged pull request's commit: every test runs" % sha)
        return dict(NONE)
    pr = merged[0]
    head = pr["head"]["sha"]
    head_tree = api("repos/%s/git/commits/%s" % (repo, head))["tree"]["sha"]
    if head_tree != tree:
        log("#%s's last commit %s has other files than %s (main moved on after it was "
            "tested): every test runs" % (pr.get("number"), head[:7], sha[:7]))
        return dict(NONE)
    runs = [r for r in api("repos/%s/actions/workflows/%s/runs?head_sha=%s&per_page=20"
                           % (repo, WORKFLOW, head))["workflow_runs"]
            if r.get("head_sha") == head and r.get("status") == "completed"]
    if not runs:
        log("no finished build of %s: every test runs" % head[:7])
        return dict(NONE)
    run = max(runs, key=lambda r: r.get("created_at") or "")
    jobs = api("repos/%s/actions/runs/%s/jobs?filter=latest&per_page=100"
               % (repo, run["id"]))["jobs"]
    out = {}
    for platform, name in JOBS.items():
        job = [j for j in jobs if j.get("name") == name]
        steps = [s for s in (job[0].get("steps") or []) if
                 (s.get("name") or "").startswith(TEST_STEP)] if job else []
        out[platform] = bool(job and job[0].get("conclusion") == "success" and steps
                             and all(s.get("conclusion") == "success" for s in steps))
        log("%s: %s" % (platform, "tested on #%s's %s (run %s), skipped here"
                        % (pr.get("number"), head[:7], run["id"]) if out[platform]
                        else "not tested there, tested here"))
    return out


def github_api(token, base="https://api.github.com"):
    def api(path):
        req = urllib.request.Request("%s/%s" % (base, path), headers={
            "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    return api


def main():
    env = os.environ
    log = lambda line: sys.stdout.write(line + "\n")
    try:
        result = decide(github_api(env["GITHUB_TOKEN"], env.get("GITHUB_API_URL",
                                                                 "https://api.github.com")),
                        env["GITHUB_REPOSITORY"], env["GITHUB_SHA"], log)
    except Exception as e:      # (any doubt runs every test: never a reason to skip one)
        log("couldn't tell (%s: %s): every test runs" % (type(e).__name__, e))
        result = dict(NONE)
    with open(env.get("GITHUB_OUTPUT") or os.devnull, "a", encoding="utf-8") as f:
        for platform in JOBS:
            f.write("%s=%s\n" % (platform, "true" if result[platform] else "false"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
