"""
Nova Architect — Voice Handler
Uses Amazon Nova 2 Sonic for real-time text-to-speech and speech-to-text.
Nova Sonic supports bidirectional streaming for natural conversation.
"""

import asyncio
import base64
import json
import os
import boto3
from typing import Optional


class VoiceHandler:

    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        self.model_id = "amazon.nova-sonic-v1:0"
        self.voice_id = os.getenv("NOVA_SONIC_VOICE", "matthew")  # AWS Polly-style voice

    async def speak(self, text: str) -> str:
        """
        Convert text to speech using Amazon Polly (neural).
        Nova Sonic uses a bidirectional streaming API for real-time voice —
        for the demo TTS we use Polly which is simpler and more reliable.
        Returns base64-encoded audio bytes (MP3).
        """
        try:
            polly = boto3.client(
                "polly",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            )
            response = polly.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId="Matthew",
                Engine="neural",
            )
            audio_bytes = response["AudioStream"].read()
            return base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            print(f"Polly TTS error: {e}")
            return ""

    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe speech to text using Nova 2 Sonic.
        audio_bytes: raw audio bytes (PCM 16-bit, 16kHz recommended)
        Returns transcribed text string.
        """
        try:
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "inputAudio": audio_b64,
                    "audioConfig": {
                        "mediaType": "audio/pcm",
                        "sampleRateHertz": 16000,
                    }
                }),
                contentType="application/json",
                accept="application/json",
            )

            result = json.loads(response["body"].read())
            return result.get("transcription", "")

        except Exception as e:
            print(f"Nova Sonic STT error: {e}")
            return ""

    async def converse(self, audio_bytes: bytes, context: str = "") -> dict:
        """
        Full bidirectional: audio in → response text + audio out.
        Used for the approval flow: engineer speaks, Nova responds.
        Returns: { transcription, response_text, response_audio_b64 }
        """
        # First transcribe
        transcription = await self.transcribe(audio_bytes)

        if not transcription:
            return {
                "transcription": "",
                "response_text": "I didn't catch that. Could you say that again?",
                "response_audio_b64": await self.speak("I didn't catch that. Could you say that again?"),
            }

        # Check for approval/denial keywords
        lower = transcription.lower()
        if any(word in lower for word in ["approve", "yes", "build it", "go ahead", "do it", "confirm"]):
            response_text = "Approved. Starting build now."
        elif any(word in lower for word in ["deny", "no", "cancel", "stop", "wait"]):
            response_text = "Understood. Build cancelled. Let me know when you're ready."
        else:
            response_text = f"I heard: {transcription}. Say 'approve' to build or 'cancel' to stop."

        response_audio = await self.speak(response_text)

        return {
            "transcription": transcription,
            "response_text": response_text,
            "response_audio_b64": response_audio,
            "action": "approve" if "Approved" in response_text else
                      "deny" if "cancelled" in response_text else "unclear",
        }


# ─── POLLY FALLBACK ───────────────────────────────────────────────────────────
# If Nova Sonic is unavailable, fall back to Amazon Polly for TTS

class PollyFallback:
    """Amazon Polly TTS as fallback when Nova Sonic is unavailable."""

    def __init__(self):
        self.client = boto3.client(
            "polly",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )

    async def speak(self, text: str) -> str:
        try:
            response = self.client.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId="Matthew",
                Engine="neural",
            )
            audio_bytes = response["AudioStream"].read()
            return base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            print(f"Polly fallback error: {e}")
            return ""

    async def transcribe(self, audio_bytes: bytes) -> str:
        # Polly doesn't do STT — would need Amazon Transcribe here
        return ""