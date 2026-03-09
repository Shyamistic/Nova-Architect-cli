"""
Nova Architect — Main Orchestration Server
FastAPI backend with WebSocket for real-time frontend updates.
"""

import asyncio
import json
import base64
import time
import logging
import re
import os
from collections import defaultdict
from typing import Optional
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path

from architect import ArchitectAgent
from vision import VisionAgent
from act_executor import ActExecutor
from voice_handler import VoiceHandler
from database import init_db, save_build, list_builds, get_build, delete_build, builds_today
from templates import TEMPLATES
from exporter import CloudFormationExporter
from config import settings

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB and validate settings
    init_db()
    warnings = settings.validate()
    for w in warnings:
        logger.warning(w)
    logger.info("Nova Architect v2.0.0 started")
    
    yield
    
    # Shutdown: Close all active WebSockets
    for ws in active_connections:
        try:
            await ws.close()
        except Exception:
            pass
    logger.info("Server shutdown complete")

app = FastAPI(title="Nova Architect", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import nova_architect
_pkg = Path(nova_architect.__file__).parent
app.mount("/static", StaticFiles(directory=str(_pkg / "frontend")), name="static")

# Global agents (initialized once at startup)
architect = ArchitectAgent()
vision = VisionAgent()
act = ActExecutor()
voice = VoiceHandler()
exporter = CloudFormationExporter()

_start_time = time.time()

# ── Rate limiting ──────────────────────────────────────────────────────────────
_request_counts: dict = defaultdict(list)  # IP -> list of timestamps


def check_rate_limit(ip: str, limit: int = 10, window: int = 3600) -> bool:
    """Returns True if allowed, False if rate-limited. 10 builds/hour per IP."""
    now = time.time()
    _request_counts[ip] = [t for t in _request_counts[ip] if now - t < window]
    if len(_request_counts[ip]) >= limit:
        return False
    _request_counts[ip].append(now)
    return True


# ── Input sanitization ─────────────────────────────────────────────────────────
def sanitize_text(text: str, max_len: int = 2000) -> str:
    """Strip HTML tags and truncate."""
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()[:max_len]


def validate_architecture(architecture: dict) -> bool:
    return isinstance(architecture.get("services"), list)


# ── WebSocket connection registry ──────────────────────────────────────────────
active_connections: list[WebSocket] = []


async def broadcast(message: dict):
    for ws in active_connections:
        try:
            await ws.send_json(message)
        except Exception:
            pass


# ── Static routes ──────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    import nova_architect
    _pkg = Path(nova_architect.__file__).parent
    return FileResponse(str(_pkg / "frontend" / "index.html"))


# ── REST API endpoints ─────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    """System health check."""
    nova_act_status = "connected" if act else "unavailable"
    bedrock_status = "connected" if architect else "unavailable"
    return {
        "status": "ok",
        "nova_act": nova_act_status,
        "bedrock": bedrock_status,
        "version": "2.0.0",
        "builds_today": builds_today(),
        "uptime_seconds": round(time.time() - _start_time),
        "region": settings.aws_region,
    }


@app.get("/api/templates")
async def get_templates():
    return {"templates": TEMPLATES}


@app.get("/api/builds")
async def get_builds():
    return {"builds": list_builds(20)}


@app.get("/api/builds/{build_id}")
async def get_build_detail(build_id: str):
    record = get_build(build_id)
    if not record:
        raise HTTPException(status_code=404, detail="Build not found")
    return record


@app.delete("/api/builds/{build_id}")
async def delete_build_record(build_id: str):
    if not delete_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    return {"deleted": build_id}


@app.post("/api/export/cloudformation")
async def export_cloudformation(request: Request):
    body = await request.json()
    architecture = body.get("architecture", {})
    if not validate_architecture(architecture):
        raise HTTPException(status_code=400, detail="Invalid architecture payload")
    try:
        yaml_text = exporter.export(architecture)
    except Exception as e:
        logger.error(f"CloudFormation export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"yaml": yaml_text, "filename": "template.yaml"}


@app.post("/upload-diagram")
async def upload_diagram(file: UploadFile = File(...)):
    """Accept an uploaded architecture diagram image."""
    contents = await file.read()
    image_b64 = base64.b64encode(contents).decode("utf-8")
    vision_result = await vision.read_architecture_diagram(image_b64)
    architecture = await architect.design_from_vision(vision_result)
    return {"vision_result": vision_result, "architecture": architecture}


# ── WebSocket ──────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    await websocket.send_json({"type": "connected", "message": "Nova Architect ready."})
    try:
        while True:
            data = await websocket.receive_json()
            await handle_ws_message(websocket, data)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)


async def handle_ws_message(ws: WebSocket, data: dict):
    """Route incoming WebSocket messages to the right handler."""
    msg_type = data.get("type")

    if msg_type == "text_requirement":
        text = sanitize_text(data.get("text", ""))
        if not text:
            await ws.send_json({"type": "error", "message": "Requirement text is empty."})
            return
        await handle_text_requirement(ws, text)

    elif msg_type == "voice_requirement":
        audio_b64 = data.get("audio_b64", "")
        if not audio_b64:
            return
        if len(audio_b64) > 10 * 1024 * 1024:  # 10MB base64 = ~7.5MB binary
            await ws.send_json({"type": "error", "message": "Audio too large."})
            return
        audio_bytes = base64.b64decode(audio_b64)
        transcription = await voice.transcribe(audio_bytes)
        await ws.send_json({"type": "transcription", "text": transcription})
        await handle_text_requirement(ws, transcription)

    elif msg_type == "approve_build":
        architecture = data.get("architecture", {})
        if not validate_architecture(architecture):
            await ws.send_json({"type": "error", "message": "Invalid architecture payload."})
            return
        # Rate limit by connection (use websocket id as proxy for IP in WS context)
        client_id = str(id(ws))
        if not check_rate_limit(client_id):
            await ws.send_json({
                "type": "error",
                "message": "Rate limit exceeded — 10 builds per hour. Please wait."
            })
            return
        await handle_build_execution(ws, architecture)

    elif msg_type == "deny_build":
        await ws.send_json({"type": "status", "message": "Build cancelled. Ready for new requirements."})

    elif msg_type == "image_requirement":
        image_b64 = data.get("image_b64", "")
        if not image_b64:
            return
        if len(image_b64) > 13_400_000:  # ~10MB of binary encoded as base64
            await ws.send_json({"type": "error", "message": "Image too large (max 10MB)."})
            return
        await handle_image_requirement(ws, image_b64)


# ── Core Orchestration Flows ───────────────────────────────────────────────────
async def handle_text_requirement(ws: WebSocket, requirement: str):
    """Full flow: requirement → architecture design → present to user."""
    if not requirement.strip():
        return

    await ws.send_json({"type": "status", "message": "Analyzing requirements..."})
    await ws.send_json({"type": "thinking", "text": f'"{requirement}"'})

    ack_audio = await voice.speak("Got it. Designing your AWS architecture now. Give me a moment.")
    if ack_audio:
        await ws.send_json({"type": "audio", "audio_b64": ack_audio})

    await ws.send_json({"type": "status", "message": "Nova 2 Lite designing architecture..."})
    architecture = await architect.design(requirement)
    architecture["_requirement"] = requirement  # stash for later DB save

    await ws.send_json({"type": "architecture", "data": architecture})

    summary = architect.summarize_for_voice(architecture)
    summary_audio = await voice.speak(summary)
    if summary_audio:
        await ws.send_json({"type": "audio", "audio_b64": summary_audio})

    approval_text = (
        "Architecture designed. Shall I build this in your AWS Console now? "
        "Say Approve or click the button."
    )
    approval_audio = await voice.speak(approval_text)
    await ws.send_json({"type": "awaiting_approval", "architecture": architecture})
    if approval_audio:
        await ws.send_json({"type": "audio", "audio_b64": approval_audio})


async def handle_image_requirement(ws: WebSocket, image_b64: str):
    """Read an architecture diagram image and build from it."""
    await ws.send_json({"type": "status", "message": "Nova Multimodal reading your diagram..."})

    vision_result = await vision.read_architecture_diagram(image_b64)
    await ws.send_json({"type": "vision_result", "data": vision_result})

    await ws.send_json({"type": "status", "message": "Converting diagram to buildable architecture..."})
    architecture = await architect.design_from_vision(vision_result)
    await ws.send_json({"type": "architecture", "data": architecture})

    audio = await voice.speak(
        f"I can see your diagram. It shows {vision_result.get('summary', 'a cloud architecture')}. "
        f"I've mapped it to AWS services. Ready to build when you are."
    )
    if audio:
        await ws.send_json({"type": "audio", "audio_b64": audio})
    await ws.send_json({"type": "awaiting_approval", "architecture": architecture})


async def handle_build_execution(ws: WebSocket, architecture: dict):
    """Execute the build via Nova Act and persist the results."""
    await ws.send_json({"type": "status", "message": "Starting Nova Act browser automation..."})

    start_audio = await voice.speak(
        "Approved. Opening AWS Console now. Watch me build your architecture."
    )
    if start_audio:
        await ws.send_json({"type": "audio", "audio_b64": start_audio})
    await ws.send_json({"type": "build_started"})

    services = architecture.get("services", [])
    results = []
    build_start = time.time()

    for i, service in enumerate(services):
        await ws.send_json({
            "type": "build_progress",
            "step": i + 1,
            "total": len(services),
            "service": service.get("name"),
            "action": service.get("action"),
            "aws_service": service.get("aws_service"),
        })

        step_audio = await voice.speak(f"Creating {service.get('name')}.")
        if step_audio:
            await ws.send_json({"type": "audio", "audio_b64": step_audio})

        act.on_screenshot = _make_screenshot_callback(ws)
        act.main_loop = asyncio.get_running_loop()

        # Use retry-aware wrapper
        result = await act.create_service_with_retry(service, max_retries=2)
        results.append(result)

        await ws.send_json({
            "type": "build_step_complete",
            "service": service.get("name"),
            "success": result.get("success", False),
            "details": result.get("details", ""),
            "screenshot_b64": result.get("screenshot_b64", ""),
        })

    duration = time.time() - build_start
    success_count = sum(1 for r in results if r.get("success"))
    total = len(results)
    status = "completed" if success_count == total else ("partial" if success_count > 0 else "failed")

    # Persist to build history
    try:
        requirement = architecture.get("_requirement", "Unknown")
        save_build(
            requirement=requirement,
            architecture=architecture,
            status=status,
            success_count=success_count,
            total_count=total,
            duration_seconds=duration,
            services_built=[
                {"service": s.get("name"), "success": r.get("success")}
                for s, r in zip(services, results)
            ],
        )
    except Exception as e:
        logger.warning(f"Failed to save build history: {e}")

    done_audio = await voice.speak(
        f"Build complete. {success_count} of {total} services created successfully. "
        f"Your architecture is live on AWS."
    )
    if done_audio:
        await ws.send_json({"type": "audio", "audio_b64": done_audio})

    await ws.send_json({
        "type": "build_complete",
        "results": results,
        "success_count": success_count,
        "total": total,
        "architecture": architecture,
    })


# ── Screenshot streaming callback ──────────────────────────────────────────────
def _make_screenshot_callback(websocket):
    async def _cb(b64: str):
        try:
            await websocket.send_json({
                "type": "screenshot",
                "screenshot_b64": b64,
            })
        except Exception:
            pass
    return _cb


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
