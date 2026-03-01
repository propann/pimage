from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List


class MenuItem(str, Enum):
    CAPTURE = "capture"
    GALLERY = "gallery"
    ISO = "iso"
    SHUTTER = "shutter"
    AWB = "awb"
    EXPOSURE = "exposure"
    CONTRAST = "contrast"
    SATURATION = "saturation"
    QUIT = "quit"


@dataclass
class CameraSetting:
    key: str
    value: int
    minimum: int
    maximum: int
    step: int = 1

    def bump(self, delta: int) -> int:
        self.value = max(self.minimum, min(self.maximum, self.value + (delta * self.step)))
        return self.value


@dataclass
class CameraProfile:
    name: str = "freelance-default"
    settings: Dict[MenuItem, CameraSetting] = field(default_factory=dict)

    @classmethod
    def defaults(cls) -> "CameraProfile":
        return cls(
            settings={
                MenuItem.ISO: CameraSetting("iso", 200, 100, 800, 100),
                MenuItem.SHUTTER: CameraSetting("shutter", 0, 0, 20000, 500),
                MenuItem.EXPOSURE: CameraSetting("exposure", 0, -10, 10, 1),
                MenuItem.CONTRAST: CameraSetting("contrast", 0, -20, 20, 1),
                MenuItem.SATURATION: CameraSetting("saturation", 0, -20, 20, 1),
            }
        )


@dataclass
class CaptureResult:
    path: Path
    success: bool


MENU_FLOW: List[MenuItem] = [
    MenuItem.CAPTURE,
    MenuItem.GALLERY,
    MenuItem.ISO,
    MenuItem.SHUTTER,
    MenuItem.AWB,
    MenuItem.EXPOSURE,
    MenuItem.CONTRAST,
    MenuItem.SATURATION,
    MenuItem.QUIT,
]
