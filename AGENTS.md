# Repository Guidelines

## Project Structure & Module Organization
This repository is intentionally small and hardware-focused:
- `app_photo.py`: Main application (camera pipeline, UI, GPIO input, sync/background workers).
- `sync_photos.sh`: Optional `rsync`-based photo sync script.
- `enable_ro.sh`: Raspberry Pi OverlayFS helper for read-only deployments.
- `pimage.service`: `systemd` unit for autostart on boot.
- `README.md`: Setup and runtime notes.
- `PROGRESS.md`: Feature/status log.

If you add tests, place them in a new `tests/` directory and keep fixtures minimal due to hardware dependencies.

## Build, Test, and Development Commands
- `python3 app_photo.py`: Run the app locally on Raspberry Pi hardware.
- `python3 -m py_compile app_photo.py`: Fast syntax validation before committing.
- `bash sync_photos.sh`: Run one manual sync cycle (uses `REMOTE_TARGET` in script).
- `sudo cp pimage.service /etc/systemd/system/ && sudo systemctl enable --now pimage.service`: Install and start autostart service.
- `sudo systemctl status pimage.service`: Verify runtime health.

## Coding Style & Naming Conventions
- Target Python 3 with 4-space indentation and PEP 8-friendly formatting.
- Use `snake_case` for functions/variables, `UPPER_SNAKE_CASE` for constants, `PascalCase` for classes/enums.
- Keep type hints on public methods and dataclasses (consistent with `CameraParam` and `Menu`).
- Prefer `pathlib.Path`, structured logging (`logging`), and small focused methods over large monolith blocks.
- Shell scripts should stay POSIX/Bash-friendly and include short, actionable comments.

## Testing Guidelines
- Current project has no automated suite; validate changes with:
  - syntax check (`py_compile`)
  - targeted runtime test on device (`python3 app_photo.py`)
  - service smoke test (`systemctl status`)
- For new tests, use `pytest` with names like `tests/test_<feature>.py`.
- Keep hardware-specific logic behind narrow functions so non-hardware unit tests remain possible.

## Commit & Pull Request Guidelines
- Follow Conventional Commit prefixes seen in history: `feat:`, `fix:`, `docs:`, `chore:`.
- Keep each commit focused on one functional change.
- PRs should include:
  - concise problem/solution summary
  - hardware/environment used (e.g., CM4 + Bookworm)
  - validation evidence (commands run, logs, or screenshots for UI changes)
  - linked issue/task when applicable
