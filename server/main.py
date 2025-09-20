from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import boto3
import random
import string
import os
from dotenv import load_dotenv
import asyncpg, os, random, string
from datetime import datetime

load_dotenv()

# ------------------------------
# CONFIG
# ------------------------------
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

ECS_CLUSTER = os.getenv("ECS_CLUSTER")
ECS_TASK = os.getenv("ECS_TASK")

# Convert comma-separated strings to lists
SUBNETS = os.getenv("SUBNETS", "").split(",") if os.getenv("SUBNETS") else []
SECURITY_GROUPS = os.getenv("SECURITY_GROUPS", "").split(",") if os.getenv("SECURITY_GROUPS") else []


# ------------------------------
# APP
# ------------------------------
app = FastAPI()

# ------------------------------
# AWS ECS CLIENT
# ------------------------------
ecs_client = boto3.client(
    "ecs",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# ---------------- DB Connection ----------------
@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()

# ------------------------------
# HELPERS
# ------------------------------
def generate_slug(length: int = 8) -> str:
    """Generate a random slug"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def serialize_record(record):
    if not record:
        return None
    data = dict(record)
    for k, v in data.items():
        if isinstance(v, datetime):
            data[k] = v.isoformat()
    return data

# ------------------------------
# ROUTES
# ------------------------------
@app.post("/deploy")
async def create_project(request: Request):
    body = await request.json()
    gitURL = body.get("gitURL")
    slug = body.get("slug") or generate_slug()

    async with app.state.db.acquire() as conn:
        async with conn.transaction():
            project = await conn.fetchrow("""
                INSERT INTO projects (slug, git_url)
                VALUES ($1, $2)
                ON CONFLICT (slug) DO UPDATE SET git_url = EXCLUDED.git_url
                RETURNING id, slug, git_url, created_at
            """, slug, gitURL)

            deployment = await conn.fetchrow("""
                INSERT INTO deployments (project_id, status)
                VALUES ($1, 'queued')
                RETURNING id, status, created_at
            """, project["id"])    

    command = {
        "cluster": ECS_CLUSTER,
        "taskDefinition": ECS_TASK,
        "launchType": "FARGATE",
        "count": 1,
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "assignPublicIp": "ENABLED",
                "subnets": SUBNETS,
                "securityGroups": SECURITY_GROUPS,
            }
        },
        "overrides": {
            "containerOverrides": [
                {
                    "name": "build-server-image",
                    "environment": [
                        {"name": "GIT_REPOSITORY_URL", "value": gitURL},
                        {"name": "PROJECT_ID", "value": slug},
                        {"name": "DEPLOYMENT_ID", "value": str(deployment["id"])},
                        {"name": "DATABASE_URL", "value": os.getenv("DATABASE_URL")},
                    ],
                }
            ]
        },
    }

    ecs_client.run_task(**command)

    return JSONResponse(
        {
            "status": "queued",
            "data": {
                "projectSlug": slug,
                "project": serialize_record(project),
                "deployment": serialize_record(deployment),
                "url": f"http://{slug}.localhost:8000",
            },
        }
    )
