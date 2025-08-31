from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import boto3
import random
import string
import os
from dotenv import load_dotenv

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


# ------------------------------
# HELPERS
# ------------------------------
def generate_slug(length: int = 8) -> str:
    """Generate a random slug"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ------------------------------
# ROUTES
# ------------------------------
@app.post("/project")
async def create_project(request: Request):
    body = await request.json()
    gitURL = body.get("gitURL")
    slug = body.get("slug") or generate_slug()

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
                        {"name": "GIT_REPOSITORY__URL", "value": gitURL},
                        {"name": "PROJECT_ID", "value": slug},
                    ],
                }
            ]
        },
    }

    ecs_client.run_task(**command)

    return JSONResponse(
        {
            "status": "queued",
            "data": {"projectSlug": slug, "url": f"http://{slug}.localhost:8000"},
        }
    )
