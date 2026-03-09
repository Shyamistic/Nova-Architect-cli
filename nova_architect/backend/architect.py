"""
Nova Architect — Architecture Design Agent
Uses Amazon Nova 2 Lite via Bedrock to reason about AWS architecture
"""

import json
import time
import logging
import boto3
import os
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Nova Architect, the world's best AWS solutions architect.
Your job is to take a user's plain-English application requirement and design the 
optimal AWS serverless architecture.

You always output a structured JSON architecture plan with:
- services: list of AWS services to create (in dependency order)
- diagram: ASCII representation of the architecture
- estimated_cost: monthly cost estimate
- rationale: why you chose this architecture
- clarifying_questions: any questions you have (max 1-2)

Each service in the list must have:
- name: human-readable name (e.g. "Image Upload Bucket") — ALWAYS append the provided uid suffix to make it unique
- aws_service: the AWS service (e.g. "S3", "Lambda", "DynamoDB", "API Gateway")
- aws_console_url: The direct, exact AWS console URL where the creation of this service begins (e.g. "https://console.aws.amazon.com/s3/"). 
- action: A highly detailed, step-by-step instruction string for an autonomous browser automation agent to create this service. Be explicitly specific about what to click, what text to type, and what to wait for.
- config: key configuration values as a dict — resource names (bucket_name, table_name, function_name, api_name, queue_name) MUST include the uid suffix
- depends_on: list of service names this depends on (empty if none)

You are opinionated, clear, and always choose the simplest architecture that solves
the problem. You prefer serverless over servers, managed over self-managed.
Use python3.12 as the default Lambda runtime (NOT python3.8 or python3.9 — those are deprecated).

CRITICAL: Output valid JSON only. No markdown, no explanation outside the JSON."""

REFINE_PROMPT = """Given this vision analysis of an architecture diagram:
{vision_data}

Convert this into a complete AWS architecture plan following the same JSON schema, including aws_console_url and detailed agent action strings.
Fill in any gaps intelligently. Use the uid suffix: -{uid} on ALL resource names.
Output valid JSON only."""


def _uid() -> str:
    """Generate a short 5-char hex suffix based on current timestamp for unique resource names."""
    return hex(int(time.time()) % 0xFFFFF)[2:].zfill(5)


class ArchitectAgent:

    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        self.model_id = "amazon.nova-lite-v1:0"

    async def design(self, requirement: str) -> dict:
        """Design an AWS architecture from a natural language requirement."""
        uid = _uid()
        prompt = f"""Design an AWS architecture for this requirement:

"{requirement}"

IMPORTANT: Append the suffix "-{uid}" to ALL resource names (bucket names, table names, 
function names, API names, queue names, etc.) to ensure global uniqueness. For example:
- S3 bucket: "my-bucket-{uid}"
- Lambda: "my-function-{uid}"
- DynamoDB table: "my-table-{uid}"

Use python3.12 as the Lambda runtime.

Remember: output valid JSON only with the full architecture plan."""

        logger.info(f"Designing architecture for: {requirement[:80]}... (uid={uid})")
        response = self._invoke(prompt)
        architecture = self._parse_json(response)
        architecture["services"] = self._deduplicate_services(architecture.get("services", []))
        architecture["uid"] = uid
        return architecture

    async def design_from_vision(self, vision_result: dict) -> dict:
        """Convert a vision analysis of a diagram into a full architecture plan."""
        uid = _uid()
        prompt = REFINE_PROMPT.format(
            vision_data=json.dumps(vision_result, indent=2),
            uid=uid,
        )
        response = self._invoke(prompt)
        architecture = self._parse_json(response)
        architecture["services"] = self._deduplicate_services(architecture.get("services", []))
        architecture["uid"] = uid
        return architecture

    def _deduplicate_services(self, services: list) -> list:
        """
        Remove duplicate services from the list.
        - Keeps the FIRST occurrence of each aws_service type for API Gateway
        - Deduplicates any service whose config name already appeared
        """
        seen_names: set = set()
        seen_api_gateway = False
        deduped = []

        for svc in services:
            aws_service = svc.get("aws_service", "")
            # Extract the canonical resource name from config
            config = svc.get("config", {})
            resource_name = (
                config.get("function_name")
                or config.get("table_name")
                or config.get("bucket_name")
                or config.get("api_name")
                or config.get("queue_name")
                or config.get("topic_name")
                or config.get("role_name")
                or svc.get("name", "")
            )

            # Deduplicate API Gateways — only allow one
            if aws_service == "API Gateway":
                if seen_api_gateway:
                    logger.info(f"Deduplicating extra API Gateway: {svc.get('name')}")
                    continue
                seen_api_gateway = True

            # Deduplicate by resource name
            if resource_name and resource_name in seen_names:
                logger.info(f"Deduplicating duplicate service: {svc.get('name')}")
                continue

            if resource_name:
                seen_names.add(resource_name)
            deduped.append(svc)

        return deduped

    def summarize_for_voice(self, architecture: dict) -> str:
        """Create a concise spoken summary of the architecture for Nova Sonic."""
        services = architecture.get("services", [])
        service_names = [s.get("aws_service") for s in services]
        unique_services = list(dict.fromkeys(service_names))  # dedupe, preserve order

        cost = architecture.get("estimated_cost", "unknown")
        rationale = architecture.get("rationale", "")

        if len(unique_services) > 1:
            service_list = ", ".join(unique_services[:-1]) + f", and {unique_services[-1]}"
        else:
            service_list = unique_services[0] if unique_services else "AWS services"

        return (
            f"I've designed a {len(services)}-service architecture using {service_list}. "
            f"Estimated cost: {cost} per month. "
            f"{rationale[:200] if rationale else ''} "
            f"Ready to build this in your AWS Console?"
        )

    def generate_cloudformation(self, architecture: dict) -> str:
        """Use Nova 2 Lite to convert an architecture JSON into a CloudFormation YAML."""
        prompt = f"""Convert this AWS architecture JSON into a valid CloudFormation YAML template.
Include all resources, IAM roles with least-privilege permissions, and Outputs.
Architecture:
{json.dumps(architecture, indent=2)}

Return only valid YAML, no explanation, no markdown fences."""
        logger.info("Generating CloudFormation template via Nova 2 Lite")
        return self._invoke(prompt)

    def _invoke(self, user_message: str) -> str:
        """Call Nova 2 Lite via Bedrock."""
        body = {
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": [
                {"role": "user", "content": [{"text": user_message}]}
            ],
            "inferenceConfig": {
                "maxTokens": 2000,
                "temperature": 0.3,
            }
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result["output"]["message"]["content"][0]["text"]

    def _parse_json(self, text: str) -> dict:
        """Safely parse JSON from Nova's response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed — returning fallback structure")
            return {
                "services": [],
                "diagram": "Could not parse architecture",
                "estimated_cost": "Unknown",
                "rationale": text[:500],
                "clarifying_questions": [],
                "error": "JSON parse failed",
            }


# ─── DEMO FALLBACK (used when no real AWS credentials are available) ──────────

_demo_uid = _uid()

DEMO_ARCHITECTURE = {
    "services": [
        {
            "name": f"Image Storage Bucket-{_demo_uid}",
            "aws_service": "S3",
            "action": "Create S3 bucket with private ACL and versioning enabled",
            "aws_console_url": "https://console.aws.amazon.com/s3/home",
            "config": {
                "bucket_name": f"nova-architect-images-{_demo_uid}",
                "versioning": True,
                "public_access": False,
            },
            "depends_on": [],
        },
        {
            "name": f"Metadata Table-{_demo_uid}",
            "aws_service": "DynamoDB",
            "action": "Create DynamoDB table with on-demand billing",
            "aws_console_url": "https://console.aws.amazon.com/dynamodbv2/home",
            "config": {
                "table_name": f"nova-architect-metadata-{_demo_uid}",
                "partition_key": "imageId",
                "billing_mode": "PAY_PER_REQUEST",
            },
            "depends_on": [],
        },
        {
            "name": f"Image Processor-{_demo_uid}",
            "aws_service": "Lambda",
            "aws_console_url": "https://console.aws.amazon.com/lambda/home",
            "action": "Create Lambda function with S3 trigger and DynamoDB write permissions",
            "config": {
                "function_name": f"nova-architect-processor-{_demo_uid}",
                "runtime": "python3.12",
                "memory_mb": 512,
                "timeout_seconds": 30,
            },
            "depends_on": [f"Image Storage Bucket-{_demo_uid}", f"Metadata Table-{_demo_uid}"],
        },
        {
            "name": f"REST API-{_demo_uid}",
            "aws_service": "API Gateway",
            "aws_console_url": "https://console.aws.amazon.com/apigateway/main/apis",
            "action": "Create HTTP API Gateway with Lambda proxy integration",
            "config": {
                "api_name": f"nova-architect-api-{_demo_uid}",
                "type": "HTTP",
                "routes": ["POST /upload", "GET /images/{id}"],
            },
            "depends_on": [f"Image Processor-{_demo_uid}"],
        },
    ],
    "diagram": """
  Client
    │
    ▼
┌─────────────────┐
│   API Gateway   │
│  (HTTP API)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐       ┌─────────────────┐
│    Lambda       │──────▶│    DynamoDB     │
│  (Processor)   │       │  (Metadata)     │
└────────┬────────┘       └─────────────────┘
         │
         ▼
┌─────────────────┐
│       S3        │
│  (Image Store) │
└─────────────────┘
    """,
    "estimated_cost": "$4.20/month at 10,000 requests",
    "rationale": (
        "Serverless architecture scales to zero when idle. "
        "S3 for durable image storage, DynamoDB for fast metadata lookups, "
        "Lambda for processing, API Gateway as the entry point."
    ),
    "clarifying_questions": [
        "Should images be accessible publicly via direct URLs or private with signed URLs?"
    ],
}
