import os
import unittest
from io import BytesIO

from docx import Document

from career_core import (
    CareerAnalyzer,
    ModelSettings,
    UserFacingError,
    build_base_resume,
    extract_resume_file,
    fallback_direction,
    has_unsupported_claim,
)


JD = """
岗位职责：
1. 负责微信公众号内容策划、撰写和发布；
2. 使用 Excel 跟踪内容数据并复盘；
3. 配合活动执行和用户沟通。
任职要求：具备文案能力、数据意识和执行力。
""".strip()


def successful_caller(step, payload):
    if step == "diagnosis":
        return {
            "requirements": ["内容策划", "Excel 数据整理", "活动执行"],
            "evidence": ["用户提供了公众号和 Excel 经历"],
            "risks": ["责任边界不清", "交付数量待确认", "活动职责待确认"],
            "unknowns": ["是否独立完成"],
            "priority": "先补清责任和交付。",
            "confidence": "中",
        }
    if step == "questions":
        return {
            "questions": [
                {
                    "id": "q1",
                    "focus": "responsibility",
                    "question": "公众号工作中你本人负责哪些环节？",
                    "choices": ["选题", "撰写", "排版", "发布"],
                }
            ]
        }
    if step == "rewrite":
        resume = payload["resume"]
        quantitative = "8 篇" if "8 篇" in resume else "40%"
        return {
            "match_conclusion": "已有部分证据，可继续核对硬性条件。",
            "hard_requirements": "未发现可直接否定的硬性条件。",
            "requirements": ["内容策划", "Excel 数据整理"],
            "risks": ["活动职责待确认", "协作边界待确认", "工具熟练度待确认"],
            "strengths": ["提供了公众号经历"],
            "before_after": [
                {
                    "before": "参与公众号内容",
                    "after": f"参与公众号内容并完成 {quantitative}",
                    "basis": "用户原文",
                }
            ],
            "resume_bullets": [
                {
                    "text": f"参与公众号内容策划并完成 {quantitative}",
                    "source_quote": "参与公众号内容策划",
                    "fact_status": "已确认事实",
                }
            ],
            "unknowns": ["具体发布频率"],
            "interview_questions": ["你具体负责哪些环节？"],
            "confidence": "中",
        }
    if step == "review":
        return {
            "status": "通过",
            "notes": ["已检查数字和职责"],
            "rejected_claims": [],
            "replacement_bullets": [],
        }
    if step == "direction":
        return fallback_direction(payload["profile"])
    if step == "revise":
        return {
            "replacement": payload["current_text"],
            "basis": "保留原文",
            "status": "已确认事实",
        }
    raise AssertionError(step)


class MvpPathTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = CareerAnalyzer(
            ModelSettings(), caller=successful_caller
        )

    def test_path_1_resume_jd_with_quantified_result(self):
        resume = "参与公众号内容策划，完成 8 篇图文；使用 Excel 整理数据。"
        diagnosis = self.analyzer.diagnose("新媒体运营", JD, resume)
        questions = self.analyzer.questions(diagnosis, resume)
        result = self.analyzer.finalize(
            "新媒体运营",
            JD,
            resume,
            diagnosis,
            [{"id": questions[0]["id"], "answer": "负责选题和撰写", "status": "confirmed"}],
        )
        self.assertLessEqual(len(questions), 3)
        self.assertIn("8 篇", result["resume_bullets"][0]["text"])
        self.assertFalse(result["offline"])

    def test_path_2_no_numbers_blocks_invented_percentage(self):
        resume = "参与公众号内容策划；使用 Excel 整理内容数据。"
        diagnosis = self.analyzer.diagnose("新媒体运营", JD, resume)
        result = self.analyzer.finalize(
            "新媒体运营", JD, resume, diagnosis, []
        )
        combined = "\n".join(item["text"] for item in result["resume_bullets"])
        self.assertNotIn("40%", combined)
        self.assertTrue(result["review"]["rejected_claims"])

    def test_path_3_vague_experience_skip_all_still_finishes(self):
        offline = CareerAnalyzer(ModelSettings(offline=True))
        resume = "参加过校园公众号，也帮忙做过活动。"
        diagnosis = offline.diagnose("运营助理", JD, resume)
        questions = offline.questions(diagnosis, resume)
        answers = [
            {
                "id": item["id"],
                "question": item["question"],
                "answer": "先按现有内容生成",
                "status": "skipped",
            }
            for item in questions
        ]
        result = offline.finalize("运营助理", JD, resume, diagnosis, answers)
        self.assertTrue(result["resume_bullets"])
        self.assertTrue(result["offline"])
        self.assertEqual(len(questions), 3)

    def test_path_4_course_project_keeps_truthful_label(self):
        base = build_base_resume(
            {
                "education": "市场营销本科",
                "experience": "",
                "projects": "课程项目：完成校园咖啡店内容调研报告。",
                "skills": "Excel",
                "transferable": "资料整理",
                "responsibility": "参与",
            }
        )
        self.assertIn("课程项目", base["plain_text"])
        self.assertNotIn("企业项目", base["plain_text"])
        self.assertNotIn("客户项目", base["plain_text"])

    def test_path_5_base_resume_can_feed_target_flow(self):
        base = build_base_resume(
            {
                "education": "2025 年毕业，新闻学本科",
                "experience": "社团公众号：参与选题和排版。",
                "projects": "",
                "skills": "秀米、Excel",
                "transferable": "",
                "responsibility": "参与",
            }
        )
        diagnosis = self.analyzer.diagnose("内容运营", JD, base["plain_text"])
        self.assertTrue(diagnosis["requirements"])
        self.assertIn("社团公众号", base["plain_text"])

    def test_path_6_direction_change_respects_exclusion(self):
        result = fallback_direction(
            {
                "experience": "做过 Unity 课程项目，负责 UI、测试和素材整理。",
                "continue_old": "不想继续",
                "priority": "岗位优先",
                "excluded": "不想继续游戏开发",
                "urgency": "否",
            }
        )
        self.assertEqual(len(result["roles"]), 3)
        self.assertTrue(
            all("不想继续游戏开发" in item["preference_risk"] for item in result["roles"])
        )

    def test_path_7_minimal_experience_gets_exploration_and_micro_project(self):
        result = fallback_direction(
            {
                "experience": "",
                "continue_old": "不确定",
                "priority": "暂时没有偏好",
                "excluded": "暂时没有偏好",
                "urgency": "不确定",
            }
        )
        self.assertEqual(
            [item["category"] for item in result["roles"]],
            ["直接可投", "相邻方向", "探索方向"],
        )
        self.assertIn("3 至 7 天", result["micro_project"]["duration"])
        self.assertIn("不冒充", result["micro_project"]["resume_usage"])

    def test_path_8_model_failure_falls_back_without_loop(self):
        def failed_caller(step, payload):
            raise UserFacingError("模型免费额度可能已用尽")

        analyzer = CareerAnalyzer(ModelSettings(), caller=failed_caller)
        resume = "参与课程项目，完成报告。"
        diagnosis = analyzer.diagnose("运营助理", JD, resume)
        result = analyzer.finalize("运营助理", JD, resume, diagnosis, [])
        self.assertEqual(diagnosis["mode"], "conservative")
        self.assertTrue(result["offline"])
        self.assertTrue(result["resume_bullets"])

    def test_upload_txt_and_docx(self):
        self.assertEqual(
            extract_resume_file("resume.txt", "真实简历".encode("utf-8")),
            "真实简历",
        )
        buffer = BytesIO()
        document = Document()
        document.add_paragraph("课程项目：完成数据分析报告。")
        document.save(buffer)
        parsed = extract_resume_file("resume.docx", buffer.getvalue())
        self.assertIn("课程项目", parsed)

    def test_unsupported_file_and_claim(self):
        with self.assertRaises(UserFacingError):
            extract_resume_file("resume.exe", b"invalid")
        self.assertTrue(
            has_unsupported_claim(
                "显著提升用户增长 40%",
                "参与公众号内容整理",
            )
        )


class StreamlitSmokeTests(unittest.TestCase):
    def test_landing_has_exactly_three_entry_buttons(self):
        os.environ["AI_RESUME_OFFLINE"] = "1"
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=15).run()
        self.assertFalse(app.exception)
        labels = [button.label for button in app.button]
        self.assertEqual(
            labels,
            ["开始岗位定制", "探索岗位方向", "整理基础简历"],
        )

    def test_target_ui_can_finish_after_skipping_all_questions(self):
        os.environ["AI_RESUME_OFFLINE"] = "1"
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=15).run()
        app.button(key="landing_target").click().run()
        app.text_input(key="target_position").input("Content operations")
        app.text_area(key="target_jd").input(
            "Job requirements include content planning, publishing, Excel data "
            "review, campaign execution, user communication and writing skills. "
            "This is a sufficiently long real JD for testing."
        )
        app.text_area(key="target_resume_input").input(
            "Campus account: participated in planning, layout and publishing; "
            "completed 8 posts and used Excel to organize reading data."
        )
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.radio), 3)
        app.button(key="skip_all_target_questions").click().run()
        self.assertFalse(app.exception)
        headings = [item.value for item in app.subheader]
        self.assertIn("1. 岗位匹配结论", headings)
        self.assertIn("8. 面试官可能追问", headings)
        self.assertEqual(len(app.get("download_button")), 2)

    def test_base_resume_carries_into_target_without_retyping(self):
        os.environ["AI_RESUME_OFFLINE"] = "1"
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=15).run()
        app.button(key="landing_base").click().run()
        app.text_area(key="base_education").input("News major, graduating in 2025.")
        app.text_area(key="base_projects").input(
            "Course project: completed a content research report."
        )
        app.button[1].click().run()
        self.assertFalse(app.exception)
        app.button(key="base_to_target").click().run()
        self.assertFalse(app.exception)
        value = app.text_area(key="target_resume_input").value
        self.assertIn("Course project", value)

    def test_direction_ui_returns_three_categories_and_city_notice(self):
        os.environ["AI_RESUME_OFFLINE"] = "1"
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=15).run()
        app.button(key="landing_direction").click().run()
        app.text_area(key="direction_experience").input(
            "Unity course project: worked on UI, testing and asset organization."
        )
        app.button[1].click().run()
        self.assertFalse(app.exception)
        markdown = [item.value for item in app.markdown]
        self.assertIn(":blue-badge[直接可投]", markdown)
        self.assertIn(":blue-badge[相邻方向]", markdown)
        self.assertIn(":blue-badge[探索方向]", markdown)
        captions = [item.value for item in app.caption]
        self.assertTrue(any("不代表实时岗位数量或录取结果" in text for text in captions))


if __name__ == "__main__":
    unittest.main()
