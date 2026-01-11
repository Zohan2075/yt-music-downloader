"""Progress bar utilities"""

from __future__ import annotations

import time
from typing import Optional

from src.ui.colors import Colors


def format_bytes(num_bytes: Optional[float]) -> str:
    """Return human readable size string."""
    if num_bytes is None or num_bytes <= 0:
        return "--"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:6.2f} {units[idx]}"


def format_speed(num_bytes_per_sec: Optional[float]) -> str:
    if num_bytes_per_sec is None or num_bytes_per_sec <= 0:
        return "--/s"
    return f"{format_bytes(num_bytes_per_sec)}/s"


def format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


class ProgressBar:
    """Animated progress bar for terminal"""

    def __init__(
        self,
        total: float = 100,
        width: int = 40,
        title: str = "",
        show_counts: bool = True,
    ):
        self.total = float(total) if total else 0.0
        self.width = width
        self.title = title
        self.current = 0
        self.start_time = time.time()
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.show_counts = show_counts

    def update(self, value: float, status: str = "", total: Optional[float] = None) -> None:
        """Update progress bar."""
        if total is not None and total > 0:
            self.total = float(total)
        self.current = max(0.0, float(value))
        denom = self.total if self.total > 0 else max(self.current, 1.0)
        percent = (self.current / denom) if denom else 0.0
        percent = max(0.0, min(percent, 1.0))
        filled = int(percent * self.width)
        # Create gradient bar
        bar = ""
        if filled > 0:
            bar += "█" * (filled - 1)
            pct_val = percent * 100
            if pct_val < 25:
                bar += "▏"
            elif pct_val < 50:
                bar += "▌"
            elif pct_val < 75:
                bar += "▊"
            else:
                bar += "█"
        bar += "░" * (self.width - filled)
        # Calculate ETA
        elapsed = time.time() - self.start_time
        if self.current > 0 and elapsed > 0 and self.total > 0:
            speed = self.current / elapsed
            remaining = max(self.total - self.current, 0.0)
            eta = remaining / speed if speed > 0 else 0
            eta_str = f"ETA: {self._format_time(eta)}"
        else:
            eta_str = ""
        # Spinner
        spinner = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1
        # Build display string
        display = f"\r{Colors.CYAN}{spinner}{Colors.RESET} "
        if self.title:
            display += f"{Colors.BOLD}{self.title:<20}{Colors.RESET} "
        display += f"[{Colors.GREEN}{bar}{Colors.RESET}] {Colors.BOLD}{percent*100:6.2f}%{Colors.RESET}"
        if self.show_counts and self.total > 0:
            display += f" {Colors.GRAY}({self._format_units(self.current)}/{self._format_units(self.total)}){Colors.RESET}"
        if eta_str:
            display += f" {Colors.GRAY}{eta_str}{Colors.RESET}"
        if status:
            display += f" {Colors.YELLOW}{status}{Colors.RESET}"
        print(display, end="", flush=True)

    def complete(self, message: str = "") -> None:
        """Complete the progress bar."""
        final_value = self.total if self.total > 0 else self.current
        self.update(final_value, message)
        print()

    def _format_time(self, seconds: float) -> str:
        """Format time for ETA display"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.0f}m {seconds%60:.0f}s"
        else:
            return f"{seconds/3600:.1f}h"

    def _format_units(self, value: float) -> str:
        if value >= 1_000_000:
            return f"{value/1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value/1_000:.1f}K"
        return f"{value:.0f}"