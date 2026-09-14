import asyncio
import traceback
from app.utils.llm_client import generate_structured
from app.agents.intake.gap_analyzer import RawSkillGapAnalysis, GAP_ANALYSIS_SYSTEM

async def main():
    try:
        print("Testing generate_structured call...")
        res = await generate_structured(
            system_prompt=GAP_ANALYSIS_SYSTEM,
            user_prompt="CANDIDATE ID: c1\nJOB ID: j1\nRESUME: Senior Python Dev with 5 years exp in FastAPI, PostgreSQL.\nSTRUCTURED JD: {\"job_title\": \"Senior Backend Engineer\", \"required_skills\": [{\"name\": \"Python\", \"proficiency\": \"expert\"}]}",
            response_model=RawSkillGapAnalysis,
        )
        print("Success! Result:", res)
    except Exception as e:
        print("ERROR OCCURRED:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
