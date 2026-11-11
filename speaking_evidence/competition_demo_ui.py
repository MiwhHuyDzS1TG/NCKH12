"""Polished Streamlit competition experience for the frozen scorer."""
from __future__ import annotations

import base64
import hashlib
import html
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from speaking_evidence.competition_demo import (
    DEMO_IDS,
    DEMO_LABELS,
    StaleDemoCacheError,
    load_demo_cache,
    offline_readiness,
    resolve_demo_video,
    run_live_analysis,
)


COMPETITION_CSS = """
<style>
:root {
  --demo-bg: #f4f6fa;
  --demo-surface: #fbfcfe;
  --demo-card: #ffffff;
  --demo-text: #14213d;
  --demo-muted: #5f6f89;
  --demo-line: #dce3ee;
  --demo-accent: #2557c9;
  --demo-accent-soft: #eaf0ff;
  --demo-success: #25634f;
  --demo-shadow: 0 18px 50px rgba(39, 72, 132, 0.10);
  --demo-radius: 16px;
}
html, body, [class*="css"] {font-family: "Aptos", "Segoe UI Variable", "Segoe UI", sans-serif;}
[data-testid="stAppViewContainer"] {
  background: var(--demo-bg);
  color: var(--demo-text);
}
[data-testid="stHeader"], [data-testid="stToolbar"], section[data-testid="stSidebar"], footer {display:none !important;}
.block-container {max-width: 1380px; padding: 1.1rem 2.4rem 4rem;}
h1, h2, h3 {color: var(--demo-text); letter-spacing: -0.035em;}
p {color: var(--demo-muted);}
.demo-nav {
  min-height: 58px; display:flex; align-items:center; justify-content:space-between;
  border-bottom: 1px solid var(--demo-line); margin-bottom: 1.25rem;
}
.demo-brand {font-size: 1.04rem; font-weight: 760; color: var(--demo-text); letter-spacing: -0.02em;}
.demo-brand-mark {color: var(--demo-accent);}
.demo-nav-path {font-size: .82rem; color: var(--demo-muted); word-spacing: .45rem;}
.demo-nav-path strong {color: var(--demo-text);}
.stButton > button {
  min-height: 2.8rem; border-radius: 12px; border: 1px solid var(--demo-line);
  font-weight: 700; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.stButton > button:hover {transform: translateY(-1px); border-color: var(--demo-accent); box-shadow: 0 9px 22px rgba(37,87,201,.12);}
.stButton > button:active {transform: translateY(1px);}
.stButton > button[kind="primary"], [data-testid="stBaseButton-primary"] {
  background: var(--demo-accent) !important; color: #ffffff !important;
  border-color: var(--demo-accent) !important;
}
.stButton > button[kind="primary"] p, [data-testid="stBaseButton-primary"] p {color:#ffffff !important;}
.st-key-competition_hero {
  background: var(--demo-card); border: 1px solid var(--demo-line); border-radius: var(--demo-radius);
  padding: 2.4rem; box-shadow: var(--demo-shadow); min-height: 470px;
}
.st-key-competition_hero iframe {display:block; width:100%; border:0; border-radius:var(--demo-radius);}
.demo-kicker {font-size:.76rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; color:var(--demo-accent); margin-bottom:.7rem;}
.demo-hero-title {font-size:clamp(2.6rem,4.5vw,4.9rem); line-height:.98; font-weight:780; letter-spacing:-.065em; color:var(--demo-text); max-width:720px; margin:0 0 1rem;}
.demo-hero-copy {font-size:1.08rem; line-height:1.55; color:var(--demo-muted); max-width:520px; margin-bottom:1.1rem;}
.demo-trust-row {display:grid; grid-template-columns:1.2fr .9fr .9fr; gap:1rem; margin:1.25rem 0 2.2rem;}
.demo-proof {padding:1rem 1.1rem; border-left:3px solid var(--demo-accent); background:rgba(255,255,255,.68); border-radius:0 12px 12px 0;}
.demo-proof b {display:block; color:var(--demo-text); font-size:.96rem;}
.demo-proof span {font-size:.8rem; color:var(--demo-muted);}
.demo-section-head {font-size:2rem; font-weight:760; color:var(--demo-text); margin:.2rem 0 .35rem; letter-spacing:-.04em;}
.demo-section-copy {max-width:660px; margin:0 0 1.2rem; font-size:.96rem;}
div[role="radiogroup"] {gap:.75rem;}
div[role="radiogroup"] label {
  background:var(--demo-card); border:1px solid var(--demo-line); border-radius:var(--demo-radius);
  padding:.9rem 1rem; min-height:64px; box-shadow:0 8px 24px rgba(39,72,132,.05);
  transition:border-color .18s ease, transform .18s ease;
}
div[role="radiogroup"] label:hover {border-color:var(--demo-accent); transform:translateY(-1px);}
[data-testid="stFileUploader"] {background:var(--demo-card); border-radius:var(--demo-radius); padding:1rem; border:1px solid var(--demo-line);}
[data-testid="stFileUploaderDropzone"] {border:1.5px dashed #9fb0ca; border-radius:12px; background:#f8faff;}
.demo-process {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin:.5rem 0 1.25rem;}
.demo-process-item {background:var(--demo-card); border:1px solid var(--demo-line); border-radius:12px; padding:.8rem .85rem; color:var(--demo-text); font-size:.82rem; font-weight:650;}
.demo-process-item span {display:inline-grid; place-items:center; width:1.25rem; height:1.25rem; border-radius:50%; background:var(--demo-accent-soft); color:var(--demo-accent); margin-right:.4rem;}
.demo-result-head {display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; margin:.4rem 0 1.1rem;}
.demo-result-title {font-size:2.45rem; line-height:1.05; font-weight:780; letter-spacing:-.05em; color:var(--demo-text);}
.demo-status {display:inline-block; padding:.42rem .72rem; border-radius:999px; background:var(--demo-accent-soft); color:var(--demo-accent); font-size:.75rem; font-weight:800;}
.demo-score-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.85rem; margin:0 0 1.55rem;}
.demo-score-card {position:relative; overflow:hidden; min-height:190px; background:var(--demo-card); border:1px solid var(--demo-line); border-radius:var(--demo-radius); padding:1.15rem; box-shadow:0 12px 34px rgba(39,72,132,.07); transition:transform .18s ease, box-shadow .18s ease;}
.demo-score-card:hover {transform:translateY(-2px); box-shadow:0 18px 42px rgba(39,72,132,.11);}
.demo-score-card:before {content:""; position:absolute; inset:0 auto 0 0; width:4px; background:var(--demo-accent);}
.demo-score-name {font-size:.88rem; font-weight:760; color:var(--demo-text); margin-bottom:.78rem;}
.demo-score {font-size:2.4rem; line-height:1; letter-spacing:-.055em; font-weight:800; color:var(--demo-text);}
.demo-score small {font-size:.9rem; color:var(--demo-muted); font-weight:650; letter-spacing:0;}
.demo-score-sub {font-size:.78rem; line-height:1.4; color:var(--demo-muted); margin-top:.75rem;}
.demo-badge {display:inline-block; margin-top:.75rem; padding:.28rem .48rem; border-radius:999px; background:var(--demo-accent-soft); color:var(--demo-accent); font-size:.67rem; font-weight:800; letter-spacing:.02em;}
.demo-badge.usable {background:#e9f4ef; color:var(--demo-success);}
.demo-feedback-title {font-size:1.65rem; font-weight:760; color:var(--demo-text); margin:1.15rem 0 .7rem; letter-spacing:-.035em;}
.demo-feedback-grid {display:grid; grid-template-columns:1.14fr .93fr .93fr; gap:.85rem; margin-bottom:1.5rem;}
.demo-feedback-card {background:var(--demo-card); border:1px solid var(--demo-line); border-radius:var(--demo-radius); padding:1.15rem 1.2rem; min-height:150px;}
.demo-feedback-card.primary {background:linear-gradient(145deg,#eef3ff,#ffffff 72%); border-color:#cbd8f5;}
.demo-feedback-label {font-size:.76rem; font-weight:800; color:var(--demo-accent); margin-bottom:.55rem;}
.demo-feedback-text {font-size:.95rem; line-height:1.55; color:var(--demo-text);}
.demo-mini-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin:.65rem 0 1rem;}
.demo-mini {background:var(--demo-card); border:1px solid var(--demo-line); border-radius:12px; padding:.8rem;}
.demo-mini b {display:block; font-size:1.15rem; color:var(--demo-text);}
.demo-mini span {font-size:.73rem; color:var(--demo-muted);}
.demo-reading {background:var(--demo-card); border:1px solid var(--demo-line); border-radius:var(--demo-radius); padding:1.15rem; line-height:1.72; color:var(--demo-text);}
.demo-word-chip {display:inline-block; padding:.24rem .5rem; margin:.16rem .18rem .16rem 0; border-radius:999px; background:#fff4df; color:#765117; font-size:.78rem;}
.demo-failure {background:var(--demo-card); border:1px solid #efcfca; border-radius:var(--demo-radius); padding:2rem; box-shadow:var(--demo-shadow);}
.demo-failure h2 {margin:0 0 .5rem;}
.demo-footer {margin-top:2rem; padding-top:1rem; border-top:1px solid var(--demo-line); font-size:.76rem; color:var(--demo-muted);}
details {border-radius:var(--demo-radius) !important; border-color:var(--demo-line) !important; background:var(--demo-card) !important;}
@media (max-width: 980px) {
  .block-container {padding:1rem 1.2rem 3rem;}
  .demo-score-grid, .demo-process, .demo-mini-grid {grid-template-columns:repeat(2,minmax(0,1fr));}
  .demo-feedback-grid, .demo-trust-row {grid-template-columns:1fr;}
  .st-key-competition_hero {padding:1.35rem; min-height:auto;}
  .st-key-competition_hero iframe {min-height:270px;}
}
@media (max-width: 620px) {
  .block-container {padding:.8rem .85rem 2.5rem;}
  .demo-nav-path {display:none;}
  .demo-hero-title {font-size:2.55rem;}
  .demo-score-grid, .demo-process, .demo-mini-grid {grid-template-columns:1fr;}
  .demo-result-head {display:block;}
  .demo-status {margin-top:.65rem;}
}
@media (prefers-reduced-motion: reduce) {
  *, *:before, *:after {scroll-behavior:auto !important; transition:none !important; animation:none !important;}
}
</style>
"""


def _nav(current: str) -> None:
    st.markdown(
        f"<div class='demo-nav'><div class='demo-brand'><span class='demo-brand-mark'>NCKH12</span> Speaking Coach</div>"
        f"<div class='demo-nav-path'>{'<strong>' if current == 'Home' else ''}Home{'</strong>' if current == 'Home' else ''} / "
        f"{'<strong>' if current == 'Assessment' else ''}Assessment{'</strong>' if current == 'Assessment' else ''} / "
        f"{'<strong>' if current == 'Results' else ''}Results{'</strong>' if current == 'Results' else ''}</div></div>",
        unsafe_allow_html=True,
    )


def _go(view: str) -> None:
    st.session_state["competition_view"] = view
    st.rerun()


def _landing(root: Path) -> None:
    _nav("Home")
    with st.container(key="competition_hero"):
        left, right = st.columns([1.05, .95], gap="large", vertical_alignment="center")
        with left:
            st.markdown("<div class='demo-kicker'>Evidence-based speaking practice</div>", unsafe_allow_html=True)
            st.markdown("<h1 class='demo-hero-title'>Turn a Duet into useful speaking feedback.</h1>", unsafe_allow_html=True)
            st.markdown("<p class='demo-hero-copy'>Upload a completed TikTok Duet and receive clear, measured feedback on your controlled reading.</p>", unsafe_allow_html=True)
            if st.button("Assess Speaking", type="primary", width="stretch", key="competition_cta"):
                _go("assessment")
        with right:
            image_bytes = (root / "assets/competition-hero-v1.webp").read_bytes()
            encoded = base64.b64encode(image_bytes).decode("ascii")
            components.html(
                "<style>html,body{margin:0;background:transparent;overflow:hidden}"
                "img{display:block;width:100%;height:400px;object-fit:cover;border-radius:16px}</style>"
                f"<img src='data:image/webp;base64,{encoded}' "
                "alt='Abstract speech ribbon flowing through layered paper'>",
                height=404,
                scrolling=False,
            )
    st.markdown(
        "<div class='demo-trust-row'>"
        "<div class='demo-proof'><b>Real learner extraction</b><span>Completed Duet audio, isolated with Phase 1 timestamps</span></div>"
        "<div class='demo-proof'><b>Frozen scoring</b><span>No tuning after validation</span></div>"
        "<div class='demo-proof'><b>Runs offline</b><span>No cloud service required for demo results</span></div>"
        "</div>", unsafe_allow_html=True)
    st.markdown("<div class='demo-footer'>Development and preliminary assessment. Not CEFR, B2 or IELTS.</div>", unsafe_allow_html=True)


def _fast_demo(root: Path) -> None:
    labels = {pair_id: f"{DEMO_LABELS[pair_id]}  |  {pair_id.replace('T001-', '')}" for pair_id in DEMO_IDS}
    selected = st.radio(
        "Choose a demonstration",
        DEMO_IDS,
        format_func=lambda pair_id: labels[pair_id],
        horizontal=True,
        key="competition_demo_choice",
    )
    st.caption("Each choice loads genuine output from the frozen local pipeline.")
    if st.button("View genuine results", type="primary", width="stretch", key="competition_fast_run"):
        try:
            with st.status("Preparing the assessment", expanded=True) as status:
                result = load_demo_cache(root, selected, verify_media=True)
                for message in ("Video received", "Learner speech identified",
                                "Audio quality verified", "AI speaking analysis completed"):
                    st.write(message)
                    time.sleep(.08)
                status.update(label="Assessment ready", state="complete", expanded=False)
            st.session_state["competition_result"] = result
            st.session_state["competition_view"] = "results"
            st.rerun()
        except (OSError, ValueError, KeyError, StaleDemoCacheError) as exc:
            st.error("This demonstration could not be verified. The cached result was not shown.")
            st.caption("Please restart the demo or ask the presenter to verify local assets.")
            st.session_state["competition_internal_error"] = str(exc)


def _live_demo(root: Path) -> None:
    readiness = offline_readiness(root)
    upload = st.file_uploader(
        "Completed TikTok Duet video",
        type=["mp4", "mov", "mkv"],
        help="The file stays on this computer and is processed by local models.",
        key="competition_upload",
    )
    if not readiness["ready"]:
        st.warning("Live analysis is unavailable because a required local model asset is missing. Fast Demo remains available.")
        return
    if st.button("Run live analysis", type="primary", width="stretch",
                 disabled=upload is None, key="competition_live_run"):
        suffix = Path(upload.name).suffix.lower()
        payload = upload.getvalue()
        run_id = hashlib.sha256(payload).hexdigest()[:12]
        work_dir = root / "runs/competition_demo" / run_id
        source = work_dir / f"completed_duet{suffix}"
        work_dir.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        try:
            with st.status("Running local analysis", expanded=True) as status:
                placeholder = st.empty()

                def update(message: str) -> None:
                    placeholder.write(message)

                result = run_live_analysis(root, source, work_dir, update)
                status.update(label="Analysis finished", state="complete", expanded=False)
            st.session_state["competition_result"] = result
            st.session_state["competition_view"] = "results"
            st.rerun()
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            st.error("We could not complete a trustworthy assessment for this file.")
            st.caption("Please try another completed Duet. Technical details remain hidden during presentation.")
            st.session_state["competition_internal_error"] = str(exc)


def _assessment(root: Path) -> None:
    _nav("Assessment")
    top = st.columns([.2, .8])
    if top[0].button("Home", key="competition_home_from_assessment", width="stretch"):
        _go("home")
    st.markdown("<div class='demo-section-head'>Choose how to assess</div>", unsafe_allow_html=True)
    st.markdown("<p class='demo-section-copy'>Use a prepared demonstration for a fast presentation, or run the full local pipeline on a new completed Duet.</p>", unsafe_allow_html=True)
    fast, live = st.tabs(["Fast Demo", "Live Analysis"])
    with fast:
        _fast_demo(root)
    with live:
        _live_demo(root)


def _score_card(name: str, value: float | None, subtitle: str, status: str,
                percent: bool = False) -> str:
    preliminary = status == "PRELIMINARY"
    badge = "Preliminary" if preliminary else ("Measured" if status == "USABLE" else "Unavailable")
    badge_class = "" if preliminary else " usable"
    if not isinstance(value, (int, float)):
        display = "Unavailable"
        unit = ""
    elif percent:
        display = f"{value:.0%}"
        unit = ""
    else:
        display = f"{value:.1f}"
        unit = "<small>/ 5</small>"
    return (
        "<div class='demo-score-card'>"
        f"<div class='demo-score-name'>{html.escape(name)}</div>"
        f"<div class='demo-score'>{display} {unit}</div>"
        f"<div class='demo-score-sub'>{html.escape(subtitle)}</div>"
        f"<div class='demo-badge{badge_class}'>{badge}</div>"
        "</div>"
    )


def _feedback(result: dict) -> None:
    feedback = result["feedback"]
    cards = (
        ("What you did well", feedback["strength"]["text"], " primary"),
        ("Focus next", feedback["focus_next"]["text"], ""),
        ("Try this", feedback["try_this"]["text"], ""),
    )
    markup = "<div class='demo-feedback-title'>Your feedback</div><div class='demo-feedback-grid'>"
    for label, text, extra in cards:
        markup += (
            f"<div class='demo-feedback-card{extra}'><div class='demo-feedback-label'>{html.escape(label)}</div>"
            f"<div class='demo-feedback-text'>{html.escape(text)}</div></div>"
        )
    st.markdown(markup + "</div>", unsafe_allow_html=True)


def _metric_grid(metrics: list[tuple[str, str]]) -> None:
    markup = "<div class='demo-mini-grid'>"
    for value, label in metrics:
        markup += f"<div class='demo-mini'><b>{html.escape(value)}</b><span>{html.escape(label)}</span></div>"
    st.markdown(markup + "</div>", unsafe_allow_html=True)


def _evidence_explorer(result: dict, root: Path) -> None:
    evidence = result.get("evidence", {})
    complete = result.get("completeness", {})
    with st.expander("See why you received these scores", expanded=False):
        st.markdown("### Pronunciation")
        raw = evidence.get("raw_multipa") or {}
        prompts = evidence.get("word_review_prompts", [])
        _metric_grid([
            (f"{raw.get('accuracy'):.2f}" if isinstance(raw.get("accuracy"), (int, float)) else "Unavailable",
             "Raw MultiPA accuracy evidence"),
            (str(len(prompts)), "Word review prompts"),
        ])
        if prompts:
            st.markdown("Words with lower relative model evidence: " + " ".join(
                f"<span class='demo-word-chip'>{html.escape(row['word'])}</span>" for row in prompts),
                unsafe_allow_html=True)
            st.caption("These are review prompts, not confirmed pronunciation errors.")

        st.markdown("### Fluency")
        fluency = evidence.get("fluency", {})
        _metric_grid([
            (f"{fluency.get('speech_rate_wpm'):.0f}" if isinstance(fluency.get("speech_rate_wpm"), (int, float)) else "Unavailable", "Words per minute"),
            (str(fluency.get("pause_count", "Unavailable")), "Measured pauses"),
            (f"{fluency.get('longest_pause_sec'):.2f}s" if isinstance(fluency.get("longest_pause_sec"), (int, float)) else "Unavailable", "Longest pause"),
            (f"{fluency.get('mean_length_of_run_words'):.1f}" if isinstance(fluency.get("mean_length_of_run_words"), (int, float)) else "Unavailable", "Words per speech run"),
        ])

        st.markdown("### Prosody")
        _metric_grid([
            (f"{raw.get('prosody'):.2f}" if isinstance(raw.get("prosody"), (int, float)) else "Unavailable", "Raw MultiPA prosody evidence"),
            (f"{raw.get('total'):.2f}" if isinstance(raw.get("total"), (int, float)) else "Unavailable", "Model context score"),
        ])
        st.caption("Prosody is preliminary and should be read as formative evidence, not a proficiency label.")

        st.markdown("### Reading completeness")
        _metric_grid([
            (f"{complete.get('coverage', 0):.0%}", "Target coverage"),
            (str(complete.get("matched_word_count", 0)), "Matched target words"),
            (str(len(complete.get("possible_asr_uncertainty", []))), "Possible ASR uncertainty spans"),
        ])
        uncertain = complete.get("possible_asr_uncertainty", [])[:8]
        if uncertain:
            st.markdown("Possible ASR uncertainty: " + " ".join(
                f"<span class='demo-word-chip'>{html.escape(word)}</span>" for word in uncertain),
                unsafe_allow_html=True)
        st.caption("Possible ASR uncertainty is not the same as a confirmed learner omission.")

        st.markdown("### Target passage")
        st.markdown(f"<div class='demo-reading'>{html.escape(result.get('target_text', 'Unavailable'))}</div>", unsafe_allow_html=True)
        st.markdown("### Learner transcript")
        st.markdown(f"<div class='demo-reading'>{html.escape(result.get('transcript', 'Unavailable'))}</div>", unsafe_allow_html=True)

        if result.get("source_mode") == "FAST_DEMO_FROZEN_CACHE":
            try:
                video = resolve_demo_video(root, result["pair_id"], result["raw_duet_sha256"])
                st.markdown("### Completed Duet")
                st.video(str(video))
            except (OSError, ValueError):
                st.info("The source video is unavailable, but the verified machine evidence remains unchanged.")


def _judge_panels() -> None:
    with st.expander("How does the AI work?", expanded=False):
        _metric_grid([
            ("Separate", "Learner speech from the completed Duet"),
            ("Analyze", "Pronunciation and prosody with MultiPA"),
            ("Measure", "Fluency timing and reading coverage"),
            ("Validate", "Mappings against development teacher evidence"),
        ])
        st.markdown("**Model mapping**")
        st.write("Pronunciation: MultiPA | Fluency: NCKH12 timing evidence | Prosody: MultiPA | Completeness: faster-whisper plus target alignment")
    with st.expander("Research validation", expanded=False):
        _metric_grid([
            ("0.491 / 0.436", "Pronunciation MAE, development / mini-validation"),
            ("0.420 / 0.513", "Fluency MAE, development / mini-validation"),
            ("0.588 / 0.703", "Prosody MAE, development / mini-validation"),
        ])
        st.info("Mini-validation: N=3, descriptive evidence only.")
        st.caption("Pronunciation and Prosody are preliminary due to limited development data.")


def _failure(result: dict) -> None:
    _nav("Results")
    st.markdown(
        "<div class='demo-failure'><h2>We couldn't assess this recording reliably.</h2>"
        "<p>Learner speech or audio quality was not clear enough for a trustworthy assessment. Please try another recording.</p></div>",
        unsafe_allow_html=True)
    if st.button("Try another recording", type="primary", key="competition_retry"):
        _go("assessment")


def _results(root: Path, result: dict) -> None:
    if result.get("status") == "NOT_SCORABLE":
        _failure(result)
        return
    _nav("Results")
    actions = st.columns([.18, .18, .64])
    if actions[0].button("Home", key="competition_home_from_results", width="stretch"):
        _go("home")
    if actions[1].button("New assessment", key="competition_new_assessment", width="stretch"):
        _go("assessment")
    st.markdown(
        "<div class='demo-process'>"
        "<div class='demo-process-item'><span>✓</span>Video received</div>"
        "<div class='demo-process-item'><span>✓</span>Learner speech identified</div>"
        "<div class='demo-process-item'><span>✓</span>Audio quality verified</div>"
        "<div class='demo-process-item'><span>✓</span>AI analysis completed</div>"
        "</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='demo-result-head'><div><div class='demo-result-title'>{html.escape(result['display_name'])}</div>"
        f"<p>Assessment completed</p></div><div class='demo-status'>AI-assisted assessment</div></div>",
        unsafe_allow_html=True)
    scores = result.get("scores", {})
    statuses = result.get("criterion_status", {})
    coverage = result.get("completeness", {}).get("coverage")
    cards = [
        _score_card("Pronunciation", scores.get("pronunciation"), "Sound accuracy and clarity", statuses.get("pronunciation", "UNAVAILABLE")),
        _score_card("Fluency", scores.get("fluency"), "Flow, continuity and pausing", statuses.get("fluency", "UNAVAILABLE")),
        _score_card("Prosody", scores.get("prosody"), "Stress, rhythm and intonation", statuses.get("prosody", "UNAVAILABLE")),
        _score_card("Reading Completeness", coverage, "Target text covered", statuses.get("completeness", "UNAVAILABLE"), percent=True),
    ]
    st.markdown("<div class='demo-score-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
    for failure in result.get("model_failures", []):
        st.info(failure["public_message"])
    _feedback(result)
    _evidence_explorer(result, root)
    _judge_panels()
    st.markdown("<div class='demo-footer'>Development and preliminary assessment. Not CEFR, B2 or IELTS.</div>", unsafe_allow_html=True)


def render_competition_demo(root: Path) -> None:
    st.markdown(COMPETITION_CSS, unsafe_allow_html=True)
    st.session_state.setdefault("competition_view", "home")
    view = st.session_state["competition_view"]
    if view == "home":
        _landing(root)
    elif view == "assessment":
        _assessment(root)
    elif view == "results" and st.session_state.get("competition_result"):
        _results(root, st.session_state["competition_result"])
    else:
        st.session_state["competition_view"] = "home"
        st.rerun()
