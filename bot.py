import atexit
import logging
import os
import sys

import discord
from discord.ext import commands

import config
from utils.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("etvin")

COGS = [
    "cogs.panel",
    "cogs.setup_welcome",
    "cogs.setup_roles",
    "cogs.setup_voice",
    "cogs.setup_social",
    "cogs.setup_rules",
    "cogs.setup_shop",
    "cogs.setup_earning",
    "cogs.shop",
    "cogs.setup_twitch",
    "cogs.setup_logs",
    "cogs.events",
    "cogs.moderation_log",
    "cogs.voice",
    "cogs.twitch",
    "cogs.interaction_log",
]
LOCK_PATH = os.path.join(os.path.dirname(__file__), "data", "bot.lock")


def _acquire_single_instance_lock() -> bool:
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    if os.path.exists(LOCK_PATH):
        try:
            with open(LOCK_PATH, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
        except (OSError, ValueError):
            old_pid = None

        if old_pid and _pid_alive(old_pid):
            if _is_our_bot_process(old_pid):
                log.warning("Останавливаю предыдущий экземпляр бота (PID %s)...", old_pid)
                _terminate_process(old_pid)
            else:
                log.warning(
                    "Lock-файл указывает на чужой процесс (PID %s), перезаписываю",
                    old_pid,
                )
        elif old_pid:
            log.info("Удаляю устаревший lock-файл (PID %s не найден)", old_pid)

    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    atexit.register(_release_single_instance_lock)
    return True


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_our_bot_process(pid: int) -> bool:
    cmdline = _get_process_cmdline(pid)
    if not cmdline:
        return False
    bot_script = os.path.basename(__file__)
    return bot_script in cmdline


def _get_process_cmdline(pid: int) -> str:
    if sys.platform == "win32":
        import subprocess

        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=flags,
        )
        return (result.stdout or "").strip()

    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().decode("utf-8", errors="replace").replace("\x00", " ")
    except OSError:
        return ""


def _terminate_process(pid: int) -> None:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0001 | 0x00100000, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.WaitForSingleObject(handle, 5000)
            kernel32.CloseHandle(handle)
        return

    import signal

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def _release_single_instance_lock():
    try:
        if os.path.exists(LOCK_PATH):
            with open(LOCK_PATH, "r", encoding="utf-8") as f:
                if f.read().strip() == str(os.getpid()):
                    os.remove(LOCK_PATH)
    except OSError:
        pass


class EtvinBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.reactions = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        for cog in COGS:
            await self.load_extension(cog)
            log.info("Loaded %s", cog)

        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            log.info("Synced to guild %s", config.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Synced globally")

    async def on_ready(self):
        log.debug("Online: %s | ЛС отключены | только embed-приветствие в канал", self.user)


def main():
    if not _acquire_single_instance_lock():
        sys.exit(1)

    if not config.DISCORD_TOKEN:
        log.error("DISCORD_TOKEN не задан в .env")
        return

    bot = EtvinBot()
    try:
        bot.run(config.DISCORD_TOKEN, log_handler=None)
    except discord.PrivilegedIntentsRequired:
        log.error(
            "Включи Server Members Intent:\n"
            "discord.com/developers/applications → Bot → Privileged Gateway Intents"
        )


if __name__ == "__main__":
    main()
