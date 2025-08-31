import os
import subprocess
import boto3
import mimetypes
import shutil
from pathlib import Path

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
    clone_repo()   
    run_build()
    upload_dist()
