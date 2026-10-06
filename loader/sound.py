import glob
import logging
import os
import shutil
import time
from threading import Thread

from modfolder import get_mod_folder
from platform_paths import find_game_dir, is_windows


def sound_folder() -> str:
    return os.path.join(
        str(find_game_dir()),
        "LimbusCompany_Data",
        "StreamingAssets",
        "Assets",
        "Sound",
        "FMODBuilds",
        "Desktop",
    )


def is_game_running() -> bool:
    """Only meaningful on Windows.

    On Linux the loader runs the game with subprocess and stays alive until it exits,
    so the monitor loop below is skipped there.
    """
    if not is_windows():
        return False
    try:
        with os.popen('tasklist /FI "IMAGENAME eq LimbusCompany.exe"') as task:
            return "LimbusCompany.exe" in task.read()
    except Exception:
        return False

def sound_replace_thread(mod_folder: str):
    logging.info("Replacing sound files in Steam directory...")
    target_folder = sound_folder()
    
    for sound_file in glob.glob(f"{mod_folder}/*.bank"):
        logging.info("Replacing %s", sound_file)
        target = os.path.join(target_folder, os.path.basename(sound_file))
        
        if os.path.exists(target) and not os.path.exists(target + ".bak"):
            os.replace(target, target + ".bak")
        elif os.path.exists(target):
            os.remove(target)
            
        shutil.copyfile(sound_file, target)

    if not is_windows():
        return

    for _ in range(30):
        if is_game_running():
            break
        time.sleep(1)

    # Monitor the process and wait until game closes
    logging.info("Game is running. Monitoring for exit to restore all assets...")
    while is_game_running():
        time.sleep(2)

    time.sleep(1)
    logging.info("Game closed detected. Cleaning up both sound and __data assets...")
    
    #Restore the sound files
    restore_sound()
    
    #Restore __data
    try:
        import patch
        patch.cleanup_assets()
        logging.info("Main mod assets successfully restored.")
    except Exception as e:
        logging.error("Failed to auto-restore main assets on close: %s", e)

def restore_sound():
    target_folder = sound_folder()
    backup_files = glob.glob(f"{target_folder}/*.bank.bak")
    if not backup_files:
        return
        
    for sound_file in backup_files:
        target = sound_file.replace(".bak", "")
        if os.path.exists(target):
            os.remove(target)
        os.replace(sound_file, target)
    logging.info("Audio restoration complete.")

def replace_sound(mod_folder: str):
    mod_zips_root_path = get_mod_folder()
    if any(file_name.endswith(".bank") for file_name in os.listdir(mod_zips_root_path)):
        Thread(target=sound_replace_thread, args=(mod_folder,)).start()
    else:
        logging.info("No .bank found, skip sound replacing process.")