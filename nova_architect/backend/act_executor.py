"""
Nova Architect — Nova Act Executor
Uses Nova Act to physically navigate the AWS Console and create services.
Includes window activation, live screenshot streaming, retry logic, and
graceful handling of "already exists" errors.
"""

import asyncio
import base64
import os
import contextlib
import json
import time
import logging
import urllib.parse
import urllib.request
import boto3
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from nova_act import NovaAct, ActError, Workflow
    from nova_act.types.workflow import set_current_workflow, get_current_workflow
    NOVA_ACT_AVAILABLE = True
except ImportError:
    NOVA_ACT_AVAILABLE = False
    logger.warning("nova-act not installed. Using demo mode.")

AWS_CONSOLE_BASE = "https://console.aws.amazon.com"

# Already-exists phrases that mean the resource is there and we can skip
ALREADY_EXISTS_PHRASES = [
    "already exists",
    "already taken",
    "bucket already exists",
    "already in use",
    "name is already",
]

SERVICE_HANDLERS = {
    "S3": "_create_s3_bucket",
    "Lambda": "_create_lambda_function",
    "DynamoDB": "_create_dynamodb_table",
    "API Gateway": "_create_api_gateway",
    "SQS": "_create_sqs_queue",
    "SNS": "_create_sns_topic",
    "IAM": "_create_iam_role",
    "EventBridge": "_create_eventbridge_rule",
    "Cognito": "_create_cognito_user_pool",
}


class ActExecutor:
    def __init__(self):
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.headless = os.getenv("NOVA_ACT_HEADLESS", "false").lower() == "true"
        self.demo_mode = False

        # Callbacks for streaming
        self.on_screenshot: Optional[Callable] = None
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None

    def _workflow(self):
        return Workflow(
            model_id="nova-act-latest",
            workflow_definition_name="default",
            boto_session_kwargs={"region_name": self.aws_region}
        )

    @contextlib.contextmanager
    def _workflow_context(self):
        with self._workflow() as wf:
            outer = get_current_workflow()
            set_current_workflow(wf)
            try:
                yield wf
            finally:
                set_current_workflow(outer)

    def _get_federated_url(self, destination: str) -> str:
        """Exchanges IAM credentials for an AWS Console federated sign-in URL."""
        sts = boto3.client('sts', region_name=self.aws_region)
        try:
            federation = sts.get_federation_token(
                Name="NovaArchitectSession",
                Policy=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]
                }),
                DurationSeconds=3600
            )
            creds = federation['Credentials']
            session_json = json.dumps({
                "sessionId": creds['AccessKeyId'],
                "sessionKey": creds['SecretAccessKey'],
                "sessionToken": creds['SessionToken']
            })

            quote_session = urllib.parse.quote_plus(session_json)
            req = urllib.request.Request(
                f"https://signin.aws.amazon.com/federation?Action=getSigninToken&Session={quote_session}"
            )

            with urllib.request.urlopen(req) as response:
                signin_token = json.loads(response.read().decode())['SigninToken']

            quote_destination = urllib.parse.quote_plus(destination)
            return (
                f"https://signin.aws.amazon.com/federation?Action=login"
                f"&Issuer=NovaArchitect&Destination={quote_destination}&SigninToken={signin_token}"
            )
        except Exception as e:
            logger.warning(f"Federation failed ({e}). Falling back to direct URL.")
            return destination

    @contextlib.contextmanager
    def _act(self, url: str):
        """Create a NovaAct instance. Uses AWS IAM credentials for console access."""
        os.environ.pop("NOVA_ACT_API_KEY", None)
        federated_url = self._get_federated_url(url)

        agent = NovaAct(starting_page="about:blank", headless=self.headless, go_to_url_timeout=120)

        with agent:
            # Force the browser to the front on Windows so judges can see it
            if not self.headless:
                import subprocess
                subprocess.Popen(
                    ['powershell', '-command',
                     'try { '
                     '  Add-Type -AssemblyName Microsoft.VisualBasic; '
                     '  $p = Get-Process -Name chrome,chromium -ErrorAction SilentlyContinue | Select-Object -First 1; '
                     '  if ($p) { [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id) } '
                     '} catch {}'],
                    shell=True
                )

            try:
                agent.page.goto(federated_url, timeout=120000)
            except Exception as e:
                logger.warning(f"Navigation to federated URL failed: {e}")

            yield agent

    # ── Public API ─────────────────────────────────────────────────────────────

    async def create_service(self, service: dict) -> dict:
        """Create a single AWS service via Nova Act."""
        aws_service = service.get("aws_service", "")
        handler_name = SERVICE_HANDLERS.get(aws_service)

        if self.demo_mode:
            return await self._demo_create_service(service)

        handler = getattr(self, handler_name, None) if handler_name else None

        if not handler:
            logger.info(f"No native handler for {aws_service}. Using generic AI pilot.")
            handler = self._generic_handler

        try:
            self.main_loop = asyncio.get_running_loop()
            return await asyncio.to_thread(self._run_sync_with_loop, handler, service)
        except Exception as e:
            logger.error(f"Nova Act error for {aws_service}: {e}")
            return {"success": False, "details": f"Nova Act error: {str(e)}", "screenshot_b64": ""}

    async def create_service_with_retry(self, service: dict, max_retries: int = 2) -> dict:
        """Retry wrapper — attempts up to max_retries+1 times before giving up."""
        last_result = {}
        for attempt in range(max_retries + 1):
            result = await self.create_service(service)
            last_result = result
            if result.get("success"):
                return result
            if attempt < max_retries:
                logger.info(
                    f"Service {service.get('name')} failed (attempt {attempt+1}/{max_retries+1}). "
                    f"Retrying in 2s..."
                )
                await asyncio.sleep(2)
        logger.warning(f"Service {service.get('name')} failed after {max_retries+1} attempts.")
        return last_result

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _check_already_exists(self, details: str) -> bool:
        """Returns True if error text indicates the resource already exists."""
        lower = details.lower()
        return any(phrase in lower for phrase in ALREADY_EXISTS_PHRASES)

    def _make_result(self, success: bool, details: str, screenshot_b64: str = "") -> dict:
        """
        Build a result dict. Converts "already exists" failures into soft successes.
        """
        if not success and self._check_already_exists(details):
            logger.info(f"Treating 'already exists' as success: {details[:80]}")
            return {
                "success": True,
                "details": details + " (already existed — skipped)",
                "screenshot_b64": screenshot_b64,
            }
        return {"success": success, "details": details, "screenshot_b64": screenshot_b64}

    def _run_sync_with_loop(self, handler, service):
        """Sets up a thread-local event loop required by Playwright before executing the handler."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return handler(service)

    def _screenshot(self, agent) -> str:
        try:
            screenshot_bytes = agent.page.screenshot(type="jpeg", quality=60)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            if getattr(self, "on_screenshot", None) and getattr(self, "main_loop", None):
                asyncio.run_coroutine_threadsafe(self.on_screenshot(b64), self.main_loop)

            return b64
        except Exception as e:
            logger.warning(f"Screenshot error: {e}")
            return ""

    # ── Generic (LLM-driven) handler ────────────────────────────────────────────

    def _generic_handler(self, service: dict) -> dict:
        """Dynamically create ANY AWS service using the LLM's provided URL and Action steps."""
        service_name = service.get("name", "Custom Service")
        aws_service = service.get("aws_service", "Unknown AWS Service")
        action_steps = service.get("action", f"Find and create {service_name}")
        target_url = service.get("aws_console_url", f"{AWS_CONSOLE_BASE}/console/home?region={self.aws_region}")

        try:
            with self._workflow_context():
                with self._act(target_url) as agent:
                    agent.act(f"""
                        {action_steps}
                        Wait for the success confirmation on the screen.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(
                True,
                f"✅ {aws_service} '{service_name}' provisioned successfully via AI pilot",
                screenshot_b64
            )
        except Exception as e:
            details = str(e)
            return self._make_result(False, f"❌ {aws_service} '{service_name}' failed: {details}")

    # ── Hardcoded service handlers ──────────────────────────────────────────────

    def _create_s3_bucket(self, service: dict) -> dict:
        config = service.get("config", {})
        bucket_name = config.get("bucket_name", f"nova-architect-{int(time.time())}")
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/s3/") as agent:
                    agent.act(f"""
                        Click "Create bucket".
                        In the Bucket name field, type: {bucket_name}
                        Ensure region is {self.aws_region}.
                        Scroll down and click "Create bucket".
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"S3 bucket '{bucket_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_dynamodb_table(self, service: dict) -> dict:
        config = service.get("config", {})
        table_name = config.get("table_name", "nova-architect-table")
        partition_key = config.get("partition_key", "id")
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/dynamodbv2/home?region={self.aws_region}#tables") as agent:
                    agent.act(f"""
                        Click "Create table".
                        Type table name: {table_name}
                        Type partition key: {partition_key}
                        Select "On-demand" capacity mode.
                        Click "Create table".
                        Wait for success.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"DynamoDB table '{table_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_lambda_function(self, service: dict) -> dict:
        config = service.get("config", {})
        function_name = config.get("function_name", "nova-architect-function")
        runtime = config.get("runtime", "python3.12")   # default is now python3.12
        memory = config.get("memory_mb", 128)
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/lambda/home?region={self.aws_region}#/functions") as agent:
                    agent.act(f"""
                        Click "Create function".
                        Select "Author from scratch".
                        Type function name: {function_name}
                        Open the Runtime dropdown and select: {runtime}
                        Click "Create function".
                        After creation, go to Configuration > General configuration > Edit.
                        Set Memory to {memory} MB and Save.
                        Wait for the save confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(
                True, f"Lambda '{function_name}' created ({runtime}, {memory}MB)", screenshot_b64
            )
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_api_gateway(self, service: dict) -> dict:
        config = service.get("config", {})
        api_name = config.get("api_name", "nova-architect-api")
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/apigateway/main/apis?region={self.aws_region}") as agent:
                    agent.act(f"""
                        Click "Create API".
                        Under HTTP API, click "Build".
                        Type API name: {api_name}
                        Click Next, Next, Next, then Create.
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"API Gateway '{api_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_sqs_queue(self, service: dict) -> dict:
        config = service.get("config", {})
        queue_name = config.get("queue_name", f"nova-queue-{int(time.time())}")
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/sqs/v3/home?region={self.aws_region}#/queues") as agent:
                    agent.act(f"""
                        Click "Create queue".
                        Select Standard type.
                        In the Name field, type: {queue_name}
                        Scroll down and click "Create queue".
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"✅ SQS queue '{queue_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_sns_topic(self, service: dict) -> dict:
        config = service.get("config", {})
        topic_name = config.get("topic_name", f"nova-topic-{int(time.time())}")
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/sns/v3/home?region={self.aws_region}#/topics") as agent:
                    agent.act(f"""
                        Click "Create topic".
                        Select Standard type.
                        In the Name field, type: {topic_name}
                        Scroll down and click "Create topic".
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"✅ SNS topic '{topic_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_iam_role(self, service: dict) -> dict:
        config = service.get("config", {})
        role_name = config.get("role_name", "nova-architect-role")
        try:
            with self._workflow_context():
                with self._act(f"{AWS_CONSOLE_BASE}/iamv2/home?region={self.aws_region}#/roles") as agent:
                    agent.act(f"""
                        Click "Create role".
                        Select AWS service as trusted entity.
                        Select Lambda as the service.
                        Click Next: Permissions, Next: Tags, Next: Review.
                        Type role name: {role_name}
                        Click "Create role".
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"IAM role '{role_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_eventbridge_rule(self, service: dict) -> dict:
        config = service.get("config", {})
        rule_name = config.get("rule_name", f"nova-rule-{int(time.time())}")
        try:
            with self._workflow_context():
                with self._act(
                    f"{AWS_CONSOLE_BASE}/events/home?region={self.aws_region}#/rules"
                ) as agent:
                    agent.act(f"""
                        Click "Create rule".
                        Type rule name: {rule_name}
                        Select "Schedule" as the rule type.
                        Enter a schedule expression: rate(1 hour)
                        Click Next and continue through to Create rule.
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"✅ EventBridge rule '{rule_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    def _create_cognito_user_pool(self, service: dict) -> dict:
        config = service.get("config", {})
        pool_name = config.get("pool_name", f"nova-pool-{int(time.time())}")
        try:
            with self._workflow_context():
                with self._act(
                    f"{AWS_CONSOLE_BASE}/cognito/v2/idp/user-pools?region={self.aws_region}"
                ) as agent:
                    agent.act(f"""
                        Click "Create user pool".
                        Select Email as the sign-in option.
                        Click Next through all pages using defaults.
                        Set user pool name to: {pool_name}
                        Click "Create user pool".
                        Wait for success confirmation.
                    """)
                    screenshot_b64 = self._screenshot(agent)
            return self._make_result(True, f"✅ Cognito user pool '{pool_name}' created", screenshot_b64)
        except Exception as e:
            return self._make_result(False, str(e))

    # ── Demo mode ───────────────────────────────────────────────────────────────

    async def _demo_create_service(self, service: dict) -> dict:
        """Simulated execution for testing without real AWS Console automation."""
        await asyncio.sleep(1.5)
        aws_service = service.get("aws_service", "Unknown")
        config = service.get("config", {})
        details_map = {
            "S3": f"S3 bucket '{config.get('bucket_name', 'demo-bucket')}' created",
            "DynamoDB": f"DynamoDB table '{config.get('table_name', 'demo-table')}' created",
            "Lambda": f"Lambda '{config.get('function_name', 'demo-fn')}' created",
            "API Gateway": f"API Gateway '{config.get('api_name', 'demo-api')}' created",
            "SQS": f"SQS queue '{config.get('queue_name', 'demo-queue')}' created",
            "SNS": f"SNS topic '{config.get('topic_name', 'demo-topic')}' created",
            "IAM": f"IAM role '{config.get('role_name', 'demo-role')}' created",
            "EventBridge": f"EventBridge rule '{config.get('rule_name', 'demo-rule')}' created",
            "Cognito": f"Cognito user pool '{config.get('pool_name', 'demo-pool')}' created",
        }
        return {
            "success": True,
            "details": details_map.get(aws_service, f"{aws_service} created successfully"),
            "screenshot_b64": "",
            "demo_mode": True,
        }