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
                "thin-doc: topic-b",
                "uncited-reference: references/uncited.md",
                "citation-without-link: topic-b",
                "stale: topic-a/two.md",
                "index-count: index.md",
            ]),
        )

    def test_grouped_lines_name_example_paths(self):
        lines = self.defect_lines(self.measure("defects"))
        thin = [l for l in lines if l.startswith("thin-doc:")]
        cited = [l for l in lines if l.startswith("citation-without-link:")]
        self.assertEqual(len(thin), 1)
        self.assertIn("topic-b/two.md", thin[0])
        self.assertEqual(len(cited), 1)
        self.assertIn("topic-b/one.md", cited[0])

    def test_per_file_flag_restores_one_line_per_file(self):
        lines = self.defect_lines(self.measure("defects", KB_AUDIT_PER_FILE="1"))
        self.assertIn("thin-doc: topic-b/two.md - 0 cross-topic link(s), fewer than 1", lines)
        self.assertTrue([l for l in lines if l.startswith("citation-without-link: topic-b/one.md")])

    def test_angle_bracket_and_nested_links_and_claude_md_are_not_false_positives(self):
        lines = self.defect_lines(self.measure("links"))
        self.assertEqual(
            sorted(lines),
            ["unreachable-doc: stray.md - no index.md reaches it by following links",
             "unresolved-link: topic-b/one.md - ../topic-a/missing (v2).md"],
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
        docs = sum(int(l.split(" - ")[1].split(" ")[0]) for l in thin)
        self.assertGreater(docs, 1)

    def test_missing_schedule_state_parks(self):
        remote = make_remote("clean")
        data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, remote)
        self.addCleanup(shutil.rmtree, data)
        proc = run("kb-measure.py", data, remote)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("schedule_state", proc.stderr)


class LinkParserTests(unittest.TestCase):
    def test_angle_bracket_target_keeps_parentheses_and_drops_brackets(self):
        body = "[x](<https://en.wikipedia.org/wiki/Foo_(bar)>) and [y](<a (v2).md> \"title\")"
        self.assertEqual(kb_audit.body_links(body), ["https://en.wikipedia.org/wiki/Foo_(bar)", "a (v2).md"])

    def test_nested_bracket_text_is_one_link(self):
        self.assertEqual(kb_audit.body_links("[see [the spec]](x.md)"), ["x.md"])

    def test_bare_target_still_ends_at_first_paren_and_images_are_skipped(self):
        self.assertEqual(kb_audit.body_links("[a](b.md) ![i](c.png)"), ["b.md"])


class GroupingTests(unittest.TestCase):
    def test_groups_per_topic_with_five_examples(self):
        defects = [("thin-doc", "t1/d%d.md" % i, "x") for i in range(7)] + [("thin-doc", "t2/d.md", "x"), ("stale", "t1/s.md", "x")]
        grouped = kb_audit.group_by_topic(defects, 1)
        self.assertEqual(grouped[0], ("stale", "t1/s.md", "x"))
        self.assertEqual(grouped[1][:2], ("thin-doc", "t1"))
        self.assertTrue(grouped[1][2].startswith("7 doc(s)"))
        self.assertEqual(grouped[1][2].split("e.g. ")[1].split(", "), ["t1/d%d.md" % i for i in range(5)])
        self.assertEqual(grouped[2][:2], ("thin-doc", "t2"))
        self.assertTrue(grouped[2][2].startswith("1 doc(s)"))

    def test_root_files_group_under_root(self):
        grouped = kb_audit.group_by_topic([("citation-without-link", "a.md", "x")], 1)
        self.assertEqual(grouped[0][:2], ("citation-without-link", "(root)"))


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
