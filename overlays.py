from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pygame

Color = Tuple[int, int, int, int]


@dataclass
class GridStyle:
    name: str


class GridOverlay:
    """Draw switchable composition grids with thin semi-transparent lines."""

    def __init__(self) -> None:
        self.styles = [
            GridStyle("thirds"),
            GridStyle("golden"),
            GridStyle("diagonals"),
            GridStyle("dense-6x6"),
            GridStyle("crop-guides"),
        ]
        self.index = 0
        self.enabled = True
        self.color = (255, 255, 255, 128)

    @property
    def current(self) -> str:
        return self.styles[self.index].name

    def cycle(self) -> None:
        self.index = (self.index + 1) % len(self.styles)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        if not self.enabled:
            return
        layer = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        style = self.current
        if style == "thirds":
            self._draw_regular_grid(layer, 3, 3)
        elif style == "golden":
            self._draw_golden(layer)
        elif style == "diagonals":
            self._draw_diagonals(layer)
        elif style == "dense-6x6":
            self._draw_regular_grid(layer, 6, 6)
        elif style == "crop-guides":
            self._draw_crop_guides(layer)
        surface.blit(layer, rect.topleft)

    def _draw_regular_grid(self, surf: pygame.Surface, cols: int, rows: int) -> None:
        w, h = surf.get_size()
        for c in range(1, cols):
            x = int(w * c / cols)
            pygame.draw.line(surf, self.color, (x, 0), (x, h), 1)
        for r in range(1, rows):
            y = int(h * r / rows)
            pygame.draw.line(surf, self.color, (0, y), (w, y), 1)

    def _draw_diagonals(self, surf: pygame.Surface) -> None:
        w, h = surf.get_size()
        pygame.draw.line(surf, self.color, (0, 0), (w, h), 1)
        pygame.draw.line(surf, self.color, (w, 0), (0, h), 1)

    def _draw_crop_guides(self, surf: pygame.Surface) -> None:
        w, h = surf.get_size()
        for rw, rh in [(16, 9), (4, 3), (1, 1)]:
            if w / h > rw / rh:
                box_h = h
                box_w = int(h * rw / rh)
            else:
                box_w = w
                box_h = int(w * rh / rw)
            x = (w - box_w) // 2
            y = (h - box_h) // 2
            pygame.draw.rect(surf, self.color, pygame.Rect(x, y, box_w, box_h), 1, border_radius=3)

    def _draw_golden(self, surf: pygame.Surface) -> None:
        w, h = surf.get_size()
        phi = 0.618
        x = int(w * phi)
        y = int(h * phi)
        pygame.draw.line(surf, self.color, (x, 0), (x, h), 1)
        pygame.draw.line(surf, self.color, (0, y), (w, y), 1)
        center = (x, y)
        max_r = min(w, h) // 2
        points: List[Tuple[int, int]] = []
        for i in range(100):
            t = i / 99 * 4 * math.pi
            r = max_r * (i / 99)
            px = int(center[0] + math.cos(t) * r * 0.6)
            py = int(center[1] + math.sin(t) * r * 0.6)
            points.append((px, py))
        if len(points) > 1:
            pygame.draw.lines(surf, self.color, False, points, 1)


class HistogramOverlay:
    """Small live histogram with throttled updates for Raspberry Pi."""

    def __init__(self, interval_s: float = 0.5) -> None:
        self.interval_s = interval_s
        self.last_update = 0.0
        self.rgb_bins = [np.zeros(64), np.zeros(64), np.zeros(64)]

    def update(self, frame: np.ndarray) -> None:
        now = time.time()
        if now - self.last_update < self.interval_s:
            return
        small = frame[::4, ::4, :]
        for channel in range(3):
            hist, _ = np.histogram(small[:, :, channel], bins=64, range=(0, 255))
            self.rgb_bins[channel] = hist.astype(np.float32)
        self.last_update = now

    def draw(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        panel.fill((12, 12, 12, 170))
        pygame.draw.rect(panel, (140, 140, 140, 180), panel.get_rect(), 1, border_radius=10)

        max_val = max(float(np.max(ch)) for ch in self.rgb_bins) or 1.0
        for c, color in enumerate([(255, 90, 90), (90, 255, 120), (90, 150, 255)]):
            pts = []
            bins = self.rgb_bins[c]
            for i, val in enumerate(bins):
                x = int(i / (len(bins) - 1) * (rect.width - 10)) + 5
                y = rect.height - 5 - int((val / max_val) * (rect.height - 15))
                pts.append((x, y))
            if len(pts) > 1:
                pygame.draw.lines(panel, color, False, pts, 1)
        surface.blit(panel, rect.topleft)
