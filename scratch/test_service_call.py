import asyncio
import traceback
from app.utils.llm_client import generate_structured
from app.utils.vector_store import embed_texts
from app.agents.intake.service import analyze_skill_gap
from app.agents.intake.jd_parser import ParsedJobDescription, JDRequirement

async def main():
    parsed_jd = ParsedJobDescription(
        title="Senior Backend Engineer",
        company="NovaTech",
        requirements=[
            JDRequirement(
                skill_name="Python",
                category="technical",
                required_level="expert",
                priority=5,
                evidence="5+ years of professional Python development"
            ),
        ],
        responsibilities=["Build services"],
        raw_text="JD text..."
    )

    resume_text = "Jane Doe. Python developer."

    try:
        print("Calling analyze_skill_gap WITHOUT db_session...")
        report = await analyze_skill_gap(
            candidate_id="cand-123",
            job_id="job-456",
            resume_text=resume_text,
            parsed_jd=parsed_jd,
            generate_structured=generate_structured,
            db_session=None,
            embed_fn=embed_texts,
        )
        print("SUCCESS WITHOUT DB! Report ID:", report.report_id)
        print("Match score:", report.overall_match_score)
        print("Top gaps count:", len(report.top_gaps))
        print("Strengths count:", len(report.strengths))
    except Exception:
        print("FAILED WITHOUT DB:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
