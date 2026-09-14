import asyncio
from groq import AsyncGroq
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncGroq(api_key=settings.groq_api_key)
    try:
        res = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hi"}],
            reasoning_effort="low"
        )
        print("Success:", res)
    except Exception as e:
        print("Error with reasoning_effort:", type(e), e)

    try:
        res2 = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hi"}],
        )
        print("Success without reasoning_effort:", res2.choices[0].message.content)
    except Exception as e:
        print("Error without reasoning_effort:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())
