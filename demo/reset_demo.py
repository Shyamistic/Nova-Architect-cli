"""
Nova Architect — Demo Reset Script
Run this between demo takes to clean up all AWS resources created.
YOU WILL NEED THIS. Run it every time before re-recording.
"""

import boto3
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
DEMO_PREFIX = "nova-architect"  # Only deletes resources with this prefix


def reset_demo():
    print("\n🔄 Nova Architect — Demo Reset\n" + "="*50)
    print(f"⚠️  This will DELETE all AWS resources prefixed with '{DEMO_PREFIX}'")
    confirm = input("Type 'reset' to confirm: ")
    if confirm.lower() != "reset":
        print("Cancelled.")
        return

    s3 = boto3.client("s3", region_name=REGION)
    dynamodb = boto3.client("dynamodb", region_name=REGION)
    lambda_client = boto3.client("lambda", region_name=REGION)
    apigateway = boto3.client("apigatewayv2", region_name=REGION)

    errors = []

    # 1. Delete S3 buckets
    print("\n[1/4] Deleting S3 buckets...")
    try:
        buckets = s3.list_buckets()["Buckets"]
        demo_buckets = [b for b in buckets if b["Name"].startswith(DEMO_PREFIX)]
        for bucket in demo_buckets:
            name = bucket["Name"]
            try:
                # Empty bucket first
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=name):
                    objects = page.get("Contents", [])
                    if objects:
                        s3.delete_objects(
                            Bucket=name,
                            Delete={"Objects": [{"Key": o["Key"]} for o in objects]}
                        )
                s3.delete_bucket(Bucket=name)
                print(f"  ✅ Deleted bucket: {name}")
            except Exception as e:
                errors.append(f"S3 {name}: {e}")
                print(f"  ❌ Failed to delete {name}: {e}")
    except Exception as e:
        errors.append(f"S3 list: {e}")

    # 2. Delete DynamoDB tables
    print("\n[2/4] Deleting DynamoDB tables...")
    try:
        tables = dynamodb.list_tables()["TableNames"]
        demo_tables = [t for t in tables if t.startswith(DEMO_PREFIX)]
        for table in demo_tables:
            try:
                dynamodb.delete_table(TableName=table)
                print(f"  ✅ Deleted table: {table}")
            except Exception as e:
                errors.append(f"DynamoDB {table}: {e}")
                print(f"  ❌ Failed to delete {table}: {e}")
    except Exception as e:
        errors.append(f"DynamoDB list: {e}")

    # 3. Delete Lambda functions
    print("\n[3/4] Deleting Lambda functions...")
    try:
        functions = lambda_client.list_functions()["Functions"]
        demo_fns = [f for f in functions if f["FunctionName"].startswith(DEMO_PREFIX)]
        for fn in demo_fns:
            name = fn["FunctionName"]
            try:
                lambda_client.delete_function(FunctionName=name)
                print(f"  ✅ Deleted function: {name}")
            except Exception as e:
                errors.append(f"Lambda {name}: {e}")
                print(f"  ❌ Failed to delete {name}: {e}")
    except Exception as e:
        errors.append(f"Lambda list: {e}")

    # 4. Delete API Gateways
    print("\n[4/4] Deleting API Gateways...")
    try:
        apis = apigateway.get_apis()["Items"]
        demo_apis = [a for a in apis if a["Name"].startswith(DEMO_PREFIX)]
        for api in demo_apis:
            api_id = api["ApiId"]
            name = api["Name"]
            try:
                apigateway.delete_api(ApiId=api_id)
                print(f"  ✅ Deleted API: {name}")
            except Exception as e:
                errors.append(f"API {name}: {e}")
                print(f"  ❌ Failed to delete {name}: {e}")
    except Exception as e:
        errors.append(f"API list: {e}")

    print("\n" + "="*50)
    if errors:
        print(f"⚠️  Reset complete with {len(errors)} errors:")
        for err in errors:
            print(f"   - {err}")
    else:
        print("✅ Reset complete! AWS account is clean.")
    print("   Ready to record another demo take.\n")


if __name__ == "__main__":
    reset_demo()
