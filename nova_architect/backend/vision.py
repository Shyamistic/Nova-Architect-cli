"""
Nova Architect — Vision Agent
Uses Amazon Nova Pro (multimodal) via Bedrock to read architecture diagrams,
whiteboard sketches, and screenshots
"""

import json
import boto3
import base64
import os


VISION_PROMPT = """You are analyzing an architecture diagram, whiteboard sketch, 
or technical drawing. Extract all the information needed to build this on AWS.

Return JSON with:
{
  "summary": "one sentence describing the overall architecture",
  "services_detected": [
    {
      "type": "what kind of service (database, API, storage, compute, queue, etc)",
      "aws_equivalent": "the best AWS service for this",
      "label": "label from the diagram if visible",
      "connections": ["list of other service labels this connects to"]
    }
  ],
  "data_flow": "describe how data flows through the system",
  "special_requirements": ["any special requirements visible in the diagram"],
  "confidence": 0.0-1.0
}

If this is not an architecture diagram, return:
{"error": "Not an architecture diagram", "confidence": 0.0}

Output valid JSON only."""


class VisionAgent:

    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        # Nova Pro supports multimodal (images + text)
        self.model_id = "amazon.nova-pro-v1:0"

    async def read_architecture_diagram(self, image_b64: str) -> dict:
        """
        Analyze an architecture diagram image and extract service information.
        image_b64: base64-encoded image (PNG or JPEG)
        """
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "png",
                                "source": {
                                    "bytes": image_b64
                                }
                            }
                        },
                        {
                            "text": VISION_PROMPT
                        }
                    ]
                }
            ],
            "inferenceConfig": {
                "maxTokens": 1500,
                "temperature": 0.2,
            }
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        text = result["output"]["message"]["content"][0]["text"]
        return self._parse_json(text)

    async def analyze_cloudwatch_screenshot(self, screenshot_b64: str) -> dict:
        """
        Analyze a CloudWatch dashboard screenshot for anomalies.
        Used by the monitoring/prediction flow.
        """
        prompt = """Analyze this AWS CloudWatch dashboard screenshot.
        
Return JSON with:
{
  "metrics_visible": ["list of metric names visible"],
  "concerning_trends": ["describe any metrics with upward/downward concerning trends"],
  "warning_indicators": ["any orange/red warning states visible"],
  "overall_health": "healthy | degrading | critical",
  "confidence": 0.0-1.0
}

Output valid JSON only."""

        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "png",
                                "source": {"bytes": screenshot_b64}
                            }
                        },
                        {"text": prompt}
                    ]
                }
            ],
            "inferenceConfig": {"maxTokens": 800, "temperature": 0.1}
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        text = result["output"]["message"]["content"][0]["text"]
        return self._parse_json(text)

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "error": "Failed to parse vision response",
                "raw": text[:300],
                "confidence": 0.0,
            }


# ─── DEMO FALLBACK ────────────────────────────────────────────────────────────

DEMO_VISION_RESULT = {
    "summary": "A three-tier web application with frontend, API layer, and data storage",
    "services_detected": [
        {
            "type": "API / entry point",
            "aws_equivalent": "API Gateway",
            "label": "API",
            "connections": ["Backend Service"]
        },
        {
            "type": "compute / backend logic",
            "aws_equivalent": "Lambda",
            "label": "Backend Service",
            "connections": ["Database", "Cache"]
        },
        {
            "type": "relational database",
            "aws_equivalent": "DynamoDB",
            "label": "Database",
            "connections": []
        },
        {
            "type": "file storage",
            "aws_equivalent": "S3",
            "label": "Storage",
            "connections": ["Backend Service"]
        }
    ],
    "data_flow": "Client calls API Gateway → Lambda processes request → reads/writes DynamoDB and S3",
    "special_requirements": ["Needs authentication layer", "Files should be private"],
    "confidence": 0.92,
}
