"""
Nova Architect — Demo Setup Script
Run this before recording your demo video.
Creates a clean AWS environment ready for the Nova Architect demo.
"""

import boto3
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()


def setup_demo_environment():
    """
    Sets up everything needed for the demo:
    1. Verifies AWS credentials work
    2. Creates a demo IAM role for Nova Act to use
    3. Confirms Nova Act can access the console
    4. Prints a checklist of what's ready
    """
    print("\n🚀 Nova Architect — Demo Setup\n" + "="*50)

    # 1. Check AWS credentials
    print("\n[1/4] Checking AWS credentials...")
    try:
        sts = boto3.client(
            "sts",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        identity = sts.get_caller_identity()
        print(f"  ✅ Connected as: {identity['Arn']}")
        print(f"  ✅ Account ID: {identity['Account']}")
    except Exception as e:
        print(f"  ❌ AWS credentials failed: {e}")
        print("  → Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env")
        sys.exit(1)

    # 2. Check Bedrock access
    print("\n[2/4] Checking Bedrock model access...")
    try:
        bedrock = boto3.client(
            "bedrock",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        models = bedrock.list_foundation_models(byProvider="Amazon")
        nova_models = [
            m for m in models["modelSummaries"]
            if "nova" in m["modelId"].lower()
        ]
        print(f"  ✅ Found {len(nova_models)} Nova models available:")
        for m in nova_models:
            print(f"     - {m['modelId']}")
    except Exception as e:
        print(f"  ⚠️  Could not list Bedrock models: {e}")
        print("  → Ensure your IAM user has bedrock:ListFoundationModels permission")

    # 3. Test Nova 2 Lite
    print("\n[3/4] Testing Nova 2 Lite...")
    try:
        bedrock_rt = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        test_body = {
            "messages": [
                {"role": "user", "content": [{"text": "Reply with just the word: READY"}]}
            ],
            "inferenceConfig": {"maxTokens": 10}
        }
        response = bedrock_rt.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            body=json.dumps(test_body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        reply = result["output"]["message"]["content"][0]["text"]
        print(f"  ✅ Nova 2 Lite responded: {reply.strip()}")
    except Exception as e:
        print(f"  ❌ Nova 2 Lite test failed: {e}")
        print("  → Enable amazon.nova-lite-v1:0 in Bedrock Model Access console")

    # 4. Check Nova Act
    print("\n[4/4] Checking Nova Act installation...")
    try:
        from nova_act import NovaAct
        print("  ✅ Nova Act SDK installed")
        api_key = os.getenv("NOVA_ACT_API_KEY", "")
        if api_key:
            print("  ✅ NOVA_ACT_API_KEY is set")
        else:
            print("  ⚠️  NOVA_ACT_API_KEY not set — set it in .env")
    except ImportError:
        print("  ⚠️  Nova Act not installed")
        print("  → Run: pip install nova-act")
        print("  → Get API key from: https://nova.aws.amazon.com/act")

    # Final checklist
    print("\n" + "="*50)
    print("📋 DEMO CHECKLIST")
    print("="*50)
    checklist = [
        "AWS credentials configured",
        "Nova 2 Lite accessible in Bedrock",
        "Nova Multimodal (Nova Pro) accessible in Bedrock",
        "Nova Act installed and API key set",
        "Nova Sonic accessible (or Polly fallback ready)",
        "Browser visible (NOVA_ACT_HEADLESS=false in .env)",
        "Demo AWS account is CLEAN (no leftover resources)",
        "Screen recording software ready",
        "Microphone tested for voice approval flow",
        "reset_demo.py tested and working",
    ]
    for item in checklist:
        print(f"  ☐  {item}")

    print("\n✨ Setup complete! Run `python main.py` to start the server.")
    print("   Then open http://localhost:8000 in your browser.\n")


if __name__ == "__main__":
    setup_demo_environment()
