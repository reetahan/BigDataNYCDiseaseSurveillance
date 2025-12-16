import boto3
import os
import shutil
import time
from datetime import datetime
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv 

load_dotenv()
# --- CONFIGURATION ---
# Expects "data" folder to be in the same directory as this script
DATA_DIR = "data"
PROCESSED_DIR = "data_processed"

# AWS Configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "nyc-disease-surveillance-raw")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def get_s3_client():
    if AWS_ACCESS_KEY and AWS_SECRET_KEY:
        try:
            return boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY,
                aws_secret_access_key=AWS_SECRET_KEY,
                region_name=AWS_REGION
            )
        except Exception as e:
            print(f"Error creating S3 client: {e}")
            return None
    return None

def upload_files():
    print(f"--- Starting S3 Uploader Job at {datetime.now()} ---")
    
    s3 = get_s3_client()
    if s3:
        print(f"MODE: LIVE (Connected to Bucket: {AWS_BUCKET_NAME})")
    else:
        print("MODE: DRY RUN (No credentials found - mimicking upload)")

    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    files_found = 0
    files_uploaded = 0

    # Walk through the data directory
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            # Skip hidden files and gitkeeps
            if file.startswith('.') or file == ".gitkeep":
                continue

            # Process JSON, JSONL, and CSV
            if file.endswith(".json") or file.endswith(".csv") or file.endswith(".jsonl"):
                files_found += 1
                local_path = os.path.join(root, file)
                
                # relative_path becomes "nyc_311/311_data.json"
                relative_path = os.path.relpath(local_path, DATA_DIR)
                
                # s3_key becomes "raw/nyc_311/311_data.json"
                s3_key = f"raw/{relative_path.replace(os.sep, '/')}"

                try:
                    if s3:
                        # LIVE UPLOAD
                        print(f"Uploading: {relative_path} -> s3://{AWS_BUCKET_NAME}/{s3_key}")
                        s3.upload_file(local_path, AWS_BUCKET_NAME, s3_key)
                    else:
                        # MOCK UPLOAD
                        print(f"[Mock] Would upload: {relative_path} -> s3://{AWS_BUCKET_NAME}/{s3_key}")
                    
                    # Move to processed folder
                    dest_folder = os.path.join(PROCESSED_DIR, os.path.dirname(relative_path))
                    os.makedirs(dest_folder, exist_ok=True)
                    shutil.move(local_path, os.path.join(dest_folder, file))
                    files_uploaded += 1
                    
                except Exception as e:
                    print(f"Error processing {file}: {e}")

    print("-" * 40)
    print(f"Job Complete. Found {files_found} files. Processed {files_uploaded}.")
    if not s3:
        print("NOTE: Dry run mode. Set AWS keys to enable live upload.")

if __name__ == "__main__":
    upload_files()