import asyncio
from groq import AsyncGroq
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncGroq(api_key=settings.groq_api_key)
    print("Testing openai/gpt-oss-20b with reasoning_effort...")
    try:
        res = await client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Hello"}],
            reasoning_effort="low"
        )
        print("With reasoning_effort success:", res.choices[0].message.content)
    except Exception as e:
        print("With reasoning_effort ERROR:", type(e), e)

    print("\nTesting openai/gpt-oss-20b WITHOUT reasoning_effort...")
    try:
        res = await client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Hello"}],
        )
        print("WITHOUT reasoning_effort success:", res.choices[0].message.content)
    except Exception as e:
        print("WITHOUT reasoning_effort ERROR:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())
