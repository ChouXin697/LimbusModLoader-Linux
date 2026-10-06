import os
import re
from pathlib import Path

LIMBUS_APPID = "1973530"
GAME_DIR_NAME = "Limbus Company"


def is_windows() -> bool:
    return os.name == "nt"


def steam_roots() -> list[Path]:
    """Steam installation roots, most likely first.

    Linux users may find themselves running the game through Proton from a flatpak install.
    """
    if is_windows():
        import winreg

        roots = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
                roots.append(Path(os.path.normpath(steam_path)))
        except OSError:
            pass
        for var in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
            if base := os.environ.get(var):
                roots.append(Path(base) / "Steam")
        return roots

    home = Path.home()
    candidates = [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
        Path("/usr/share/steam"),
    ]
    return [path for path in candidates if path.is_dir()]


def library_roots() -> list[Path]:
    """Every Steam library folder, including additional drives."""
    roots = []
    for root in steam_roots():
        roots.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        text = vdf.read_text(errors="ignore")
        for raw in re.findall(r'"path"\s*"([^"]+)"', text):
            roots.append(Path(raw.replace("\\\\", "\\")))

    unique = {}
    for root in roots:
        unique.setdefault(str(root), root)
    return list(unique.values())


def find_game_dir() -> Path:
    """Directory holding LimbusCompany.exe."""
    if override := os.environ.get("LIMBUS_GAME_DIR"):
        return Path(override)

    for library in library_roots():
        game_dir = library / "steamapps" / "common" / GAME_DIR_NAME
        if (game_dir / "LimbusCompany.exe").is_file():
            return game_dir

    raise FileNotFoundError(
        f"{GAME_DIR_NAME} not found in any Steam library; "
        "set LIMBUS_GAME_DIR to the folder containing LimbusCompany.exe"
    )


def find_prefix() -> Path:
    """Proton prefix of Limbus Company (Linux only)."""
    for library in library_roots():
        prefix = library / "steamapps" / "compatdata" / LIMBUS_APPID / "pfx"
        if prefix.is_dir():
            return prefix

    raise FileNotFoundError(
        f"Proton prefix for app {LIMBUS_APPID} not found; "
        "launch Limbus Company once through Steam/Proton first"
    )


def get_appdata() -> Path:
    """Roaming AppData the game sees, i.e. the mod folder's parent."""
    if appdata := os.environ.get("APPDATA"):
        return Path(appdata)

    if not is_windows():
        users_dir = find_prefix() / "drive_c" / "users"
        for roaming in users_dir.glob("*/AppData/Roaming"):
            return roaming

    raise FileNotFoundError("APPDATA not found")
