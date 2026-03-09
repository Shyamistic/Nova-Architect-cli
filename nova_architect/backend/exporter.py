"""
Nova Architect — CloudFormation Exporter
Converts an architecture JSON into a CloudFormation YAML template via Nova 2 Lite.
"""

import logging
import json
import os
import boto3

logger = logging.getLogger(__name__)

CF_SYSTEM_PROMPT = (
    "You are an expert AWS CloudFormation author. When given an architecture JSON, "
    "output ONLY a valid CloudFormation YAML template — no markdown, no explanation, "
    "no code fences. Include all Resources, appropriate IAM roles using least-privilege, "
    "and a well-formed Outputs section."
)


class CloudFormationExporter:

    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        self.model_id = "amazon.nova-lite-v1:0"

    def export(self, architecture: dict) -> str:
        """Generate a CloudFormation YAML string from an architecture dict."""
        prompt = (
            f"Convert this AWS architecture JSON into a valid CloudFormation YAML template.\n"
            f"Include all resources, IAM roles with least-privilege permissions, and Outputs.\n\n"
            f"Architecture:\n{json.dumps(architecture, indent=2)}\n\n"
            f"Return only valid YAML, no explanation."
        )

        body = {
            "system": [{"text": CF_SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 3000, "temperature": 0.1},
        }

        logger.info("Generating CloudFormation template")
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        yaml_text = result["output"]["message"]["content"][0]["text"].strip()

        # Strip accidental fences
        if yaml_text.startswith("```"):
            lines = yaml_text.split("\n")
            yaml_text = "\n".join(lines[1:-1])

        return yaml_text
