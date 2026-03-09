# ⚡ Nova Architect

**Build AWS infrastructure from plain English.**

Describe your application. Nova designs the architecture. Nova Act physically 
builds it in your AWS Console — live, in real-time.

---

## Install in 30 seconds

```bash
pip install nova-architect
nova-architect setup
nova-architect start
```

Your browser opens. You start building.

---

## Demo

> *"A photo sharing API with S3 image storage, Lambda processing, and DynamoDB metadata"*

Nova Architect:
1. **Designs** the optimal serverless AWS architecture (Nova 2 Lite)
2. **Explains** it aloud and asks for approval (Nova 2 Sonic)
3. **Builds it live** — Nova Act physically navigates your AWS Console
4. **Streams screenshots** of every click to your dashboard

4 services. Real AWS account. Under 5 minutes.

---

## Prerequisites

| Requirement | Where |
|---|---|
| Python 3.11+ | python.org |
| AWS Account + IAM credentials | AWS Console → IAM → Security credentials |
| Nova Act API key | nova.amazon.com/act → Developer Tools |
| Bedrock Nova model access | AWS Console → Bedrock → Model access |

---

## Commands

```bash
nova-architect setup      # Interactive setup (run once)
nova-architect start      # Start the dashboard
nova-architect doctor     # Diagnose issues
nova-architect reset      # Clean up AWS resources
nova-architect upgrade    # Update to latest version
nova-architect version    # Show version
```

### Start options

```bash
nova-architect start --port 9000      # Custom port
nova-architect start --no-browser     # Don't auto-open browser
nova-architect start --headless       # Nova Act without visible browser
nova-architect start --demo           # Demo mode, no real AWS calls
```

---

## How It Works

```
You (text / voice / diagram)
        │
        ▼
  Nova 2 Lite ──── Designs optimal serverless architecture  
        │
        ▼
  Nova 2 Sonic ─── Presents design aloud, listens for approval
        │
        ▼
  Nova Act ──────── Opens Chromium, navigates AWS Console live
                    Creates every service. Streams screenshots.
```

**Nova Pro** reads hand-drawn architecture diagrams and whiteboard sketches.

---

## Supported AWS Services

S3 · Lambda · DynamoDB · API Gateway · SQS · SNS · Cognito · EventBridge · IAM

---

## Privacy

Your AWS credentials are stored locally in `~/.nova-architect/config.json`.
They are never sent to any Nova Architect server — there is no Nova Architect server.
Everything runs on your machine, in your AWS account.

---

## Docker

```bash
docker run -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e AWS_REGION=us-east-1 \
  -e NOVA_ACT_API_KEY=your_nova_act_key \
  -e NOVA_ACT_HEADLESS=true \
  novaarchitect/nova-architect:latest
```

---

## License

MIT — *Built with Amazon Nova 2 Lite · Nova Act · Nova 2 Sonic · Nova Pro*
