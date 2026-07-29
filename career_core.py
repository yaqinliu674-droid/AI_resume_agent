"""Business logic for the AI job-search assistant.

The module intentionally has no Streamlit imports. It can be exercised with
unit tests and reused by the UI without leaking resume text to logs.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable

from docx import Document
from openai import OpenAI
from pypdf import PdfReader


GENERIC_AI_PHRASES = (
    "显著提升",
    "有效增强",
    "全面负责",
    "深度参与",
    "赋能",
    "助力",
    "极大提高",
    "获得一致好评",
    "提升用户体验",
    "增强品牌影响力",
)

RESPONSIBILITY_UPGRADES = ("主导", "独立负责", "全面负责", "牵头")

FOLLOW_UP_FALLBACKS = (
    {
        "focus": "responsibility",
        "question": "在最相关的一段经历里，你本人具体负责了哪些部分？",
        "choices": ["独立完成", "主导其中一部分", "参与执行", "协助他人"],
    },
    {
        "focus": "delivery",
        "question": "这段经历最终完成或交付了什么？",
        "choices": ["可运行功能或页面", "报告或方案", "作品或内容", "活动或协作任务"],
    },
    {
        "focus": "evidence",
        "question": "是否有可确认的数量、时间、规模、反馈或修改轮次？",
        "choices": ["有准确数据", "有大致范围", "只有交付结果", "没有可确认数据"],
    },
)

COMMON_SKIP_OPTIONS = ("不记得", "没有数据", "跳过", "先按现有内容生成")

ROLE_RULES = (
    (
        ("公众号", "小红书", "文案", "内容", "剪映", "canva"),
        "内容运营助理",
        "围绕选题、内容制作、发布和基础数据复盘开展工作。",
    ),
    (
        ("excel", "数据", "报表", "统计", "python", "sql"),
        "数据运营助理",
        "整理业务数据、维护表格或报表，并支持基础分析与跟进。",
    ),
    (
        ("活动", "社团", "组织", "协调", "沟通", "志愿"),
        "运营助理",
        "协助活动、流程、资料和跨人协作，把任务推进到交付。",
    ),
    (
        ("网页", "网站", "前端", "ui", "unity", "交互", "设计"),
        "产品/设计助理",
        "协助需求梳理、原型或界面制作、测试和迭代记录。",
    ),
    (
        ("销售", "门店", "客户", "接待", "客服"),
        "客户运营助理",
        "处理咨询、信息记录、需求跟进和基础客户维护。",
    ),
)


class UserFacingError(RuntimeError):
    """An exception whose message is safe to show directly to a tester."""


@dataclass(slots=True)
class ModelSettings:
    api_key: str = ""
    workspace_id: str = ""
    model: str = "qwen3.7-plus"
    offline: bool = False


def clean_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if limit is not None:
        return text[:limit]
    return text


def compact_lines(text: str, limit: int = 8) -> list[str]:
    """Return meaningful, deduplicated source lines without inventing content."""
    lines: list[str] = []
    for raw in re.split(r"[\r\n]+", clean_text(text)):
        line = re.sub(r"^\s*[-*•\d.、）)]+\s*", "", raw).strip()
        if len(line) < 4 or line in lines:
            continue
        lines.append(line[:180])
        if len(lines) >= limit:
            break
    return lines


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    """Extract likely skills and requirements using deterministic text rules."""
    candidates: list[str] = []
    for line in compact_lines(text, limit=30):
        for item in re.split(r"[，,；;、/]|以及|并且|和", line):
            item = re.sub(
                r"^(负责|具备|熟悉|掌握|要求|任职资格|岗位职责|优先|能够|会使用)\s*",
                "",
                item,
                flags=re.IGNORECASE,
            ).strip(" ：:")
            if 2 <= len(item) <= 24 and item not in candidates:
                candidates.append(item)
            if len(candidates) >= limit:
                return candidates
    return candidates


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse model JSON with safe recovery from Markdown fences."""
    text = clean_text(raw)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    first, last = text.find("{"), text.rfind("}")
    if first < 0 or last <= first:
        raise UserFacingError("模型返回内容无法解析。已保留当前输入，请重试。")
    try:
        value = json.loads(text[first : last + 1])
    except json.JSONDecodeError as exc:
        raise UserFacingError("模型返回内容无法解析。已保留当前输入，请重试。") from exc
    if not isinstance(value, dict):
        raise UserFacingError("模型返回的结果结构不正确。已保留当前输入，请重试。")
    return value


def string_list(value: Any, limit: int, fallback: list[str] | None = None) -> list[str]:
    if not isinstance(value, list):
        return list(fallback or [])
    result: list[str] = []
    for item in value:
        text = clean_text(item, 240)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result or list(fallback or [])


def numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?%?", clean_text(text)))


def has_unsupported_claim(text: str, source: str) -> bool:
    """Flag common unsupported metrics or responsibility upgrades."""
    source_lower = source.lower()
    if not numbers_in(text).issubset(numbers_in(source)):
        return True
    if any(term in text and term not in source for term in RESPONSIBILITY_UPGRADES):
        return True
    if any(term in text and term not in source for term in GENERIC_AI_PHRASES):
        return True
    if any(token in text for token in ("万元", "收益", "满意度", "增长率")) and not any(
        token in source for token in ("万元", "收益", "满意度", "增长率")
    ):
        return True
    return False


def normalize_questions(value: Any) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    if not isinstance(value, list):
        value = []
    for index, item in enumerate(value[:3]):
        if not isinstance(item, dict):
            continue
        question = clean_text(item.get("question"), 180)
        if not question:
            continue
        choices = string_list(item.get("choices"), 4)
        default = FOLLOW_UP_FALLBACKS[min(index, 2)]
        questions.append(
            {
                "id": clean_text(item.get("id"), 30) or f"q{index + 1}",
                "focus": clean_text(item.get("focus"), 30) or default["focus"],
                "question": question,
                "choices": choices or list(default["choices"]),
                "skip_options": list(COMMON_SKIP_OPTIONS),
            }
        )
    if not questions:
        for index, item in enumerate(FOLLOW_UP_FALLBACKS):
            questions.append(
                {
                    "id": f"q{index + 1}",
                    "focus": item["focus"],
                    "question": item["question"],
                    "choices": list(item["choices"]),
                    "skip_options": list(COMMON_SKIP_OPTIONS),
                }
            )
    return questions[:3]


def fallback_diagnosis(position_name: str, jd: str, resume: str) -> dict[str, Any]:
    requirements = extract_keywords(jd, 5) or compact_lines(jd, 5)
    resume_lower = resume.lower()
    evidence = [
        req
        for req in requirements
        if any(token.lower() in resume_lower for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", req))
    ]
    evidence = evidence[:5]
    risks: list[str] = []
    if not any(char.isdigit() for char in resume):
        risks.append("经历缺少可确认的数量、时间、规模或交付证据")
    if len(compact_lines(resume, 12)) < 4:
        risks.append("现有经历描述较少，招聘方可能难以判断具体责任")
    missing_requirements = [item for item in requirements if item not in evidence]
    if missing_requirements:
        risks.append(f"材料暂未证明：{missing_requirements[0]}")
    while len(risks) < 3:
        risks.append("部分岗位要求目前只能标记为未知，不能直接视为不符合")
    return {
        "position_name": position_name,
        "requirements": requirements[:5],
        "evidence": evidence or ["已提供真实经历文本，但尚未找到可直接确认的 JD 关键词证据"],
        "risks": risks[:3],
        "unknowns": missing_requirements[:5] or ["职责边界、交付结果和证据强度仍需确认"],
        "priority": "优先补清最相关经历中的本人责任、具体交付和可验证证据。",
        "confidence": "中" if evidence else "低",
        "mode": "conservative",
    }


def fallback_questions(
    diagnosis: dict[str, Any], resume: str
) -> list[dict[str, Any]]:
    context = compact_lines(resume, 3)
    questions = [dict(item) for item in FOLLOW_UP_FALLBACKS]
    if context:
        questions[0]["question"] = (
            f"你写到“{context[0][:48]}”。其中哪些工作是你本人负责的？"
        )
    requirements = diagnosis.get("requirements") or []
    if requirements:
        questions[1]["question"] = (
            f"为了证明“{clean_text(requirements[0], 30)}”，你最终完成或交付了什么？"
        )
    return normalize_questions(questions)


def build_conservative_resume(position_name: str, resume: str) -> list[dict[str, str]]:
    bullets: list[dict[str, str]] = []
    for line in compact_lines(resume, 12):
        bullets.append(
            {
                "text": line,
                "source_quote": line,
                "fact_status": "已确认事实",
            }
        )
    if not bullets:
        bullets.append(
            {
                "text": "当前没有可确认的经历正文，建议先整理课程、个人项目、兼职、社团或作品。",
                "source_quote": "",
                "fact_status": "信息不足",
            }
        )
    return bullets


def sanitize_resume_bullets(value: Any, source: str) -> tuple[list[dict[str, str]], list[str]]:
    safe: list[dict[str, str]] = []
    rejected: list[str] = []
    if not isinstance(value, list):
        value = []
    for item in value[:16]:
        if not isinstance(item, dict):
            continue
        text = clean_text(item.get("text"), 260)
        quote = clean_text(item.get("source_quote"), 200)
        status = clean_text(item.get("fact_status"), 30) or "已确认事实"
        quote_is_supported = bool(quote and quote in source)
        estimate_is_confirmed = status == "用户确认的估算" and any(
            marker in text for marker in ("约", "近", "大致", "超过", "至")
        )
        if (
            not text
            or has_unsupported_claim(text, source)
            or (not quote_is_supported and not estimate_is_confirmed)
        ):
            rejected.append(text or "空条目")
            continue
        safe.append({"text": text, "source_quote": quote, "fact_status": status})
    return safe, rejected


def fallback_final_result(
    position_name: str,
    jd: str,
    resume: str,
    diagnosis: dict[str, Any],
    answers: list[dict[str, str]],
    reason: str = "",
) -> dict[str, Any]:
    answer_text = "\n".join(
        clean_text(item.get("answer")) for item in answers if clean_text(item.get("answer"))
    )
    source = f"{resume}\n{answer_text}"
    bullets = build_conservative_resume(position_name, resume)
    questions = [
        f"请说明你在与“{item}”相关经历中的具体责任和交付。"
        for item in (diagnosis.get("requirements") or [])[:3]
    ]
    questions += [
        "这段经历中哪些内容由你独立完成，哪些是团队协作？",
        "如果没有增长数据，你可以用哪些数量、时间、交付或迭代事实证明完成度？",
    ]
    review_notes = [
        "已执行确定性真实性检查：没有新增来源中不存在的数字。",
        "未把课程、个人或练习项目冒充为企业或客户项目。",
        "未确认的信息保留在待确认区，不写入简历正文。",
    ]
    if reason:
        review_notes.insert(0, f"AI 服务暂不可用，当前展示保守版本：{reason}")
    return {
        "match_conclusion": (
            f"针对“{position_name}”，当前材料可用于初步判断，但仍需结合硬性条件、已有证据和未知信息谨慎投递。"
        ),
        "hard_requirements": "需逐项核对 JD；当前不以单一分数代替判断。",
        "requirements": string_list(diagnosis.get("requirements"), 5),
        "risks": string_list(diagnosis.get("risks"), 3),
        "strengths": string_list(diagnosis.get("evidence"), 5),
        "before_after": [
            {
                "before": item["source_quote"],
                "after": item["text"],
                "basis": item["fact_status"],
            }
            for item in bullets[:5]
        ],
        "resume_bullets": bullets,
        "unknowns": string_list(diagnosis.get("unknowns"), 5),
        "interview_questions": questions[:5],
        "review": {
            "status": "保守通过",
            "notes": review_notes,
            "rejected_claims": [],
        },
        "confidence": clean_text(diagnosis.get("confidence")) or "低",
        "source": source,
        "offline": bool(reason),
    }


def build_base_resume(data: dict[str, str]) -> dict[str, Any]:
    sections: list[dict[str, str]] = []
    labels = (
        ("education", "教育背景"),
        ("experience", "实习、兼职或实践经历"),
        ("projects", "课程、个人或作品项目"),
        ("skills", "技能、工具与证书"),
        ("transferable", "可迁移技能"),
    )
    for key, label in labels:
        value = clean_text(data.get(key))
        if value:
            sections.append({"title": label, "content": value})
    if not sections:
        raise UserFacingError("至少填写一项真实信息，例如教育、经历、项目或工具。")
    role = clean_text(data.get("responsibility")) or "参与"
    plain = "\n\n".join(f"## {item['title']}\n{item['content']}" for item in sections)
    return {
        "sections": sections,
        "responsibility": role,
        "plain_text": plain,
        "notice": f"责任程度按“{role}”记录；未增加任何未填写的经历或结果。",
    }


def fallback_direction(profile: dict[str, str], reason: str = "") -> dict[str, Any]:
    evidence = "\n".join(clean_text(value) for value in profile.values())
    evidence_lower = evidence.lower()
    excluded = clean_text(profile.get("excluded"))
    if excluded in {"暂时没有偏好", "跳过", "不确定"}:
        excluded = ""
    matched_rules = [
        rule for rule in ROLE_RULES if any(token in evidence_lower for token in rule[0])
    ]
    for rule in ROLE_RULES:
        if rule not in matched_rules:
            matched_rules.append(rule)
        if len(matched_rules) >= 3:
            break
    roles: list[dict[str, Any]] = []
    categories = ("直接可投", "相邻方向", "探索方向")
    for category, rule in zip(categories, matched_rules[:3]):
        title, daily = rule[1], rule[2]
        direct = category == "直接可投" and any(
            token in evidence_lower for token in rule[0]
        )
        roles.append(
            {
                "category": category,
                "title": title,
                "daily_work": daily,
                "why": "依据你提供的工具、项目或协作经历做可迁移能力映射。",
                "evidence": compact_lines(evidence, 1)[0]
                if compact_lines(evidence, 1)
                else "当前证据较少，仅作为低成本探索方向。",
                "existing": "仅采用你已填写的经历和技能。",
                "gap": "仍需用一个真实 JD 核对硬性条件，并补充可验证作品或交付。",
                "preference_risk": (
                    f"你明确不接受：{excluded}。查看 JD 时应排除相关内容。"
                    if excluded
                    else "尚未确认不接受的工作内容。"
                ),
                "apply_now": "可以先查看真实 JD" if direct else "先完成低成本试岗任务",
                "next_action": f"搜索 5 个“{title}”真实 JD，记录重复要求和自己能证明的证据。",
            }
        )
    cities = {
        "tier": "第一梯队：杭州、南京、苏州",
        "summary": (
            "杭州相关岗位和产业机会较多，但竞争和生活成本较高；南京的岗位机会、"
            "进入难度和生活压力相对均衡；苏州纯互联网岗位总量未必最多，但制造业"
            "数字化、软件、电商和品牌相关职能值得关注。"
        ),
        "search_roles": [item["title"] for item in roles],
        "notice": "城市建议用于辅助扩大搜索范围，不代表实时岗位数量或录取结果。",
    }
    micro_project = {
        "duration": "3 至 7 天",
        "task": "选择一个真实岗位方向，完成一份岗位要求拆解和一件可展示的小作品。",
        "deliverable": "岗位关键词表、作品或分析文档、修改记录和一段真实复盘。",
        "resume_usage": "完成后按“个人项目/练习项目”如实标记，不冒充企业或客户项目。",
    }
    return {
        "roles": roles,
        "cities": cities,
        "micro_project": micro_project,
        "offline": bool(reason),
        "notice": (
            f"AI 服务暂不可用，当前为规则映射的保守建议：{reason}"
            if reason
            else "建议以真实 JD 和个人选择继续验证，不把推荐当作录取概率。"
        ),
    }


def extract_resume_file(filename: str, payload: bytes) -> str:
    suffix = os.path.splitext(filename.lower())[1]
    try:
        if suffix in {".txt", ".md"}:
            for encoding in ("utf-8-sig", "utf-8", "gb18030"):
                try:
                    text = payload.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise UserFacingError("文本文件编码无法识别，请另存为 UTF-8 后重试。")
        elif suffix == ".pdf":
            reader = PdfReader(BytesIO(payload))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif suffix == ".docx":
            document = Document(BytesIO(payload))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        else:
            raise UserFacingError("文件格式不支持。请上传 PDF、Word（.docx）、TXT 或 Markdown。")
    except UserFacingError:
        raise
    except Exception as exc:
        kind = "PDF" if suffix == ".pdf" else "Word"
        raise UserFacingError(
            f"{kind} 文件无法解析。请确认文件未加密、未损坏，或改为粘贴文字。"
        ) from exc
    text = clean_text(text)
    if not text:
        raise UserFacingError("简历正文为空或无法读取，请改为粘贴文字。")
    return text


def map_model_error(exc: Exception) -> UserFacingError:
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return UserFacingError("请求超时。已保留当前输入，请稍后重试或使用保守版本。")
    if any(token in message for token in ("quota", "insufficient", "余额", "额度")):
        return UserFacingError("模型免费额度可能已用尽。可先使用保守版本，稍后再重试。")
    if any(token in message for token in ("401", "authentication", "api key")):
        return UserFacingError("AI 服务配置无效。请联系测试负责人检查云端 Secrets。")
    return UserFacingError("AI 服务暂时不可用。已保留当前输入，可继续使用保守版本。")


class CareerAnalyzer:
    """Stepwise Qwen workflow with conservative local fallbacks."""

    def __init__(
        self,
        settings: ModelSettings,
        caller: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self._caller = caller
        self._client: OpenAI | None = None

    @property
    def available(self) -> bool:
        return bool(
            self._caller
            or (
                self.settings.api_key
                and self.settings.workspace_id
                and not self.settings.offline
            )
        )

    def _call(self, step: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._caller:
            return self._caller(step, payload)
        if not self.available:
            raise UserFacingError("AI 服务尚未配置")
        if self._client is None:
            base_url = (
                f"https://{self.settings.workspace_id}.cn-beijing.maas.aliyuncs.com/"
                "compatible-mode/v1"
            )
            self._client = OpenAI(
                api_key=self.settings.api_key,
                base_url=base_url,
                timeout=60.0,
                max_retries=1,
            )
        prompts = self._prompts(step, payload)
        try:
            response = self._client.chat.completions.create(
                model=self.settings.model,
                messages=prompts,
                temperature=0.25,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            content = response.choices[0].message.content or ""
            return parse_json_object(content)
        except UserFacingError:
            raise
        except Exception as exc:
            raise map_model_error(exc) from exc

    @staticmethod
    def _prompts(step: str, payload: dict[str, Any]) -> list[dict[str, str]]:
        safety = (
            "只使用用户提供的事实。不得补写公司、客户、职责、数字、商业结果、上线背景或证书。"
            "课程/个人/练习项目必须保留真实标签。没有数据时使用交付、时间、规模、责任或迭代证据，"
            "不得虚构百分比。仅输出合法 JSON。"
        )
        schemas = {
            "diagnosis": (
                '{"requirements":["3到5项"],"evidence":["已有证据"],"risks":["恰好3项"],'
                '"unknowns":["未知信息"],"priority":"优先修改内容","confidence":"高/中/低"}'
            ),
            "questions": (
                '{"questions":[{"id":"q1","focus":"responsibility/delivery/evidence",'
                '"question":"结合具体经历的问题","choices":["4个常见选项"]}]}，最多3题'
            ),
            "rewrite": (
                '{"match_conclusion":"结论","hard_requirements":"硬性条件判断",'
                '"requirements":["看重事项"],"risks":["3项"],"strengths":["真实优势"],'
                '"before_after":[{"before":"原文","after":"改写","basis":"事实依据"}],'
                '"resume_bullets":[{"text":"动作+对象+方法/难点+可验证结果",'
                '"source_quote":"必须原样引用输入中的事实片段","fact_status":"已确认事实/用户确认的估算"}],'
                '"unknowns":["待确认"],"interview_questions":["追问"],"confidence":"高/中/低"}'
            ),
            "review": (
                '{"status":"通过/需修正","notes":["真实性、夸大、空话、相关性、面试风险检查"],'
                '"rejected_claims":["必须移除的表述"],"replacement_bullets":['
                '{"text":"安全替代","source_quote":"原样事实片段","fact_status":"已确认事实"}]}'
            ),
            "direction": (
                '{"roles":[{"category":"直接可投/相邻方向/探索方向","title":"岗位",'
                '"daily_work":"日常工作","why":"原因","evidence":"真实依据","existing":"已有",'
                '"gap":"缺口","preference_risk":"偏好冲突","apply_now":"是否直投",'
                '"next_action":"具体行动"}],"cities":{"tier":"第一梯队含多个城市",'
                '"summary":"各自优势与现实代价","search_roles":["岗位类型"],'
                '"notice":"城市建议用于辅助扩大搜索范围，不代表实时岗位数量或录取结果。"},'
                '"micro_project":{"duration":"3至7天","task":"任务","deliverable":"交付",'
                '"resume_usage":"真实写法"},"notice":"边界说明"}'
            ),
            "revise": (
                '{"replacement":"仅更新目标片段后的内容","basis":"使用了哪些已确认事实",'
                '"status":"已确认事实/用户确认的估算/待确认信息"}'
            ),
        }
        user_payload = json.dumps(payload, ensure_ascii=False)
        return [
            {
                "role": "system",
                "content": f"你是严谨的中文求职顾问。{safety}",
            },
            {
                "role": "user",
                "content": (
                    f"当前独立步骤：{step}。严格输出结构：{schemas[step]}。\n"
                    f"输入：{user_payload}"
                ),
            },
        ]

    def diagnose(self, position_name: str, jd: str, resume: str) -> dict[str, Any]:
        fallback = fallback_diagnosis(position_name, jd, resume)
        if not self.available:
            fallback["notice"] = "AI 服务尚未配置，当前为保守初步诊断。"
            return fallback
        try:
            raw = self._call(
                "diagnosis",
                {"position_name": position_name, "job_description": jd, "resume": resume},
            )
        except UserFacingError as exc:
            fallback["notice"] = str(exc)
            fallback["mode"] = "conservative"
            return fallback
        return {
            "position_name": position_name,
            "requirements": string_list(raw.get("requirements"), 5, fallback["requirements"]),
            "evidence": string_list(raw.get("evidence"), 6, fallback["evidence"]),
            "risks": string_list(raw.get("risks"), 3, fallback["risks"])[:3],
            "unknowns": string_list(raw.get("unknowns"), 6, fallback["unknowns"]),
            "priority": clean_text(raw.get("priority"), 300) or fallback["priority"],
            "confidence": clean_text(raw.get("confidence"), 10) or fallback["confidence"],
            "mode": "ai",
        }

    def questions(
        self, diagnosis: dict[str, Any], resume: str
    ) -> list[dict[str, Any]]:
        fallback = fallback_questions(diagnosis, resume)
        if not self.available:
            return fallback
        try:
            raw = self._call(
                "questions",
                {"diagnosis": diagnosis, "resume": resume},
            )
            return normalize_questions(raw.get("questions"))
        except UserFacingError:
            return fallback

    def finalize(
        self,
        position_name: str,
        jd: str,
        resume: str,
        diagnosis: dict[str, Any],
        answers: list[dict[str, str]],
    ) -> dict[str, Any]:
        if not self.available:
            return fallback_final_result(
                position_name,
                jd,
                resume,
                diagnosis,
                answers,
                "AI 服务尚未配置",
            )
        payload = {
            "position_name": position_name,
            "diagnosis": diagnosis,
            "resume": resume,
            "confirmed_answers": answers,
        }
        try:
            draft = self._call("rewrite", payload)
            source = resume + "\n" + "\n".join(
                clean_text(item.get("answer")) for item in answers
            )
            safe_bullets, rejected = sanitize_resume_bullets(
                draft.get("resume_bullets"), source
            )
            if not safe_bullets:
                safe_bullets = build_conservative_resume(position_name, resume)
            review = self._call(
                "review",
                {
                    "source_facts": source,
                    "draft": {**draft, "resume_bullets": safe_bullets},
                    "automatic_rejections": rejected,
                },
            )
            replacement, second_rejected = sanitize_resume_bullets(
                review.get("replacement_bullets"), source
            )
            if replacement:
                safe_bullets = replacement
            rejected += second_rejected
            return {
                "match_conclusion": clean_text(draft.get("match_conclusion"), 500),
                "hard_requirements": clean_text(draft.get("hard_requirements"), 500),
                "requirements": string_list(
                    draft.get("requirements"), 5, diagnosis.get("requirements")
                ),
                "risks": string_list(draft.get("risks"), 3, diagnosis.get("risks"))[:3],
                "strengths": string_list(
                    draft.get("strengths"), 6, diagnosis.get("evidence")
                ),
                "before_after": [
                    item
                    for item in draft.get("before_after", [])[:6]
                    if isinstance(item, dict)
                ],
                "resume_bullets": safe_bullets,
                "unknowns": string_list(
                    draft.get("unknowns"), 6, diagnosis.get("unknowns")
                ),
                "interview_questions": string_list(
                    draft.get("interview_questions"), 6
                ),
                "review": {
                    "status": clean_text(review.get("status"), 30) or "已复核",
                    "notes": string_list(review.get("notes"), 8),
                    "rejected_claims": rejected
                    + string_list(review.get("rejected_claims"), 8),
                },
                "confidence": clean_text(draft.get("confidence"), 10)
                or diagnosis.get("confidence", "低"),
                "offline": False,
            }
        except UserFacingError as exc:
            return fallback_final_result(
                position_name, jd, resume, diagnosis, answers, str(exc)
            )

    def direction(self, profile: dict[str, str]) -> dict[str, Any]:
        fallback = fallback_direction(profile)
        if not self.available:
            return fallback_direction(profile, "AI 服务尚未配置")
        try:
            raw = self._call("direction", {"profile": profile})
        except UserFacingError as exc:
            return fallback_direction(profile, str(exc))
        roles: list[dict[str, str]] = []
        if isinstance(raw.get("roles"), list):
            for item in raw["roles"][:3]:
                if not isinstance(item, dict):
                    continue
                roles.append(
                    {
                        key: clean_text(item.get(key), 500)
                        for key in (
                            "category",
                            "title",
                            "daily_work",
                            "why",
                            "evidence",
                            "existing",
                            "gap",
                            "preference_risk",
                            "apply_now",
                            "next_action",
                        )
                    }
                )
        if not roles:
            roles = fallback["roles"]
        cities = raw.get("cities") if isinstance(raw.get("cities"), dict) else {}
        micro = (
            raw.get("micro_project")
            if isinstance(raw.get("micro_project"), dict)
            else {}
        )
        return {
            "roles": roles,
            "cities": {
                "tier": clean_text(cities.get("tier"), 100)
                or fallback["cities"]["tier"],
                "summary": clean_text(cities.get("summary"), 900)
                or fallback["cities"]["summary"],
                "search_roles": string_list(
                    cities.get("search_roles"), 6, fallback["cities"]["search_roles"]
                ),
                "notice": clean_text(cities.get("notice"), 200)
                or fallback["cities"]["notice"],
            },
            "micro_project": {
                key: clean_text(micro.get(key), 500)
                or fallback["micro_project"][key]
                for key in ("duration", "task", "deliverable", "resume_usage")
            },
            "notice": clean_text(raw.get("notice"), 300)
            or fallback["notice"],
            "offline": False,
        }

    def revise(
        self,
        original_facts: str,
        current_text: str,
        feedback: str,
    ) -> dict[str, str]:
        if not self.available:
            return {
                "replacement": current_text,
                "basis": "AI 服务不可用，已保留原文，未传播未确认修改。",
                "status": "已确认事实",
            }
        try:
            raw = self._call(
                "revise",
                {
                    "original_facts": original_facts,
                    "current_text": current_text,
                    "feedback": feedback,
                },
            )
            replacement = clean_text(raw.get("replacement"), 800)
            if not replacement or has_unsupported_claim(replacement, original_facts):
                replacement = current_text
                status = "未通过真实性检查，已保留原文"
            else:
                status = clean_text(raw.get("status"), 40) or "已确认事实"
            return {
                "replacement": replacement,
                "basis": clean_text(raw.get("basis"), 300)
                or "仅使用原始事实进行局部修改。",
                "status": status,
            }
        except UserFacingError as exc:
            return {
                "replacement": current_text,
                "basis": str(exc),
                "status": "已保留原文",
            }
