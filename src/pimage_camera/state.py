from dataclasses import dataclass, field

from .models import CameraProfile, MENU_FLOW, MenuItem


@dataclass
class CameraState:
    profile: CameraProfile = field(default_factory=CameraProfile.defaults)
    selected_index: int = 0
    running: bool = True
    last_message: str = "Prêt"

    @property
    def selected_item(self) -> MenuItem:
        return MENU_FLOW[self.selected_index]

    def rotate(self, direction: int) -> MenuItem:
        self.selected_index = (self.selected_index + direction) % len(MENU_FLOW)
        self.last_message = f"Menu: {self.selected_item.value}"
        return self.selected_item

    def click(self) -> MenuItem:
        item = self.selected_item
        if item == MenuItem.QUIT:
            self.running = False
            self.last_message = "Arrêt demandé"
        elif item == MenuItem.CAPTURE:
            self.last_message = "Capture en cours..."
        else:
            self.last_message = f"Edition: {item.value}"
        return item

    def adjust_current_setting(self, direction: int) -> int | None:
        setting = self.profile.settings.get(self.selected_item)
        if not setting:
            return None
        new_value = setting.bump(direction)
        self.last_message = f"{setting.key}={new_value}"
        return new_value
