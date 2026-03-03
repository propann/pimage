from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import CaptureResult


@dataclass
class CameraBackend:
    output_dir: Path

    def start_preview(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def capture(self) -> CaptureResult:
        filename = datetime.now().strftime("IMG_%Y%m%d_%H%M%S.jpg")
        path = self.output_dir / filename
        path.write_text("mock image bytes\n", encoding="utf-8")
        return CaptureResult(path=path, success=True)

    def stop(self) -> None:
        return
