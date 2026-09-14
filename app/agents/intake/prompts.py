"""Prompts for the Intake & Analysis Agent."""

_PROFICIENCY_SCALE = """
Proficiency scale (use exactly these five values):
expert = can teach it / clear advanced evidence (deep ownership, 5+ years, led/architected)
proficient = can perform independently / strong practical evidence (2-5 years, production use)
competent = can perform with some help / moderate evidence (<2 years or one project)
novice = basic exposure (mentioned only in passing, no supporting depth)
absent = not mentioned / no evidence at all
"""

RESUME_EXTRACTION_SYSTEM = f"""
Extract structured candidate information from the supplied resume.

Use only evidence present in the resume. Do not invent skills, experience,
projects, education, dates, or proficiency.

Normalize synonymous skill names to canonical names.
{_PROFICIENCY_SCALE}
Return only data matching the requested structured schema.
"""

JD_EXTRACTION_SYSTEM = f"""
Extract structured hiring requirements from the supplied job description.

Use only information present in the JD. Normalize synonymous skill names.
For each requirement provide skill_name, category, required_level, priority
(1-5, where 5 = explicitly mandatory / "must have", 1 = a minor nice-to-have),
and a short evidence snippet quoted from the JD.
{_PROFICIENCY_SCALE}
required_level MUST be one of the five values above — do not use free text,
years, or any other scale for it.

Also extract the role title, company if stated, and responsibilities.
Do not invent information.
"""

GAP_ANALYSIS_SYSTEM = f"""
Compare the candidate resume evidence with the job requirements semantically,
resolving synonyms (e.g. "Postgres" ~ "PostgreSQL", "React.js" ~ "React").
{_PROFICIENCY_SCALE}
For EVERY JD requirement, classify it and route it into the correct output list:

- "matched": resume_claimed_level >= jd_required_level on the scale above.
  -> Add this skill's SkillGap object to the `strengths` list.
- "partial" or "missing": resume_claimed_level < jd_required_level (including
  "absent" when nothing in the resume supports the skill at all).
  -> Add this skill's SkillGap object to the `top_gaps` list.

For every SkillGap you emit, set:
- gap_level: the proficiency level the candidate would need to reach to close
  the gap (equal to jd_required_level for gaps; equal to jd_required_level for
  matches too, since there is no gap to describe otherwise).
- gap_severity (1-5, gaps only — use 1 for matches): compute as
  round((ordinal(jd_required_level) - ordinal(resume_claimed_level)) * priority_weight),
  clamped to [1, 5], where ordinal is absent=1, novice=2, competent=3,
  proficient=4, expert=5, and priority_weight is the requirement's priority (1-5)
  divided by 5. Never leave severity at 0 for an actual gap.
- resume_evidence: null if the skill is absent from the resume.
- suggested_focus: one concrete, second-person coaching sentence specific to
  this skill — not generic advice.

Populate overall_match_score (0.0-1.0) as the priority-weighted average of
min(resume_ordinal / jd_ordinal, 1.0) across all requirements.

Order `top_gaps` by gap_severity descending. Return a complete SkillGapReport.
"""