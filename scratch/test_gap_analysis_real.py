import asyncio
import traceback
from app.utils.llm_client import generate_structured
from app.agents.intake.gap_analyzer import RawSkillGapAnalysis, GAP_ANALYSIS_SYSTEM
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
            JDRequirement(
                skill_name="Kubernetes",
                category="tool",
                required_level="expert",
                priority=5,
                evidence="Expert-level experience with Kubernetes in production"
            ),
            JDRequirement(
                skill_name="PostgreSQL",
                category="technical",
                required_level="proficient",
                priority=4,
                evidence="Strong PostgreSQL skills, including query optimization"
            ),
        ],
        responsibilities=["Build services"],
        raw_text="JD text..."
    )

    resume_text = """Jane Doe
Backend engineer with 4 years building Python services.
FastAPI, PostgreSQL schema design and query optimization.
No Kubernetes experience.
"""

    user_prompt = f"""CANDIDATE ID: cand-123
JOB ID: job-456

RESUME:
{resume_text}

STRUCTURED JD:
{parsed_jd.model_dump_json(indent=2)}
"""

    try:
        print("Calling generate_structured for RawSkillGapAnalysis...")
        res = await generate_structured(
            system_prompt=GAP_ANALYSIS_SYSTEM,
            user_prompt=user_prompt,
            response_model=RawSkillGapAnalysis,
        )
        print("RESULT SUCCESS:")
        print(res.model_dump_json(indent=2))
    except Exception:
        print("FAILED WITH EXCEPTION:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
