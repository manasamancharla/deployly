import os
import subprocess
import boto3
import mimetypes
import shutil
from pathlib import Path
import asyncpg
import asyncio
from datetime import timezone, datetime

# --- AWS S3 setup ---
s3 = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

BUCKET_NAME = os.getenv("S3_BUCKET", "vercel-clone-outputs")
PROJECT_ID = os.getenv("PROJECT_ID")
REPO_URL = os.getenv("GIT_REPOSITORY_URL")  
OUTPUT_DIR = Path("/app/output")
DEPLOYMENT_ID = os.getenv("DEPLOYMENT_ID")   # new
DATABASE_URL = os.getenv("DATABASE_URL") 

async def update_status(status: str, url: str = None):
    if not DEPLOYMENT_ID or not DATABASE_URL:
        return
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None) 
        if url:
            await conn.execute(
                "UPDATE deployments SET status = $1, url = $2, updated_at = $3 WHERE id = $4",
                status,
                url,
                now_utc,
                int(DEPLOYMENT_ID),
            )
        else:
            await conn.execute(
                "UPDATE deployments SET status = $1, updated_at = $2 WHERE id = $3",
                status,
                now_utc,
                int(DEPLOYMENT_ID),
            )
    finally:
        await conn.close()

def clone_repo():
    """Clone the git repo fresh into /app/output"""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    print(f"Cloning {REPO_URL} into {OUTPUT_DIR}...")
    subprocess.run(["git", "clone", REPO_URL, str(OUTPUT_DIR)], check=True)


def run_build():
    """Run npm install && npm run build in /app/output"""
    process = subprocess.Popen(
        "npm install && npm run build",
        cwd=OUTPUT_DIR,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in process.stdout:
        print(line.strip())  

    process.wait()
    if process.returncode != 0:
        raise RuntimeError("❌ Build failed")
    print("✅ Build complete")


def upload_dist():
    """Upload /dist folder to S3"""
    dist_dir = OUTPUT_DIR / "dist"
    if not dist_dir.exists():
        raise FileNotFoundError("dist folder not found after build")

    for file_path in dist_dir.rglob("*"):
        if file_path.is_file():
            key = f"__outputs/{PROJECT_ID}/{file_path.relative_to(dist_dir)}"
            content_type, _ = mimetypes.guess_type(str(file_path))

            s3.upload_file(
                str(file_path),
                BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": content_type or "application/octet-stream"},
            )
            print(f"Uploaded {key}")

    print("🚀 Deployment finished")

if __name__ == "__main__":
    print("Starting build + deploy...")
    async def runner():
        deployment_url = f"http://{PROJECT_ID}.localhost:8000"
        try:
            await update_status("building")
            clone_repo()
            run_build()
            upload_dist()
            await update_status("success", url=deployment_url)
        except Exception as e:
            print(f"Build failed: {e}")
            await update_status("failed")
    asyncio.run(runner())