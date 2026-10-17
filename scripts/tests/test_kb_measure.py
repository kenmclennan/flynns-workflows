import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import kb_audit
from kb_audit_helpers import git, make_remote, run


class MeasureTests(unittest.TestCase):
    def measure(self, fixture, **extra):
        remote = make_remote(fixture)
        data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, remote)
        self.addCleanup(shutil.rmtree, data)
        sha = git(remote, "rev-parse", "main")
        proc = run("kb-measure.py", data, remote, stdin=json.dumps({"schedule_state": sha}), **extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["outcome"], "measured")
        return out

    def defect_lines(self, out):
        return out["artifacts"]["measurements"].split("\n\n")[0].splitlines()

    def test_each_planted_defect_is_named_once_and_nothing_else(self):
        lines = self.defect_lines(self.measure("defects"))
        found = sorted(line.split(" - ")[0] for line in lines)
        self.assertEqual(
            found,
            sorted([
                "unresolved-link: topic-b/one.md",
                "unreachable-doc: topic-a/orphan.md",
                "island-topic: island",
                "thin-doc: topic-b/two.md",
                "uncited-reference: references/uncited.md",
                "citation-without-link: topic-b/one.md",
                "stale: topic-a/two.md",
            ]),
        )

    def test_clean_fixture_has_no_defects(self):
        out = self.measure("clean")
        self.assertEqual(self.defect_lines(out), ["no defects"])

    def test_review_context_names_snapshot_sha_and_first_audit(self):
        context = self.measure("clean")["artifacts"]["review-context"]
        self.assertIn("snapshot: ", context)
        self.assertIn("previously audited: first audit", context)

    def test_stale_after_in_the_future_is_not_stale(self):
        out = self.measure("defects", KB_AUDIT_TODAY="2025-06-01")
        self.assertFalse([l for l in self.defect_lines(out) if l.startswith("stale:")])

    def test_higher_floor_reports_more_thin_docs(self):
        out = self.measure("defects", LC_WORKFLOW_CONFIG_MIN_CROSS_TOPIC_LINKS="2")
        thin = [l for l in self.defect_lines(out) if l.startswith("thin-doc:")]
        self.assertGreater(len(thin), 1)

    def test_missing_schedule_state_parks(self):
        remote = make_remote("clean")
        data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, remote)
        self.addCleanup(shutil.rmtree, data)
        proc = run("kb-measure.py", data, remote)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("schedule_state", proc.stderr)


class ToolCountTests(unittest.TestCase):
    def test_prettier_failures_group_by_topic(self):
        out = "references/a.md\nreferences/b.md\nrpg/x.md\nREADME.md\n"
        self.assertEqual(kb_audit.prettier_counts(out), {"references": 2, "rpg": 1, "(root)": 1})

    def test_markdownlint_errors_group_by_topic(self):
        out = (
            "markdownlint-cli2 v0.1\nFinding: **/*.md\nLinting: 3 file(s)\n"
            "references/a.md:3:1 MD013/line-length Line length\n"
            "references/a.md:9 MD041/first-line-heading\n"
            "rpg/x.md:1:1 MD022/blanks-around-headings\n"
            "Summary: 3 error(s)\n"
        )
        self.assertEqual(kb_audit.markdownlint_counts(out), {"references": 2, "rpg": 1})

    def test_render_has_one_line_per_topic_and_tool(self):
        text = kb_audit.render([], {"references": 1100}, {"references": 9000, "rpg": 40}, True)
        self.assertEqual(
            text.splitlines()[2:],
            ["prettier references: 1100 file(s)", "markdownlint references: 9000 error(s)", "markdownlint rpg: 40 error(s)"],
        )


if __name__ == "__main__":
    unittest.main()
