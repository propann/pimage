from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Tuple

import pygame


@dataclass
class HudCard:
    key: str
    label: str
    value: str
    rect: pygame.Rect


class SlidePanel:
    def __init__(self, side: str, width: int, height: int, duration: float = 0.35) -> None:
        self.side = side
        self.width = width
        self.height = height
        self.duration = duration
        self.visible = True
        self.anim_from = 1.0
        self.anim_to = 1.0
        self.anim_start = 0.0

    def toggle(self) -> None:
        self.visible = not self.visible
        self.anim_from = self.progress()
        self.anim_to = 1.0 if self.visible else 0.0
        self.anim_start = time.time()

    def progress(self) -> float:
        if self.anim_start == 0.0:
            return self.anim_to
        t = min(1.0, (time.time() - self.anim_start) / self.duration)
        eased = 1 - (1 - t) * (1 - t)
        return self.anim_from + (self.anim_to - self.anim_from) * eased

    def x(self, screen_w: int) -> int:
        p = self.progress()
        if self.side == "left":
            return int(-self.width + self.width * p)
        return int(screen_w - self.width * p)


class HudUI:
    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.font = pygame.font.SysFont("DejaVuSans", 20)
        self.small = pygame.font.SysFont("DejaVuSans", 16)
        self.left_panel = SlidePanel("left", 170, screen_h)
        self.right_panel = SlidePanel("right", 220, screen_h)
        self.popup_key = ""
        self.popup_value = 0.0
        self.popup_min = 0.0
        self.popup_max = 1.0
        self.cards: List[HudCard] = []

    def build_cards(self, values: List[Tuple[str, str, str]]) -> List[HudCard]:
        self.cards.clear()
        x = self.screen_w - 212
        y = 18
        for key, label, value in values:
            rect = pygame.Rect(x, y, 194, 56)
            self.cards.append(HudCard(key, label, value, rect))
            y += 64
        return self.cards

    def open_popup(self, key: str, value: float, min_v: float, max_v: float) -> None:
        self.popup_key = key
        self.popup_value = value
        self.popup_min = min_v
        self.popup_max = max_v

    def popup_active(self) -> bool:
        return bool(self.popup_key)

    def draw(self, surface: pygame.Surface, menu_items: List[str], active_menu: int) -> None:
        left_x = self.left_panel.x(self.screen_w)
        right_x = self.right_panel.x(self.screen_w)

        left = pygame.Surface((self.left_panel.width, self.screen_h), pygame.SRCALPHA)
        left.fill((8, 8, 10, 155))
        pygame.draw.rect(left, (110, 110, 120, 170), left.get_rect(), 1, border_radius=12)

        y = 24
        for i, item in enumerate(menu_items):
            btn = pygame.Rect(10, y, self.left_panel.width - 20, 46)
            fill = (50, 80, 120, 180) if i == active_menu else (40, 40, 50, 170)
            pygame.draw.rect(left, fill, btn, border_radius=10)
            left.blit(self.small.render(item, True, (240, 240, 240)), (btn.x + 12, btn.y + 14))
            y += 56
        surface.blit(left, (left_x, 0))

        right = pygame.Surface((self.right_panel.width, self.screen_h), pygame.SRCALPHA)
        right.fill((8, 8, 10, 145))
        pygame.draw.rect(right, (110, 110, 120, 170), right.get_rect(), 1, border_radius=12)
        surface.blit(right, (right_x, 0))

        for card in self.cards:
            draw_rect = card.rect.move(right_x - (self.screen_w - self.right_panel.width), 0)
            pygame.draw.rect(surface, (18, 18, 26, 180), draw_rect, border_radius=11)
            pygame.draw.rect(surface, (135, 135, 160), draw_rect, 1, border_radius=11)
            surface.blit(self.small.render(card.label, True, (210, 210, 215)), (draw_rect.x + 10, draw_rect.y + 8))
            surface.blit(self.font.render(card.value, True, (245, 245, 255)), (draw_rect.x + 10, draw_rect.y + 26))

        if self.popup_active():
            overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            modal = pygame.Rect(self.screen_w // 2 - 180, self.screen_h // 2 - 80, 360, 160)
            pygame.draw.rect(overlay, (20, 20, 30, 230), modal, border_radius=14)
            pygame.draw.rect(overlay, (180, 180, 210), modal, 1, border_radius=14)
            overlay.blit(self.font.render(self.popup_key, True, (240, 240, 250)), (modal.x + 18, modal.y + 16))

            slider = pygame.Rect(modal.x + 22, modal.y + 78, modal.width - 44, 8)
            pygame.draw.rect(overlay, (85, 85, 95), slider, border_radius=4)
            p = 0.0 if self.popup_max == self.popup_min else (self.popup_value - self.popup_min) / (self.popup_max - self.popup_min)
            kx = int(slider.x + p * slider.width)
            pygame.draw.circle(overlay, (220, 220, 240), (kx, slider.y + 4), 10)
            overlay.blit(self.small.render(f"{self.popup_value:.2f}", True, (240, 220, 150)), (modal.x + 18, modal.y + 106))
            surface.blit(overlay, (0, 0))

    def handle_click(self, pos: Tuple[int, int], menu_count: int) -> Tuple[str, int]:
        left_x = self.left_panel.x(self.screen_w)
        right_x = self.right_panel.x(self.screen_w)

        if self.popup_active():
            modal = pygame.Rect(self.screen_w // 2 - 180, self.screen_h // 2 - 80, 360, 160)
            slider = pygame.Rect(modal.x + 22, modal.y + 78, modal.width - 44, 8)
            if slider.inflate(0, 30).collidepoint(pos):
                p = min(1.0, max(0.0, (pos[0] - slider.x) / slider.width))
                self.popup_value = self.popup_min + p * (self.popup_max - self.popup_min)
                return ("popup_adjust", -1)
            self.popup_key = ""
            return ("popup_close", -1)

        y = 24
        for i in range(menu_count):
            btn = pygame.Rect(left_x + 10, y, self.left_panel.width - 20, 46)
            if btn.collidepoint(pos):
                return ("menu", i)
            y += 56

        for card in self.cards:
            draw_rect = card.rect.move(right_x - (self.screen_w - self.right_panel.width), 0)
            if draw_rect.collidepoint(pos):
                return (f"card:{card.key}", -1)

        return ("", -1)
