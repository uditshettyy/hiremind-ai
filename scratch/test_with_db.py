import asyncio
import traceback
from app.core.database import get_db
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

    async for db in get_db():
        try:
            print("Calling analyze_skill_gap WITH real DB session...")
            report = await analyze_skill_gap(
                candidate_id="cand-123",
                job_id="job-456",
                resume_text=resume_text,
                parsed_jd=parsed_jd,
                generate_structured=generate_structured,
                db_session=db,
                embed_fn=embed_texts,
            )
            print("SUCCESS WITH DB! Report ID:", report.report_id)
        except Exception:
            print("FAILED WITH DB:")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
