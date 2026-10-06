import os

from platform_paths import get_appdata


def get_mod_folder():
    return os.path.join(str(get_appdata()), "LimbusCompanyMods")
