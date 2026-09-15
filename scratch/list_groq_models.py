import asyncio
from groq import AsyncGroq
from app.config import get_settings

async def main():
    settings = get_settings()
    client = AsyncGroq(api_key=settings.groq_api_key)
    models = await client.models.list()
    print("Available Groq models:")
    for m in models.data:
        print(" -", m.id)

if __name__ == "__main__":
    asyncio.run(main())
