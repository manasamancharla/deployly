from fastapi import FastAPI, Request, Response
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

BASE_PATH = os.getenv("BASE_PATH")


@app.middleware("http")
async def proxy_to_s3(request: Request, call_next):
    hostname = request.headers.get("host", "")
    subdomain = hostname.split(".")[0] if "." in hostname else hostname

    # TODO: Replace with DB lookup for custom domains if needed
    resolves_to = f"{BASE_PATH}/{subdomain}"

    # Preserve path, fallback to index.html for "/" and SPA routes
    path = request.url.path
    if path == "/":
        path = "/index.html"

    target_url = f"{resolves_to}{path}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(target_url)

            # SPA fallback: if not found, serve index.html
            if resp.status_code == 404:
                fallback_url = f"{resolves_to}/index.html"
                resp = await client.get(fallback_url)

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )
        except Exception as e:
            return Response(
                content=f"Proxy error: {str(e)}",
                status_code=500,
            )
