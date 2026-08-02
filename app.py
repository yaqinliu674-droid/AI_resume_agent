import os
from html import escape

import streamlit as st
from dotenv import load_dotenv

from career_core import (
    COMMON_SKIP_OPTIONS,
    CareerAnalyzer,
    ModelSettings,
    UserFacingError,
    build_base_resume,
    clean_text,
    extract_resume_file,
)


load_dotenv()

st.set_page_config(
    page_title="AI 求职助手",
    page_icon=":material/work:",
    layout="centered",
)


def apply_custom_styles() -> None:
    st.html(
        """
        <style>
        :root {
            --brand-ink: #172033;
            --brand-muted: #5b667a;
            --brand-line: rgba(23, 32, 51, 0.10);
            --brand-surface: rgba(255, 255, 255, 0.88);
            --brand-primary: #334155;
            --brand-accent: #0f766e;
            --brand-warm: #a16207;
        }
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 18% 0%, rgba(15, 118, 110, 0.10), transparent 30rem),
                radial-gradient(circle at 88% 12%, rgba(161, 98, 7, 0.08), transparent 26rem),
                linear-gradient(180deg, #fbfaf7 0%, #f7f8f6 48%, #ffffff 100%);
        }
        [data-testid="stMainBlockContainer"] {
            padding-top: 2.5rem;
            max-width: 980px;
        }
        [data-testid="stBaseButton-primary"] button {
            border-radius: 999px;
            font-weight: 700;
            background: #172033;
            border: 1px solid #172033;
        }
        [data-testid="stBaseButton-secondary"] button,
        [data-testid="stFormSubmitButton"] button {
            border-radius: 999px;
            font-weight: 650;
        }
        [data-testid="stTextArea"] textarea,
        [data-testid="stTextInput"] input {
            border-radius: 14px;
            border-color: rgba(23, 32, 51, 0.16);
            background: rgba(255, 255, 255, 0.92);
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 22px;
            border-color: var(--brand-line);
            box-shadow: 0 18px 48px rgba(23, 32, 51, 0.06);
            background: var(--brand-surface);
        }
        h1, h2, h3 {
            letter-spacing: -0.035em;
            color: var(--brand-ink);
        }
        p, li, label, [data-testid="stCaptionContainer"] {
            color: var(--brand-muted);
        }
        .product-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.36rem 0.72rem;
            border: 1px solid rgba(15, 118, 110, 0.18);
            border-radius: 999px;
            color: #0f766e;
            background: rgba(240, 253, 250, 0.82);
            font-size: 0.86rem;
            font-weight: 700;
            margin-bottom: 0.85rem;
        }
        .hero-title {
            font-size: clamp(2.35rem, 5.6vw, 4.8rem);
            line-height: 0.98;
            letter-spacing: -0.07em;
            font-weight: 860;
            color: #121826;
            margin: 0 0 1rem 0;
        }
        .hero-copy {
            color: #475569;
            font-size: 1.12rem;
            line-height: 1.75;
            max-width: 44rem;
            margin-bottom: 1.25rem;
        }
        .trust-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            margin: 1rem 0 1.3rem 0;
        }
        .trust-pill {
            border: 1px solid rgba(23, 32, 51, 0.10);
            border-radius: 999px;
            padding: 0.42rem 0.72rem;
            background: rgba(255,255,255,0.76);
            color: #334155;
            font-size: 0.88rem;
            font-weight: 650;
        }
        .route-meta {
            color: #64748b;
            font-size: 0.9rem;
            margin-top: -0.25rem;
        }
        .metric-label {
            color: #64748b;
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .metric-value {
            color: #172033;
            font-size: 1.2rem;
            font-weight: 820;
            margin-top: 0.25rem;
        }
        .section-note {
            border-left: 3px solid #0f766e;
            padding: 0.72rem 0.9rem;
            background: rgba(240, 253, 250, 0.64);
            border-radius: 0 14px 14px 0;
            color: #334155;
        }
        .conversion-strip {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 1.15rem 0 1.25rem 0;
        }
        .conversion-item {
            border: 1px solid rgba(23, 32, 51, 0.10);
            border-radius: 18px;
            padding: 0.9rem;
            background: rgba(255, 255, 255, 0.70);
        }
        .conversion-item b {
            color: #172033;
        }
        .conversion-item span {
            display: block;
            color: #64748b;
            font-size: 0.9rem;
            line-height: 1.55;
            margin-top: 0.25rem;
        }
        .cta-note {
            color: #475569;
            font-size: 0.95rem;
            line-height: 1.65;
            margin: 0.5rem 0 0.9rem 0;
        }
        @media (max-width: 760px) {
            .conversion-strip {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """
    )


def get_setting(name: str, default: str = "") -> str:
    local = os.getenv(name)
    if local:
        return local
    try:
        value = st.secrets.get(name, default)
    except Exception:
        return default
    return str(value) if value else default


def get_analyzer() -> CareerAnalyzer:
    return CareerAnalyzer(
        ModelSettings(
            api_key=get_setting("DASHSCOPE_API_KEY"),
            workspace_id=get_setting("DASHSCOPE_WORKSPACE_ID"),
            model=get_setting("DASHSCOPE_MODEL", "qwen3.7-plus"),
            offline=get_setting("AI_RESUME_OFFLINE") == "1",
        )
    )


def render_metric_card(label: str, value: str, note: str = "") -> None:
    with st.container(border=True):
        safe_label = escape(label)
        safe_value = escape(value)
        safe_note = escape(note)
        st.html(
            f"""
            <div class="metric-label">{safe_label}</div>
            <div class="metric-value">{safe_value}</div>
            <div class="route-meta">{safe_note}</div>
            """
        )


def render_page_intro(title: str, subtitle: str, kicker: str = "") -> None:
    if kicker:
        st.html(f'<div class="product-kicker">{kicker}</div>')
    st.title(title)
    st.markdown(subtitle)


def initialize_state() -> None:
    defaults = {
        "view": "landing",
        "journey": None,
        "target_stage": "input",
        "target_diagnosis": None,
        "target_questions": [],
        "target_result": None,
        "direction_result": None,
        "base_result": None,
        "target_resume_input": "",
        "target_position": "",
        "target_jd": "",
        "target_answers": [],
        "notice": "",
        "error": "",
        "hide_city_advice": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def clear_outputs() -> None:
    for key, value in {
        "target_stage": "input",
        "target_diagnosis": None,
        "target_questions": [],
        "target_result": None,
        "direction_result": None,
        "base_result": None,
        "target_answers": [],
        "notice": "",
        "error": "",
        "hide_city_advice": False,
    }.items():
        st.session_state[key] = value


def fill_target_sample() -> None:
    st.session_state.target_position = "新媒体运营助理"
    st.session_state.target_jd = (
        "负责微信公众号、小红书等平台的内容选题、文案撰写、排版发布和基础数据复盘；"
        "参与活动执行、用户沟通和素材整理，能够使用 Excel 或内容后台跟踪阅读量、互动率和转化表现；"
        "要求具备内容策划、文字表达、跨部门协作、执行力和基础数据分析能力。"
    )
    st.session_state.target_resume_input = (
        "校园公众号运营：参与选题策划、图文排版和发布，累计完成 8 篇内容；"
        "使用 Excel 记录阅读量、点赞、收藏等互动数据，协助复盘内容表现。\n\n"
        "课程项目：完成用户调研报告和竞品分析，负责资料收集、访谈纪要整理、结论汇总和课堂展示。"
    )


def fill_base_sample() -> None:
    st.session_state.base_education = "新闻传播专业，本科，2025 届。相关课程：新媒体运营、用户研究、数据分析基础。"
    st.session_state.base_experience = (
        "校园公众号运营：参与选题策划、图文排版和发布，累计完成 8 篇内容；"
        "使用 Excel 记录阅读量、点赞、收藏等互动数据，协助复盘内容表现。"
    )
    st.session_state.base_projects = (
        "课程项目：完成用户调研报告和竞品分析，负责资料收集、访谈纪要整理、结论汇总和课堂展示。"
    )
    st.session_state.base_skills = "Excel、公众号后台、基础文案写作、资料整理、用户访谈记录。"
    st.session_state.base_transferable = "内容整理、数据记录、沟通协作、执行落地。"


def fill_direction_sample() -> None:
    st.session_state.direction_experience = (
        "新闻传播专业。做过校园公众号运营，参与选题、排版、发布和数据记录；"
        "做过用户调研课程项目，负责资料收集、访谈纪要和竞品分析。"
    )


def enter_journey(journey: str) -> None:
    clear_outputs()
    st.session_state.view = "workspace"
    st.session_state.journey = journey


def go_home() -> None:
    st.session_state.view = "landing"
    st.session_state.error = ""


def start_over() -> None:
    journey = st.session_state.journey
    clear_outputs()
    if journey != "target":
        st.session_state.target_resume_input = ""


def continue_base_to_target() -> None:
    base = st.session_state.get("base_result") or {}
    st.session_state.target_resume_input = base.get("plain_text", "")
    st.session_state.view = "workspace"
    st.session_state.journey = "target"
    st.session_state.target_stage = "input"
    st.session_state.error = ""


def continue_base_to_direction() -> None:
    base = st.session_state.get("base_result") or {}
    st.session_state.direction_experience = base.get("plain_text", "")
    st.session_state.view = "workspace"
    st.session_state.journey = "direction"
    st.session_state.direction_result = None
    st.session_state.error = ""


def plain_lines(values: list[str]) -> str:
    cleaned = [clean_text(value) for value in values if clean_text(value)]
    return "\n".join(cleaned).strip()


def section_content(result: dict, title: str) -> str:
    for section in result.get("sections", []):
        if section.get("title") == title:
            return clean_text(section.get("content"))
    return ""


def build_target_resume_sections(
    result: dict, position_name: str = ""
) -> list[tuple[str, str]]:
    bullets = result.get("resume_bullets", [])
    strengths = result.get("strengths", [])
    unknowns = result.get("unknowns", [])
    return [
        ("姓名 / 联系方式", "姓名：请补充\n手机：请补充\n邮箱：请补充\n城市：请补充"),
        ("求职目标", position_name or "请补充目标岗位"),
        (
            "教育经历",
            "学校 / 专业 / 学历：请补充\n时间：请补充\n相关课程、证书或毕业设计：请补充",
        ),
        (
            "工作经历 / 项目经历",
            plain_lines([item.get("text", "") for item in bullets])
            or "请补充真实经历、项目、职责和可验证结果。",
        ),
        (
            "技能",
            plain_lines(strengths[:4]) or "请补充真实掌握的工具、语言、平台或证书。",
        ),
        (
            "投递前待补充",
            plain_lines(unknowns[:4])
            or "投递前请核对联系方式、教育经历、项目时间和数据是否真实。",
        ),
    ]


def build_base_resume_sections(result: dict) -> list[tuple[str, str]]:
    education = section_content(result, "教育背景") or "学校 / 专业 / 学历：请补充\n时间：请补充"
    experience = plain_lines(
        [
            section_content(result, "实习、兼职或实践经历"),
            section_content(result, "课程、个人或作品项目"),
        ]
    )
    skills = plain_lines(
        [
            section_content(result, "技能、工具与证书"),
            section_content(result, "可迁移技能"),
        ]
    )
    return [
        ("姓名 / 联系方式", "姓名：请补充\n手机：请补充\n邮箱：请补充\n城市：请补充"),
        ("教育经历", education),
        (
            "工作经历 / 项目经历",
            experience or "请补充真实实践经历、课程项目、个人项目或作品。",
        ),
        ("技能", skills or "请补充真实掌握的工具、语言、平台或证书。"),
        (
            "润色提醒",
            f"责任程度先按“{result.get('responsibility', '参与')}”记录，不夸大主导权。\n"
            "每段经历后续最好补充：任务、动作、工具、交付物、可验证结果。\n"
            "投递前再按具体岗位删除无关内容，保留最能证明匹配度的 3 到 5 条。",
        ),
    ]


def render_resume_sections(
    sections: list[tuple[str, str]], key_prefix: str, intro: str
) -> None:
    st.caption(intro)
    for index, (title, body) in enumerate(sections):
        with st.container(border=True):
            st.markdown(f"#### {title}")
            st.text_area(
                f"复制：{title}",
                value=body,
                height=max(90, min(220, 42 + body.count("\n") * 28)),
                key=f"{key_prefix}_{index}",
                label_visibility="collapsed",
            )


def render_target_snapshot(result: dict) -> None:
    risks = result.get("risks", [])[:3]
    strengths = result.get("strengths", [])[:3]
    unknowns = result.get("unknowns", [])[:3]
    confidence = clean_text(result.get("confidence", "低")) or "低"
    hard_requirements = clean_text(result.get("hard_requirements", "仍需核对"))
    next_step = unknowns[0] if unknowns else "复制下方简历板块，投递前再核对联系方式、时间和数据。"

    st.subheader("投递判断")
    st.html('<div class="section-note">先看结论，再复制简历正文。分析细节收在下方，避免干扰使用。</div>')
    col1, col2, col3 = st.columns(3)
    with col1:
        render_metric_card("匹配可信度", confidence, "基于 JD 与已填写经历")
    with col2:
        render_metric_card("硬性条件", hard_requirements, "有门槛先核对门槛")
    with col3:
        render_metric_card("下一步", "补齐关键事实", next_step)

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("#### 已有优势")
            if strengths:
                for item in strengths:
                    st.markdown(f"- {item}")
            else:
                st.caption("当前经历证据较少，建议先补充项目、职责、工具和交付结果。")
    with right:
        with st.container(border=True):
            st.markdown("#### 主要风险")
            if risks:
                for item in risks:
                    st.markdown(f"- {item}")
            else:
                st.caption("暂未发现明显风险；投递前仍需核对岗位硬性条件。")


def render_landing() -> None:
    st.html(
        """
        <div class="product-kicker">给正在投简历的人用，不是泛泛润色工具</div>
        <div class="hero-title">投递前，先知道<br/>这份简历该怎么改。</div>
        <div class="hero-copy">
        大多数简历不是经历太少，而是没有对准岗位：JD 里真正看重什么、你已有经历能证明什么、
        哪些地方会被筛掉。这个工具会基于真实岗位和真实经历，给你一份可直接复制到 Word 的修改结果。
        </div>
        <div class="trust-row">
            <div class="trust-pill">先判断匹配度</div>
            <div class="trust-pill">再改简历表达</div>
            <div class="trust-pill">不编造经历和数据</div>
            <div class="trust-pill">结果可直接复制</div>
        </div>
        <div class="conversion-strip">
            <div class="conversion-item"><b>你输入</b><span>目标岗位 JD + 真实经历，测试时也可以一键填样例。</span></div>
            <div class="conversion-item"><b>系统判断</b><span>岗位要求、已有优势、主要风险和需要补齐的事实。</span></div>
            <div class="conversion-item"><b>你拿到</b><span>按姓名、教育、经历、技能分好的简历文本。</span></div>
        </div>
        """
    )

    with st.container(border=True):
        st.badge("最推荐路径", icon=":material/bolt:", color="green")
        st.markdown("### 已经有岗位 JD？从这里开始")
        st.markdown(
            "把 **岗位 JD + 真实经历** 放进去。系统会先判断匹配情况，再输出按姓名、教育、经历、技能分好的简历文本。"
        )
        st.html(
            """
            <div class="cta-note">
            适合：已经看到一个岗位、准备投递、但不确定简历该删什么、补什么、怎么写得更像岗位需要的人。
            </div>
            """
        )
        a, b, c = st.columns(3)
        with a:
            render_metric_card("开始成本", "2 段文本", "JD 和经历即可")
        with b:
            render_metric_card("决策价值", "先看风险", "避免盲目投递")
        with c:
            render_metric_card("最终结果", "可复制文本", "直接粘贴到 Word")
        st.button(
            "开始岗位定制",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            on_click=enter_journey,
            args=("target",),
            key="landing_target",
        )

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### 暂时没有明确 JD")
            st.caption("先用已有经历缩小方向，找到值得看的岗位类型。")
            st.button(
                "探索岗位方向",
                icon=":material/explore:",
                width="stretch",
                on_click=enter_journey,
                args=("direction",),
                key="landing_direction",
            )
    with col2:
        with st.container(border=True):
            st.markdown("### 简历还没整理好")
            st.caption("先把课程、项目、社团、兼职和技能整理成基础简历骨架。")
            st.button(
                "整理基础简历",
                icon=":material/article:",
                width="stretch",
                on_click=enter_journey,
                args=("base",),
                key="landing_base",
            )

    st.caption("更适合：应届生、转行、经历零散、投递前需要按具体 JD 修改简历的人。")


def render_diagnosis(diagnosis: dict) -> None:
    st.subheader("初步诊断")
    st.caption("先看已有信息能说明什么，再决定是否补充。此时还没有生成定制简历。")
    if diagnosis.get("notice"):
        st.warning(diagnosis["notice"], icon=":material/info:")
    with st.container(border=True):
        st.markdown("#### 招聘方真正看重的要求")
        for item in diagnosis.get("requirements", []):
            st.markdown(f"- {item}")
    with st.container(border=True):
        st.markdown("#### 你已经能证明的能力")
        for item in diagnosis.get("evidence", []):
            st.markdown(f"- {item}")
    with st.container(border=True):
        st.markdown("#### 最可能影响初筛的 3 个风险")
        for item in diagnosis.get("risks", [])[:3]:
            st.markdown(f"- {item}")
    with st.container(border=True):
        st.markdown("#### 暂时无法判断")
        for item in diagnosis.get("unknowns", []):
            st.markdown(f"- {item}")
    st.info(diagnosis.get("priority", ""), icon=":material/edit_note:")


def collect_target_answers(questions: list[dict]) -> list[dict[str, str]]:
    answers: list[dict[str, str]] = []
    for index, question in enumerate(questions):
        selected = st.session_state.get(f"target_q_{index}", "先按现有内容生成")
        detail = clean_text(st.session_state.get(f"target_q_detail_{index}", ""))
        answer = detail or selected
        answers.append(
            {
                "id": question.get("id", f"q{index + 1}"),
                "question": question.get("question", ""),
                "answer": answer,
                "status": (
                    "skipped" if selected in COMMON_SKIP_OPTIONS and not detail else "confirmed"
                ),
            }
        )
    return answers


def finalize_target(answers: list[dict[str, str]]) -> None:
    context = st.session_state.target_context
    analyzer = get_analyzer()
    with st.spinner("正在进行 STAR 定向重构和独立真实性复核……"):
        result = analyzer.finalize(
            context["position"],
            context["jd"],
            context["resume"],
            st.session_state.target_diagnosis,
            answers,
        )
    st.session_state.target_answers = answers
    st.session_state.target_result = result
    st.session_state.target_stage = "result"
    if result.get("offline"):
        st.session_state.notice = (
            "当前版本仅使用已确认信息，没有添加未经确认的数据。"
            "补充更多事实或恢复 AI 服务后，可以进一步增强。"
        )
    st.rerun()


def render_target_flow() -> None:
    render_page_intro(
        "岗位定制",
        "粘贴真实 JD 和经历后，系统会先做岗位诊断，再输出适合复制到 Word 的简历正文。",
        "推荐路径 · 适合已经有目标岗位",
    )

    if st.session_state.target_stage == "input":
        with st.container(border=True):
            st.markdown("#### 开始前准备")
            st.caption("建议上传前隐藏身份证号、完整住址等非必要敏感信息。测试时可直接使用样例。")
            st.button(
                "一键填入测试样例",
                icon=":material/content_paste:",
                width="stretch",
                on_click=fill_target_sample,
                key="fill_target_sample",
            )
        with st.form("target_input_form"):
            position = st.text_input(
                "目标岗位名称",
                key="target_position",
                placeholder="例如：新媒体运营专员",
                persist_state="session",
            )
            jd = st.text_area(
                "真实岗位 JD",
                key="target_jd",
                placeholder="粘贴岗位职责、任职要求和硬性条件。内容过短会影响判断。",
                height=220,
                persist_state="session",
            )
            upload = st.file_uploader(
                "上传简历（可选）",
                type=["pdf", "docx", "txt", "md"],
                key="target_resume_upload",
                help="支持 PDF、Word（.docx）、TXT 和 Markdown；也可以直接粘贴经历。",
            )
            resume_input = st.text_area(
                "或粘贴真实经历",
                key="target_resume_input",
                placeholder="教育、实习、兼职、课程项目、个人项目、社团、作品和会用的工具都可以。",
                height=260,
                persist_state="session",
            )
            submitted = st.form_submit_button(
                "查看初步诊断",
                icon=":material/analytics:",
                type="primary",
                width="stretch",
                key="submit_target_input",
            )

        if submitted:
            st.session_state.error = ""
            try:
                uploaded_text = ""
                if upload is not None:
                    uploaded_text = extract_resume_file(upload.name, upload.getvalue())
                resume = "\n\n".join(
                    item for item in (uploaded_text, clean_text(resume_input)) if item
                )
                if not clean_text(position):
                    raise UserFacingError("请填写目标岗位名称。")
                if len(clean_text(jd)) < 50:
                    raise UserFacingError(
                        "岗位 JD 过短，至少粘贴一段岗位职责或任职要求后再分析。"
                    )
                if not resume:
                    raise UserFacingError("简历正文为空，请上传可读取文件或粘贴真实经历。")
                analyzer = get_analyzer()
                with st.spinner("正在拆解 JD、提取真实证据并识别缺口……"):
                    diagnosis = analyzer.diagnose(position, jd, resume)
                    questions = analyzer.questions(diagnosis, resume)
                st.session_state.target_context = {
                    "position": clean_text(position),
                    "jd": clean_text(jd),
                    "resume": resume,
                }
                st.session_state.target_diagnosis = diagnosis
                st.session_state.target_questions = questions[:3]
                st.session_state.target_stage = "diagnosis"
                st.rerun()
            except UserFacingError as exc:
                st.session_state.error = str(exc)

    elif st.session_state.target_stage == "diagnosis":
        render_diagnosis(st.session_state.target_diagnosis)
        questions = st.session_state.target_questions[:3]
        st.subheader("补充最多 3 个关键事实")
        st.caption("每题都有常见选项，也可以不记得、没有数据、跳过或直接按现有内容生成。")
        with st.form("target_questions_form"):
            for index, question in enumerate(questions):
                with st.container(border=True):
                    st.markdown(f"**{index + 1}. {question['question']}**")
                    options = question.get("choices", []) + list(COMMON_SKIP_OPTIONS)
                    st.radio(
                        f"第 {index + 1} 题选项",
                        options,
                        index=len(question.get("choices", [])) + 3,
                        key=f"target_q_{index}",
                        label_visibility="collapsed",
                    )
                    st.text_input(
                        "补充一句真实细节（选填）",
                        key=f"target_q_detail_{index}",
                        placeholder="例如：参与 5 人团队；约一个月完成；根据反馈修改 2 至 3 轮。",
                    )
            answer_submit = st.form_submit_button(
                "根据回答生成定制结果",
                icon=":material/arrow_forward:",
                type="primary",
                width="stretch",
            )
        if answer_submit:
            finalize_target(collect_target_answers(questions))
        if st.button(
            "跳过全部，按现有内容生成保守版本",
            icon=":material/fast_forward:",
            width="stretch",
            key="skip_all_target_questions",
        ):
            answers = [
                {
                    "id": question.get("id", ""),
                    "question": question.get("question", ""),
                    "answer": "先按现有内容生成",
                    "status": "skipped",
                }
                for question in questions
            ]
            finalize_target(answers)
        if st.button(
            "返回修改岗位或经历",
            icon=":material/arrow_back:",
            width="stretch",
            key="back_to_target_input",
        ):
            st.session_state.target_stage = "input"
            st.rerun()
    else:
        render_target_result()

    if st.session_state.error:
        st.error(st.session_state.error, icon=":material/error:")


def render_target_result() -> None:
    result = st.session_state.target_result or {}
    context = st.session_state.get("target_context") or {}
    position_name = context.get("position", "")
    st.title("岗位定向结果")
    if st.session_state.notice:
        st.warning(st.session_state.notice, icon=":material/verified_user:")

    render_target_snapshot(result)

    resume_sections = build_target_resume_sections(result, position_name)
    st.subheader("可复制简历结果")
    with st.container(border=True):
        render_resume_sections(
            resume_sections,
            "target_resume_section",
            "按板块选中复制到 Word。每个文本框只放普通文本，不再导出文件。",
        )

    with st.expander("查看分析依据、风险和面试追问", icon=":material/analytics:"):
        st.subheader("1. 岗位匹配结论")
        with st.container(border=True):
            st.markdown(result.get("match_conclusion", "当前信息不足，暂时无法形成可靠结论。"))
            st.markdown(f"**硬性条件：** {result.get('hard_requirements', '仍需核对')}")
            st.markdown(f"**结论可信度：** {result.get('confidence', '低')}")

        st.subheader("2. 招聘方真正看重什么")
        for item in result.get("requirements", []):
            with st.container(border=True):
                st.markdown(item)

        st.subheader("3. 最可能影响初筛的 3 个风险")
        for item in result.get("risks", [])[:3]:
            st.warning(item, icon=":material/warning:")

        st.subheader("4. 你已有的真实优势")
        for item in result.get("strengths", []):
            st.success(item, icon=":material/check_circle:")

        st.subheader("5. 修改前后对照")
        before_after = result.get("before_after", [])
        if before_after:
            for item in before_after:
                with st.container(border=True):
                    st.caption(f"原文：{item.get('before', '未提供')}")
                    st.markdown(f"**改写：{item.get('after', '')}**")
                    st.caption(f"依据：{item.get('basis', '已确认事实')}")
        else:
            st.caption("保守版本没有强行改写原文；补充真实责任和交付后可生成更清晰的对照。")

        st.subheader("6. 逐条修改建议")
        bullets = result.get("resume_bullets", [])
        for index, item in enumerate(bullets):
            with st.container(border=True):
                st.markdown(f"**{item.get('text', '')}**")
                st.caption(f"事实状态：{item.get('fact_status', '已确认事实')}")
                with st.popover("纠正这一条", icon=":material/edit:"):
                    correction = st.selectbox(
                        "选择纠正方式",
                        [
                            "这不是我负责的",
                            "数据不准确",
                            "表达太夸张",
                            "表达太笼统",
                            "不像我的说话方式",
                            "保留原文",
                            "重新改写这一条",
                        ],
                        key=f"correction_type_{index}",
                    )
                    detail = st.text_input(
                        "补充说明（选填）",
                        key=f"correction_detail_{index}",
                        placeholder="只写需要更正的真实情况。",
                    )
                    if st.button(
                        "只更新这一条",
                        key=f"apply_correction_{index}",
                        type="primary",
                        width="stretch",
                    ):
                        facts = st.session_state.target_context["resume"] + "\n" + "\n".join(
                            answer.get("answer", "")
                            for answer in st.session_state.target_answers
                        )
                        feedback = "；".join(part for part in (correction, detail) if part)
                        revised = get_analyzer().revise(facts, item.get("text", ""), feedback)
                        st.session_state.target_result["resume_bullets"][index]["text"] = revised[
                            "replacement"
                        ]
                        st.session_state.target_result["resume_bullets"][index][
                            "fact_status"
                        ] = revised["status"]
                        st.session_state.notice = revised["basis"]
                        st.rerun()

        review = result.get("review", {})
        with st.container(border=True):
            st.markdown("#### 独立真实性复核")
            st.badge(
                review.get("status", "已复核"),
                icon=":material/verified:",
                color="green",
            )
            for note in review.get("notes", []):
                st.markdown(f"- {note}")
            rejected = review.get("rejected_claims", [])
            if rejected:
                st.caption(f"已拦截 {len(rejected)} 条缺少事实支撑的表述。")

        st.subheader("7. 仍需确认的信息")
        for item in result.get("unknowns", []):
            st.info(item, icon=":material/help:")

        st.subheader("8. 面试官可能追问")
        for index, item in enumerate(result.get("interview_questions", []), start=1):
            with st.container(border=True):
                st.markdown(f"**{index}. {item}**")


def render_base_flow() -> None:
    render_page_intro(
        "整理基础简历",
        "把课程、项目、实习、兼职、社团和技能整理成一份真实可用的简历骨架。",
        "基础路径 · 适合经历零散时先整理",
    )
    if not st.session_state.base_result:
        with st.container(border=True):
            st.markdown("#### 填写原则")
            st.caption("先保留真实标签：课程项目就写课程项目，参与就写参与。后续再按目标岗位删减。")
            st.button(
                "一键填入测试样例",
                icon=":material/content_paste:",
                width="stretch",
                on_click=fill_base_sample,
                key="fill_base_sample",
            )
        with st.form("base_resume_form"):
            education = st.text_area(
                "教育背景",
                key="base_education",
                placeholder="学校、专业、时间、相关课程或毕业设计。",
                height=110,
                persist_state="session",
            )
            experience = st.text_area(
                "实习、兼职、社团或实践经历",
                key="base_experience",
                placeholder="做过什么、你负责哪部分、最终完成了什么；没有可以留空。",
                height=140,
                persist_state="session",
            )
            projects = st.text_area(
                "课程、个人、练习或作品项目",
                key="base_projects",
                placeholder="请保留真实标签，不要把课程或个人项目写成企业项目。",
                height=140,
                persist_state="session",
            )
            skills = st.text_area(
                "技能、工具与证书",
                key="base_skills",
                placeholder="只写真实会用的工具、语言和证书。",
                height=110,
                persist_state="session",
            )
            transferable = st.text_area(
                "可迁移技能（选填）",
                key="base_transferable",
                placeholder="例如：资料整理、沟通、测试、内容制作、活动协作。",
                height=100,
                persist_state="session",
            )
            responsibility = st.segmented_control(
                "这段主要经历中的责任程度",
                ["独立完成", "主导", "参与", "协助"],
                default="参与",
                key="base_responsibility",
            )
            submitted = st.form_submit_button(
                "生成真实基础简历",
                icon=":material/article:",
                type="primary",
                width="stretch",
                key="submit_base_resume",
            )
        if submitted:
            try:
                st.session_state.base_result = build_base_resume(
                    {
                        "education": education,
                        "experience": experience,
                        "projects": projects,
                        "skills": skills,
                        "transferable": transferable,
                        "responsibility": responsibility,
                    }
                )
                st.rerun()
            except UserFacingError as exc:
                st.session_state.error = str(exc)
    else:
        result = st.session_state.base_result
        st.success(result["notice"], icon=":material/verified:")
        st.subheader("可复制基础简历")
        render_resume_sections(
            build_base_resume_sections(result),
            "base_resume_section",
            "这是基础简历模板。按板块选中复制到 Word，再补齐个人信息和细节。",
        )
        st.subheader("下一步")
        st.button(
            "我有目标岗位，继续定制",
            icon=":material/target:",
            type="primary",
            width="stretch",
            on_click=continue_base_to_target,
            key="base_to_target",
        )
        st.button(
            "我还没确定方向，帮我推荐",
            icon=":material/explore:",
            width="stretch",
            on_click=continue_base_to_direction,
            key="base_to_direction",
        )
    if st.session_state.error:
        st.error(st.session_state.error, icon=":material/error:")


def render_direction_flow() -> None:
    render_page_intro(
        "探索岗位方向",
        "当你还不确定投什么岗位时，先用已有经历缩小方向，再决定是否要针对具体 JD 定制简历。",
        "探索路径 · 适合转向或方向不清",
    )
    if not st.session_state.direction_result:
        with st.container(border=True):
            st.markdown("#### 先做方向筛选")
            st.caption("这里不会替你决定职业，只会根据已填写证据给出低成本验证路径。")
            st.button(
                "一键填入测试样例",
                icon=":material/content_paste:",
                width="stretch",
                on_click=fill_direction_sample,
                key="fill_direction_sample",
            )
        with st.form("direction_form"):
            experience = st.text_area(
                "先写下真实经历或基础简历",
                key="direction_experience",
                placeholder="课程、项目、实习、兼职、社团、作品、工具和长期负责的事情都可以。",
                height=220,
                persist_state="session",
            )
            continue_old = st.segmented_control(
                "1. 过去做过的方向还想继续吗？",
                ["想继续", "不想继续", "不确定", "跳过"],
                default="不确定",
                key="direction_continue_old",
            )
            priority = st.segmented_control(
                "2. 岗位和城市，哪个更优先？",
                ["岗位优先", "城市优先", "暂时没有偏好", "跳过"],
                default="暂时没有偏好",
                key="direction_priority",
            )
            excluded_choice = st.multiselect(
                "3. 明确不接受哪些工作内容？",
                ["纯销售", "高频出差", "夜班", "大量电话沟通", "长期加班", "暂时没有偏好", "跳过"],
                default=["暂时没有偏好"],
                key="direction_excluded_choice",
            )
            excluded_detail = st.text_input(
                "其他不接受内容（选填）",
                key="direction_excluded_detail",
                placeholder="例如：不想继续游戏开发；不考虑纯客服。",
            )
            urgency = st.segmented_control(
                "是否急需尽快就业？（选填）",
                ["是", "否", "不确定", "跳过"],
                default="不确定",
                key="direction_urgency",
            )
            submitted = st.form_submit_button(
                "生成方向建议",
                icon=":material/explore:",
                type="primary",
                width="stretch",
                key="submit_direction_form",
            )
        if submitted:
            excluded = "；".join(
                item
                for item in excluded_choice + [clean_text(excluded_detail)]
                if item and item not in {"暂时没有偏好", "跳过"}
            )
            profile = {
                "experience": clean_text(experience),
                "continue_old": continue_old or "不确定",
                "priority": priority or "暂时没有偏好",
                "excluded": excluded or "暂时没有偏好",
                "urgency": urgency or "不确定",
            }
            with st.spinner("正在拆解可迁移能力并梳理三类方向……"):
                st.session_state.direction_result = get_analyzer().direction(profile)
            st.session_state.direction_profile = profile
            st.rerun()
    else:
        result = st.session_state.direction_result
        if result.get("offline"):
            st.warning(result.get("notice", ""), icon=":material/info:")
        else:
            st.caption(result.get("notice", ""))
        roles = result.get("roles", [])[:3]
        st.subheader("方向判断")
        c1, c2, c3 = st.columns(3)
        with c1:
            render_metric_card("直接可投", roles[0].get("title", "待验证") if roles else "待验证", "先找真实 JD 核对")
        with c2:
            render_metric_card("相邻方向", roles[1].get("title", "待验证") if len(roles) > 1 else "待验证", "能力迁移成本较低")
        with c3:
            render_metric_card("探索方向", roles[2].get("title", "待验证") if len(roles) > 2 else "待验证", "先做微型项目验证")
        st.subheader("推荐路径")
        for role_index, role in enumerate(roles):
            with st.container(border=True):
                st.badge(role.get("category", "探索方向"), color="blue")
                st.subheader(role.get("title", "待验证方向"))
                st.markdown(f"**日常实际做什么：** {role.get('daily_work', '')}")
                st.markdown(f"**为什么推荐：** {role.get('why', '')}")
                st.markdown(f"**真实依据：** {role.get('evidence', '')}")
                st.markdown(f"**已经具备：** {role.get('existing', '')}")
                st.markdown(f"**主要缺口：** {role.get('gap', '')}")
                st.markdown(f"**可能不符合偏好：** {role.get('preference_risk', '')}")
                st.markdown(f"**现在是否建议投递：** {role.get('apply_now', '')}")
                st.markdown(f"**下一步：** {role.get('next_action', '')}")
                if st.button(
                    "我不想继续这个方向",
                    icon=":material/close:",
                    key=f"remove_direction_{role_index}",
                    width="stretch",
                ):
                    st.session_state.direction_result["roles"].pop(role_index)
                    st.rerun()

        if not st.session_state.hide_city_advice:
            city = result.get("cities", {})
            with st.container(border=True):
                st.subheader("城市第一梯队")
                st.markdown(f"**{city.get('tier', '')}**")
                st.markdown(city.get("summary", ""))
                roles = "、".join(city.get("search_roles", []))
                if roles:
                    st.markdown(f"**可以搜索：** {roles}")
                st.caption(city.get("notice", ""))
                if st.button(
                    "不考虑这些城市",
                    icon=":material/location_off:",
                    width="stretch",
                    key="hide_city",
                ):
                    st.session_state.hide_city_advice = True
                    st.rerun()

        micro = result.get("micro_project", {})
        with st.container(border=True):
            st.subheader("经历证据较少时：先做一个真实微型项目")
            st.markdown(f"**周期：** {micro.get('duration', '3 至 7 天')}")
            st.markdown(f"**任务：** {micro.get('task', '')}")
            st.markdown(f"**最终交付：** {micro.get('deliverable', '')}")
            st.markdown(f"**完成后如何写：** {micro.get('resume_usage', '')}")
    if st.session_state.error:
        st.error(st.session_state.error, icon=":material/error:")


apply_custom_styles()
initialize_state()

if st.session_state.view == "landing":
    render_landing()
    st.stop()

with st.container(horizontal=True, horizontal_alignment="distribute"):
    st.button(
        "返回首页",
        icon=":material/arrow_back:",
        width="content",
        on_click=go_home,
        key="global_back_home",
    )
    if (
        st.session_state.target_result
        or st.session_state.direction_result
        or st.session_state.base_result
    ):
        st.button(
            "开始新的分析",
            icon=":material/restart_alt:",
            width="content",
            on_click=start_over,
            key="global_start_over",
        )

journey = st.session_state.journey
if journey == "target":
    render_target_flow()
elif journey == "base":
    render_base_flow()
else:
    render_direction_flow()
