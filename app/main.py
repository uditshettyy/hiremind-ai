from fastapi import FastAPI

app = FastAPI(title="AI Career Intelligence & Interview Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}


# Route registration will live in app/api/ and be included here, e.g.:
# from app.api import router as api_router
# app.include_router(api_router)
