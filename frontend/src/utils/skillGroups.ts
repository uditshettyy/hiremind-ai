import type { SkillGap, SkillGapReport } from "../api/types";

export interface SkillGroups {
  matched: SkillGap[];
  partial: SkillGap[];
  missing: SkillGap[];
}

/**
 * The report has two lists: `strengths` (resume meets the JD) and `top_gaps`
 * (sorted by severity). Gaps are split by whether the resume shows the skill
 * at all: "absent" = missing, anything else = partial.
 */
export function groupSkills(report: SkillGapReport): SkillGroups {
  return {
    matched: report.strengths,
    partial: report.top_gaps.filter((g) => g.resume_claimed_level !== "absent"),
    missing: report.top_gaps.filter((g) => g.resume_claimed_level === "absent"),
  };
}
