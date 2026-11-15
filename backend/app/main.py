from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import health

app = FastAPI(title="Studio AI")
# Chỉ cho frontend dev (Vite) gọi; backend vốn chỉ nghe trên localhost.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def get_health(deep: bool = False):
    return await health.check(deep)
