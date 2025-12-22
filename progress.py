"""
Progress bar utilities
"""

import time
from colors import Colors


class ProgressBar:
    """Animated progress bar for terminal"""
    
    def __init__(self, total: int = 100, width: int = 40, title: str = ""):
        self.total = total
        self.width = width
        self.title = title
        self.current = 0
        self.start_time = time.time()
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0

    def update(self, value: int, status: str = ""):
        """Update progress bar"""
        self.current = value
        percent = min(100, int((value / self.total) * 100)) if self.total > 0 else 0
        filled = int((percent / 100) * self.width)
        # Create gradient bar
        bar = ""
        if filled > 0:
            bar += "█" * (filled - 1)
            if percent < 25:
                bar += "▏"
            elif percent < 50:
                bar += "▌"
            elif percent < 75:
                bar += "▊"
            else:
                bar += "█"
        bar += "░" * (self.width - filled)
        # Calculate ETA
        elapsed = time.time() - self.start_time
        if value > 0 and elapsed > 0:
            speed = value / elapsed
            eta = (self.total - value) / speed if speed > 0 else 0
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
        display += f"[{Colors.GREEN}{bar}{Colors.RESET}] {Colors.BOLD}{percent:3}%{Colors.RESET}"
        if value >= 0 and self.total > 0:
            display += f" {Colors.GRAY}({value:,}/{self.total:,}){Colors.RESET}"
        if eta_str:
            display += f" {Colors.GRAY}{eta_str}{Colors.RESET}"
        if status:
            display += f" {Colors.YELLOW}{status}{Colors.RESET}"
        print(display, end="", flush=True)

    def complete(self, message: str = ""):
        """Complete the progress bar"""
        self.update(self.total, message)
        print()

    def _format_time(self, seconds: float) -> str:
        """Format time for ETA display"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.0f}m {seconds%60:.0f}s"
        else:
            return f"{seconds/3600:.1f}h"