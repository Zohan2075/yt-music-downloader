"""Progress bar utilities"""

from __future__ import annotations

import time
from typing import Optional

from colors import Colors


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