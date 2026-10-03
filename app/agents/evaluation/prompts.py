"""Prompts for Module 3 (Evaluation & Reporting). Versioned with the module."""
from __future__ import annotations

from app.core.schemas import InterviewTurn, QuestionType, SkillGap, SkillGapReport

SCORER_SYSTEM_PROMPT = """You are an expert technical interviewer and evaluator. \
You score a single candidate answer against a single interview question, \
strictly and fairly, grounded only in the evidence provided (the question, \
the answer, the job description, the resume, and prior turns in this session).

Score five dimensions, each 0.0-10.0, with a one-to-two-sentence rationale \
grounded in the answer text:
- accuracy: is the technical/factual content correct?
- depth: does it show nuanced, non-superficial understanding?
- clarity: is it well-structured and easy to follow?
- relevance: does it actually address the question asked?
- confidence: does the phrasing read as confident and decisive (text proxy \
  for delivery), rather than hedging or rambling?

If the question is a BEHAVIORAL question, evaluate clarity specifically \
against the STAR framework (Situation, Task, Action, Result). An answer that \
jumps straight to a result with no situation/task framing, or that never \
states a concrete action the candidate personally took, should score lower \
on clarity and depth even if the outcome described sounds good.

Never invent facts not present in the answer. If the answer is vague, say so \
in the rationale rather than assuming positive intent.

Respond with ONLY a JSON object (no markdown fences, no preamble) matching \
this exact shape:
{
  "dimension_scores": [
    {"dimension": "accuracy", "score": <float>, "rationale": "<string>"},
    {"dimension": "depth", "score": <float>, "rationale": "<string>"},
    {"dimension": "clarity", "score": <float>, "rationale": "<string>"},
    {"dimension": "relevance", "score": <float>, "rationale": "<string>"},
    {"dimension": "confidence", "score": <float>, "rationale": "<string>"}
  ],
  "summary_feedback": "<2-4 paragraphs of actionable feedback, addressed to the candidate>",
  "strengths": ["<up to 5 short strength bullets>"],
  "improvements": ["<up to 5 short improvement bullets>"],
  "model_answer_snippet": "<a concise exemplar answer to this question, 2-4 sentences>",
  "skill_level_inferred": "<one of: expert, proficient, competent, novice, absent>",
  "suggested_follow_up": "<a natural follow-up question if the answer leaves something \
underexplored, else null>"
}
"""


def build_scorer_user_prompt(
    *,
    turn: InterviewTurn,
    skill_gap: SkillGap | None,
    skill_gap_report: SkillGapReport,
    session_history: list[InterviewTurn],
    job_description_text: str,
    candidate_resume_text: str,
) -> str:
    q = turn.question
    star_note = (
        "\nThis is a BEHAVIORAL question â€” apply the STAR rubric explicitly in your clarity rationale."
        if q.question_type == QuestionType.BEHAVIORAL
        else ""
    )

    gap_note = "No matching entry found in the skill-gap report for this skill."
    if skill_gap is not None:
        gap_note = (
            f"JD requires '{skill_gap.jd_required_level.value}', resume claimed "
            f"'{skill_gap.resume_claimed_level.value}', gap_severity={skill_gap.gap_severity}/5. "
            f"Coaching focus on file: {skill_gap.suggested_focus}"
        )

    history_lines = []
    for t in session_history[-4:]:  # last few turns only â€” keep prompt lean
        if t.evaluation is not None:
            history_lines.append(
                f"- Turn {t.turn_number} ({t.question.target_skill}): "
                f"weighted_score={t.evaluation.weighted_score:.1f}, "
                f"routing_hint={t.evaluation.routing_hint}"
            )
    history_block = "\n".join(history_lines) if history_lines else "(no prior evaluated turns)"

    return f"""## Question (turn {turn.turn_number}, id={q.question_id})
Type: {q.question_type.value} | Difficulty: {q.difficulty.value} | Target skill: {q.target_skill}
Text: {q.question_text}
Rubric â€” a strong answer should cover: {", ".join(q.expected_bullet_points) or "(none specified)"}{star_note}

## Candidate answer
{turn.answer_text}

## Skill-gap context for '{q.target_skill}'
{gap_note}
Candidate's overall match score for this role: {skill_gap_report.overall_match_score:.2f}

## Prior turns in this session (for consistency / avoiding repetitive feedback)
{history_block}

## Grounding material (use only to check factual claims, do not quote at length)
Job description (excerpt): {job_description_text[:1500]}
Resume (excerpt): {candidate_resume_text[:1500]}

Score this answer now, per the system instructions.
"""


REPORT_SYSTEM_PROMPT = """You are writing the closing narrative sections of a \
candidate's mock-interview feedback report. You are given aggregated scores \
and per-turn feedback already computed by upstream logic â€” do not recompute \
numbers, only synthesize narrative text from what's given.

Respond with ONLY a JSON object (no markdown fences, no preamble):
{
  "executive_summary": "<3-5 sentences, direct and encouraging but honest>",
  "top_strengths": ["<up to 5 short bullets>"],
  "priority_gaps": ["<up to 5 short bullets, ordered by importance>"],
  "study_plan": ["<4-8 ordered, specific, actionable recommendations. Where a \
turn's model_answer_snippet illustrates a stronger way to answer a similar \
question, reference it by turn number, e.g. 'Review the exemplar answer for \
turn 3 on distributed caching and practice restructuring your own answers \
around it.'>"]
}
"""


def build_report_user_prompt(
    *,
    dimension_averages: dict[str, float],
    overall_score: float,
    readiness_level: str,
    per_turn_summaries: list[str],
    skill_progression_summaries: list[str],
) -> str:
    return f"""## Aggregate scores
Overall score: {overall_score:.1f}/10
Readiness level: {readiness_level}
Dimension averages: {dimension_averages}

## Skill progressions
{chr(10).join(skill_progression_summaries) or "(none)"}

## Per-turn evaluation summaries
{chr(10).join(per_turn_summaries)}

Write the narrative sections now, per the system instructions.
"""

