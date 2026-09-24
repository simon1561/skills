#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECK_PATH = Path(__file__).parents[1] / "scripts" / "check.py"
SKILL_ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("report_writer_check", CHECK_PATH)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class ReportWriterCheckTest(unittest.TestCase):
    def style_groups(self, text):
        return {hit[1] for hit in CHECK.check_style_patterns(text) if hit[0]}

    def test_style_pattern_categories(self):
        cases = {
            "二元反转": "这不是规模问题，而是收入结构问题。",
            "表象揭示": "表面上是价格差异，实际上是成本结构不同。",
            "唯一答案": "真正决定结果的是资本投入。",
            "条件式教导": "只有理解会员结构，才能看清利润来源。",
            "预设误判": "如果只看门店数，就会误判收入规模。",
            "揭晓推进": "这揭示了更深层的问题。",
            "过强断言": "毫无疑问，该模式必然意味着更高回报。",
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, self.style_groups(text))

    def test_non_author_text_is_ignored(self):
        text = (
            "正文不是A，而是B。\n"
            "> 引用不是C，而是D。\n"
            "| 表格不是E，而是F |\n"
            "```\n代码不是G，而是H。\n```\n"
        )
        hits = [hit for hit in CHECK.check_style_patterns(text) if hit[0]]
        self.assertEqual(1, len(hits))
        self.assertEqual(1, hits[0][0])

    def test_author_callout_is_checked(self):
        text = "> [!NOTE]\n> 这不是规模问题，而是收入结构问题。\n"
        hits = [hit for hit in CHECK.check_style_patterns(text) if hit[0]]
        self.assertEqual(1, len(hits))
        self.assertEqual("二元反转", hits[0][1])

    def test_wrapped_paragraph_is_combined(self):
        text = (
            "这是一个段落。" + "包含数据和解释，" * 35 + "\n"
            "这一行仍属于同一段。" + "继续补充口径和限制。" * 25
        )
        groups = {note[1] for note in CHECK.check_readability(text)}
        self.assertIn("长段落", groups)

    def test_bold_punctuation_fix(self):
        text = "**结论如此。**接下来说明依据。"
        problems, fixed, count = CHECK.check_bold(text)
        self.assertEqual(1, count)
        self.assertTrue(problems)
        self.assertEqual("**结论如此**。接下来说明依据。", fixed)

    def test_write_fixed_keeps_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_text("原文", encoding="utf-8")
            backup = CHECK.write_fixed(str(path), "修复后")
            self.assertEqual("原文", Path(backup).read_text(encoding="utf-8"))
            self.assertEqual("修复后", path.read_text(encoding="utf-8"))

    def test_write_fixed_preserves_newlines_mode_and_each_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            path.write_bytes(b"old\r\ntext\r\n")
            os.chmod(path, 0o644)
            first = CHECK.write_fixed(str(path), "new\r\ntext\r\n")
            second = CHECK.write_fixed(str(path), "again\r\ntext\r\n")
            self.assertEqual(b"old\r\ntext\r\n", Path(first).read_bytes())
            self.assertEqual(b"new\r\ntext\r\n", Path(second).read_bytes())
            self.assertEqual(b"again\r\ntext\r\n", path.read_bytes())
            self.assertEqual(0o644, os.stat(path).st_mode & 0o777)

    def test_clean_text_has_no_style_risk(self):
        text = "两家公司利润率接近，但统计边界不同。现有数据不能确定长期排序。"
        self.assertFalse([hit for hit in CHECK.check_style_patterns(text) if hit[0]])

    def test_soft_line_break_does_not_hide_pattern(self):
        text = "限制扩张的不是市场需求，\n而是资本投入和管理半径。"
        self.assertIn("二元反转", self.style_groups(text))

    def test_bu_you_er_shi_is_flagged(self):
        text = "私教不由门店雇佣，而是每月向门店支付场地使用费。"
        self.assertIn("二元反转", self.style_groups(text))

    def test_ascii_punctuation_in_chinese_is_flagged(self):
        text = "会籍收入占82%,课程收入占18%。单店投资800万元,年度资金4000万元。"
        self.assertTrue(any("半角" in item for item in CHECK.check_misc(text)))

    def test_research_method_is_not_treated_as_version_trace(self):
        text = "两家公司折旧口径不同。采用统一口径重新计算，A公司为20.5%。"
        groups = {hit[1] for hit in CHECK.check_traces(text)}
        self.assertNotIn("版本对照", groups)

    def test_actual_version_trace_is_flagged(self):
        text = "上一版写成A公司为18%，当前结果为20.5%。"
        groups = {hit[1] for hit in CHECK.check_traces(text)}
        self.assertIn("版本对照", groups)

    def test_operating_recommendation_is_not_preaching(self):
        text = "建议增加晚间教练排班，依据是晚间教练供给不足。"
        groups = {hit[1] for hit in CHECK.check_traces(text)}
        self.assertNotIn("指教读者", groups)

    def test_frontmatter_depends_on_delivery_context(self):
        text = "---\ntitle: 示例\n---\n# 正文\n"
        self.assertFalse(any("frontmatter" in item.lower() for item in CHECK.check_misc(text)))
        self.assertTrue(CHECK.check_contextual(text))

    def test_code_fence_does_not_trigger_bold_or_quote_errors(self):
        text = '正文正常。\n```markdown\n**结论如此。**接下来\n"\n```\n'
        problems, _, _ = CHECK.check_bold(text)
        self.assertFalse(problems)
        self.assertFalse(any("双引号" in item for item in CHECK.check_misc(text)))

    def test_yaml_and_indented_code_do_not_trigger_bold_errors(self):
        yaml_text = '---\nsummary: "**结论如此。**接下来"\n---\n# 正文\n'
        indented_text = "正文正常。\n\n    **代码。**接下来\n"
        for text in (yaml_text, indented_text):
            with self.subTest(text=text):
                problems, _, _ = CHECK.check_bold(text)
                self.assertFalse(problems)

    def test_multibacktick_code_span_does_not_trigger_bold_error(self):
        text = "示例为 ``**结论如此。**接下来``，正文正常。"
        problems, _, _ = CHECK.check_bold(text)
        self.assertFalse(problems)

    def test_longer_backtick_run_inside_code_span_does_not_close_it(self):
        text = "正文 ``代码 ````` **结论。**接下来``，后文正常。"
        problems, fixed, count = CHECK.check_bold(text)
        self.assertFalse(problems)
        self.assertEqual(text, fixed)
        self.assertEqual(0, count)

    def test_multiline_inline_code_is_not_modified(self):
        text = "正文。\n前缀`代码\n**结论。**接下来\n代码`后缀\n正文。\n"
        problems, fixed, count = CHECK.check_bold(text)
        self.assertFalse(problems)
        self.assertEqual(text, fixed)
        self.assertEqual(0, count)

    def test_inline_html_and_image_alt_are_not_modified(self):
        cases = [
            '正文：<span data-label="**结论。**接下来">标签</span>。',
            '正文：![**结论。**接下来](img.png)。',
            '正文。<!--\n**结论。**接下来\n-->后文。',
        ]
        for text in cases:
            with self.subTest(text=text):
                problems, fixed, count = CHECK.check_bold(text)
                self.assertFalse(problems)
                self.assertEqual(text, fixed)
                self.assertEqual(0, count)

    def test_shorter_fence_does_not_close_longer_fence(self):
        text = "````\n**结论。**后文\n```\n**第二项。**后文\n````\n"
        problems, fixed, count = CHECK.check_bold(text)
        self.assertFalse(problems)
        self.assertEqual(text, fixed)
        self.assertEqual(0, count)

    def test_thematic_break_is_not_bold(self):
        text = "正文\n\n***\n\n后文。\n"
        problems, _, _ = CHECK.check_bold(text)
        self.assertFalse(problems)

    def test_bom_frontmatter_and_yaml_ellipsis_are_masked(self):
        text = '\ufeff---\nsummary: "**结论。**接下来"\n...\n正文正常。\n'
        problems, _, _ = CHECK.check_bold(text)
        self.assertFalse(problems)

    def test_bold_can_span_soft_line_break(self):
        text = "**跨\n行**内容保持连续。"
        problems, _, _ = CHECK.check_bold(text)
        self.assertFalse(problems)

    def test_structured_table_punctuation_is_not_a_hard_failure(self):
        text = "| 指标 | 数值 |\n|---|---|\n| 收入 | 82%,利润率 |\n"
        self.assertFalse(CHECK.check_misc(text))

    def test_inline_code_does_not_trigger_bold_error(self):
        text = "示例代码为 `**结论如此。**接下来`，正文保持正常。"
        problems, _, _ = CHECK.check_bold(text)
        self.assertFalse(problems)

    def test_internal_labels_are_contextual_not_hard_failures(self):
        text = "L1、Tier 2 和方案 A 是用户定义的正式标签。"
        self.assertFalse(CHECK.check_misc(text))
        self.assertTrue(any("代号" in item for item in CHECK.check_contextual(text)))

    def test_common_table_reference_forms_are_recognized(self):
        for ref in ("见表 1 显示收入。", "如表1所示，收入增长。", "参见表 1："):
            with self.subTest(ref=ref):
                text = "**表 1　收入比较**\n\n%s" % ref
                self.assertFalse(CHECK.check_numbering(text, "表"))

    def test_unreferenced_figure_is_reported(self):
        text = "**图 1　收入趋势**\n\n正文没有引用该图。"
        self.assertTrue(any("未被正文引用" in item
                            for item in CHECK.check_numbering(text, "图")))

    def test_heading_level_jump_is_reported(self):
        text = "# 标题\n\n## 第一节\n\n#### 跳级标题\n"
        self.assertTrue(any("跳到" in item for item in CHECK.check_hierarchy(text)))

    def test_soft_line_breaks_are_one_paragraph_for_hierarchy(self):
        body = "\n".join("同一段的第%d行。" % i for i in range(12))
        text = "# 标题\n\n### 小节\n" + body
        self.assertFalse(any("直属正文" in item for item in CHECK.check_hierarchy(text)))

    def test_benwen_frequency_is_not_a_style_error(self):
        text = "。".join(["本文说明口径"] * 8)
        self.assertFalse(any(hit[2] == "本文" for hit in CHECK.check_traces(text)))

    def test_common_false_positives_are_ignored(self):
        text = "该结果形成了一项非显然结构。管理层给出的答案是暂不调整价格。"
        self.assertFalse([hit for hit in CHECK.check_style_patterns(text) if hit[0]])


class DeliveryTargetTest(unittest.TestCase):
    """交付目标参数与退出码契约。空行一项的判定取决于交付目标，
    不传目标时必须维持旧行为，否则会破坏既有调用。"""

    LOOSE = "# 标题\n\n第一段。\n\n第二段。\n"      # 段落之间留空行
    TIGHT = "# 标题\n第一段。\n第二段。\n"           # Obsidian 写法

    def run_script(self, script, *args):
        path = SKILL_ROOT / "scripts" / script
        return subprocess.run([sys.executable, str(path)] + list(args),
                              capture_output=True, text=True)

    def written(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_no_target_keeps_old_behaviour(self):
        path = self.written(self.LOOSE)
        self.assertEqual(0, self.run_script("check.py", path).returncode)

    def test_obsidian_target_fails_on_removable_blank_lines(self):
        path = self.written(self.LOOSE)
        result = self.run_script("check.py", path, "--target", "obsidian")
        self.assertEqual(2, result.returncode)
        self.assertIn("目标为 obsidian", result.stdout)

    def test_obsidian_target_passes_when_tight(self):
        path = self.written(self.TIGHT)
        self.assertEqual(0, self.run_script("check.py", path, "--target", "obsidian").returncode)

    def test_markdown_target_keeps_blank_lines(self):
        path = self.written(self.LOOSE)
        result = self.run_script("check.py", path, "--target", "markdown")
        self.assertEqual(0, result.returncode)
        self.assertIn("不适用", result.stdout)

    def test_unknown_target_is_usage_error(self):
        path = self.written(self.LOOSE)
        self.assertEqual(1, self.run_script("check.py", path, "--target", "docx").returncode)

    def test_equals_form_of_target_is_accepted(self):
        path = self.written(self.LOOSE)
        self.assertEqual(2, self.run_script("check.py", path, "--target=obsidian").returncode)

    def test_deliver_requires_explicit_target(self):
        path = self.written(self.LOOSE)
        self.assertEqual(1, self.run_script("deliver.py", path).returncode)

    def test_deliver_preview_does_not_write(self):
        path = self.written(self.LOOSE)
        before = Path(path).read_text(encoding="utf-8")
        self.assertEqual(2, self.run_script("deliver.py", path, "--target", "obsidian").returncode)
        self.assertEqual(before, Path(path).read_text(encoding="utf-8"))

    def test_deliver_apply_then_passes(self):
        path = self.written(self.LOOSE)
        applied = self.run_script("deliver.py", path, "--target", "obsidian", "--apply")
        self.assertEqual(0, applied.returncode)
        self.assertEqual(self.TIGHT, Path(path).read_text(encoding="utf-8"))
        for leftover in Path(path).parent.glob(Path(path).name + ".*.bak"):
            leftover.unlink()

    def test_target_without_value_is_usage_error(self):
        path = self.written(self.LOOSE)
        self.assertEqual(1, self.run_script("check.py", path, "--target").returncode)
        self.assertEqual(1, self.run_script("deliver.py", path, "--target").returncode)

    def test_unknown_option_is_rejected(self):
        path = self.written(self.LOOSE)
        self.assertEqual(1, self.run_script("check.py", path, "--tidy").returncode)
        self.assertEqual(1, self.run_script("deliver.py", path, "--target", "obsidian", "--dry").returncode)

    def test_repeated_target_is_rejected(self):
        path = self.written(self.LOOSE)
        result = self.run_script("check.py", path, "--target", "obsidian", "--target", "markdown")
        self.assertEqual(1, result.returncode)

    def test_fix_option_still_accepted(self):
        path = self.written("# 标题\n**结论如此。**接下来看第二段。\n")
        result = self.run_script("check.py", path, "--fix")
        self.assertIn("已自动修复加粗标点位置", result.stdout)
        for leftover in Path(path).parent.glob(Path(path).name + ".bak.*"):
            leftover.unlink()

    def test_deliver_passes_through_checker_usage_error(self):
        """检查器的非 2 退出码不能被并入 2，否则会掩盖执行错误。"""
        missing = str(Path(tempfile.gettempdir()) / "report-writer-absent.md")
        result = self.run_script("deliver.py", missing, "--target", "obsidian")
        self.assertEqual(1, result.returncode)

    def test_markdown_delivery_leaves_file_unchanged(self):
        path = self.written(self.LOOSE)
        before = Path(path).read_text(encoding="utf-8")
        self.assertEqual(0, self.run_script("deliver.py", path, "--target", "markdown").returncode)
        self.assertEqual(before, Path(path).read_text(encoding="utf-8"))

    def test_other_format_errors_survive_cleanup(self):
        """空行清理后仍有格式问题时，交付入口不得放行。"""
        path = self.written("# 标题\n\n**未闭合加粗。\n\n第二段。\n")
        result = self.run_script("deliver.py", path, "--target", "obsidian", "--apply")
        self.assertEqual(2, result.returncode)
        for leftover in Path(path).parent.glob(Path(path).name + ".*.bak"):
            leftover.unlink()

    def test_deliver_rejects_apply_for_markdown(self):
        path = self.written(self.LOOSE)
        self.assertEqual(1, self.run_script("deliver.py", path, "--target", "markdown", "--apply").returncode)


class EvalSuiteTest(unittest.TestCase):
    def test_eval_files_and_expectations_are_complete(self):
        data = json.loads((SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual("report-writer", data["skill_name"])
        self.assertEqual(9, len(data["evals"]))
        for item in data["evals"]:
            with self.subTest(eval_id=item["id"]):
                self.assertTrue(item.get("expectations"))
                for relative_path in item.get("files", []):
                    self.assertTrue((SKILL_ROOT / relative_path).is_file(), relative_path)


if __name__ == "__main__":
    unittest.main()
