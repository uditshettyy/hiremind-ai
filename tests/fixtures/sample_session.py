"""Sample session fixtures for unit and integration tests."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.schemas import (
    Difficulty,
    InterviewTurn,
    ProficiencyLevel,
    Question,
    QuestionType,
    SkillGap,
    SkillGapReport,
    TurnStatus,
)

CANDIDATE_RESUME_TEXT = """Jane Doe
Backend Engineer with 4 years of experience building Python & FastAPI microservices.
Owned PostgreSQL schema design and query optimization at Acme Corp.
"""

JOB_DESCRIPTION_TEXT = """Senior Backend Engineer at NovaTech
Requirements:
- Strong experience with PostgreSQL database indexing and query tuning
- Demonstrated conflict resolution and cross-functional leadership skills
- Experience managing production incidents and on-call rotations
"""

SKILL_GAP_REPORT = SkillGapReport(
    report_id="report-001",
    candidate_id="cand-001",
    job_id="job-001",
    generated_at=datetime.now(timezone.utc),
    overall_match_score=0.75,
    top_gaps=[
        SkillGap(
            skill_name="conflict_resolution",
            category="soft",
            jd_required_level=ProficiencyLevel.PROFICIENT,
            resume_claimed_level=ProficiencyLevel.ABSENT,
            gap_level=ProficiencyLevel.PROFICIENT,
            gap_severity=3,
            jd_evidence="Demonstrated conflict resolution skills",
            resume_evidence=None,
            suggested_focus="Structure behavioral answers using STAR framework.",
        ),
        SkillGap(
            skill_name="incident_response",
            category="domain",
            jd_required_level=ProficiencyLevel.EXPERT,
            resume_claimed_level=ProficiencyLevel.COMPETENT,
            gap_level=ProficiencyLevel.EXPERT,
            gap_severity=4,
            jd_evidence="Experience managing production incidents",
            resume_evidence="Helped resolve team service degradation",
            suggested_focus="Focus on root cause analysis and post-mortems.",
        ),
    ],
    strengths=[
        SkillGap(
            skill_name="postgres_indexing",
            category="technical",
            jd_required_level=ProficiencyLevel.COMPETENT,
            resume_claimed_level=ProficiencyLevel.PROFICIENT,
            gap_level=ProficiencyLevel.COMPETENT,
            gap_severity=1,
            jd_evidence="Strong experience with PostgreSQL database indexing",
            resume_evidence="Owned PostgreSQL schema design and query optimization",
            suggested_focus="Highlight production query tuning results.",
        ),
    ],
)

TURN_STRONG_TECHNICAL = InterviewTurn(
    turn_number=1,
    question=Question(
        question_id="q-indexing-1",
        question_text="Explain B-tree vs Hash index in PostgreSQL.",
        question_type=QuestionType.TECHNICAL,
        target_skill="postgres_indexing",
        difficulty=Difficulty.MEDIUM,
        expected_bullet_points=["B-tree supports range queries", "Hash index is equality only"],
    ),
    answer_text="B-tree indexes support range queries like GREATER THAN or LESS THAN because nodes are kept ordered, while Hash indexes only support equality comparisons using a hash function.",
    status=TurnStatus.ANSWERED,
)

TURN_WEAK_BEHAVIORAL = InterviewTurn(
    turn_number=2,
    question=Question(
        question_id="q-conflict-1",
        question_text="Describe a conflict with a team member and how you resolved it.",
        question_type=QuestionType.BEHAVIORAL,
        target_skill="conflict_resolution",
        difficulty=Difficulty.MEDIUM,
        expected_bullet_points=["Situation context", "Specific action taken", "Measurable outcome"],
    ),
    answer_text="We disagreed about API routes so we talked and picked one.",
    status=TurnStatus.ANSWERED,
)

TURN_MEDIOCRE_SITUATIONAL = InterviewTurn(
    turn_number=3,
    question=Question(
        question_id="q-incident-1",
        question_text="What do you do if a production DB CPU hits 99%?",
        question_type=QuestionType.SITUATIONAL,
        target_skill="incident_response",
        difficulty=Difficulty.HARD,
        expected_bullet_points=["Check slow log / pg_stat_activity", "Identify long queries", "Kill or tune offending queries"],
    ),
    answer_text="I would check the slow query log, look at active connections in pg_stat_activity, and scale up if needed.",
    status=TurnStatus.ANSWERED,
)

TURN_TOO_SHORT = InterviewTurn(
    turn_number=4,
    question=Question(
        question_id="q-short-1",
        question_text="Tell me about yourself.",
        question_type=QuestionType.BEHAVIORAL,
        target_skill="communication",
        difficulty=Difficulty.EASY,
    ),
    answer_text="I code well.",
    status=TurnStatus.ANSWERED,
)
