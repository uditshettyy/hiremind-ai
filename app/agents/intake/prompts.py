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
Return a JSON object with EXACTLY these fields and no others:
{{
  "name": "candidate full name or null",
  "summary": "one-paragraph professional summary or null",
  "skills": [
    {{
      "skill_name": "canonical skill name",
      "category": "one of: technical, soft, domain, tool",
      "proficiency": "one of the five proficiency values above",
      "evidence": "brief quoted evidence from resume or null"
    }}
  ],
  "experience": ["one plain string per role, e.g. 'Software Engineer at Acme (2021-2023)'"],
  "projects": ["one plain string per project, e.g. 'Built a REST API with FastAPI and PostgreSQL'"],
  "education": ["one plain string per degree, e.g. 'B.Tech Computer Science, MIT, 2024'"]
}}
"""

JD_EXTRACTION_SYSTEM = f"""
Extract structured hiring requirements from the supplied job description.

Use only information present in the JD. Normalize synonymous skill names.
{_PROFICIENCY_SCALE}
required_level MUST be one of the five proficiency values above — do not use free text,
years, or any other scale for it.

Return a JSON object with EXACTLY these fields and no others:
{{
  "title": "job title or null",
  "company": "company name or null",
  "requirements": [
    {{
      "skill_name": "canonical skill name",
      "category": "one of: technical, soft, domain, tool",
      "required_level": "one of the five proficiency values above",
      "priority": 1,
      "evidence": "short quoted snippet from the JD"
    }}
  ],
  "responsibilities": ["one plain string per responsibility"],
  "raw_text": ""
}}

priority is an integer 1-5 (5 = explicitly mandatory / must have, 1 = nice-to-have).
Leave raw_text as an empty string — it is filled by the caller.
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

Return a JSON object with EXACTLY these fields and no others:
{{
  "overall_match_score": 0.0,
  "top_gaps": [
    {{
      "skill_name": "canonical skill name",
      "category": "one of: technical, soft, domain, tool",
      "jd_required_level": "one of the five proficiency values",
      "resume_claimed_level": "one of the five proficiency values",
      "gap_level": "the level candidate needs to reach",
      "gap_severity": 3,
      "jd_evidence": "quoted snippet from JD",
      "resume_evidence": "quoted snippet from resume or null",
      "suggested_focus": "one concrete second-person coaching sentence"
    }}
  ],
  "strengths": [],
  "metadata": {{}}
}}

For gap_severity (integer 1-5): compute as
  round((ordinal(jd_required_level) - ordinal(resume_claimed_level)) * priority_weight),
  clamped to [1, 5], where ordinal is absent=1, novice=2, competent=3,
  proficient=4, expert=5, and priority_weight is the requirement's priority (1-5)
  divided by 5. Use 1 for strengths (no actual gap).

overall_match_score (0.0-1.0): priority-weighted average of
  min(resume_ordinal / jd_ordinal, 1.0) across all requirements.

Order top_gaps by gap_severity descending.
"""