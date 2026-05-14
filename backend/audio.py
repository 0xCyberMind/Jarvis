from typing import Dict


class AudioPipeline:
    def transcribe(self, _raw_audio: bytes) -> str:
        return "[voice transcription placeholder]"

    def synthesize(self, text: str) -> Dict[str, str]:
        return {"status": "ok", "text": text}
