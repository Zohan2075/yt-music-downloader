"""
Terminal color utilities
"""

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    GRAY = "\033[90m"


def print_banner():
    banner = f"""
{Colors.CYAN}{'*'*60}{Colors.RESET}
{Colors.BOLD}{Colors.MAGENTA}{'🎵 YouTube Playlist Manager':^60}{Colors.RESET}
{Colors.CYAN}{'*'*60}{Colors.RESET}
{Colors.GRAY}Smart sync • Auto-download • Safe cleanup • Duplicate protection{Colors.RESET}
{Colors.GRAY}Format: Artist - Track (Album) • Fast & reliable • Duplicate-safe{Colors.RESET}
{Colors.CYAN}{'─'*60}{Colors.RESET}
"""
    print(banner)