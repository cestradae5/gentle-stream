"""Windows support: everything gentle-stream does differently there, kept out of the POSIX modules.

The background player (`daemon.py`, `client.py`) relies on Unix sockets, `flock` and process sessions, so on
Windows the music plays in an in-process `Player` and stops with the app. Gentle Shell is installed by npm as a
`.cmd` shim, which cannot carry the prompt (see `resolve_command`), and process trees are stopped with `taskkill`.

Nothing here imports a POSIX-only module, and the POSIX code paths never call into this one.
"""
from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
AUDIO_FACTORY_ENV = "GENTLE_STREAM_AUDIO_FACTORY"   # the daemon's testing seam: "module:attr" replaces the stream
NPM_SHIM_SCRIPT = re.compile(r'"%dp0%\\([^"%]+\.[cm]?js)"\s+%\*')   # the Node script an npm .cmd shim runs
# no sessions on Windows; and Node writes UTF-8 whatever the console code page is
POPEN_OPTIONS = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), "encoding": "utf-8"}


class PlayerError(Exception):
    """The in-process player could not be started; the message is meant for the terminal."""


class AudioError(PlayerError):
    """The in-process player could not open the audio output."""


class UnsupportedLauncher(Exception):
    """`--gentle-shell` names a batch file that cmd.exe would run with a mangled prompt."""


def local_player():
    """An in-process player, already playing: the TUI opens with the music on, as with the background player."""
    from .engine import Engine
    from .player import Player

    try:
        spec = os.environ.get(AUDIO_FACTORY_ENV)
        factory = getattr(importlib.import_module(spec.partition(":")[0]), spec.partition(":")[2]) if spec else None
        player = Player(Engine(), **({"stream_factory": factory} if factory else {}))
    except Exception as e:
        raise PlayerError(f"cannot start the player: {e}") from None
    try:
        player.start()
    except Exception as e:  # PortAudio missing, no output device, device busy...
        player.close()
        raise AudioError(str(e)) from None
    return player


def resolve_command(binary: str) -> list[str]:
    """The argv prefix that runs `binary` without cmd.exe.

    `gentle-shell` is an npm `.cmd` shim, and a batch file goes through cmd.exe, which cuts the multi-line prompt
    at its first newline and expands %, & and | inside it. So the shim is skipped and its Node script runs
    directly; any other batch file is refused.
    """
    if (path := shutil.which(binary)) is None:
        return [binary]   # a missing binary is reported by Popen
    shim = Path(path)
    if shim.suffix.lower() not in (".cmd", ".bat"):
        return [path]
    match = NPM_SHIM_SCRIPT.search(shim.read_text(errors="replace"))
    if match is None:
        raise UnsupportedLauncher(f"{path} is a batch file that is not an npm shim: cmd.exe would mangle the "
                                  "prompt, so pass --gentle-shell an .exe")
    node = shim.parent / "node.exe"   # what the shim itself prefers
    return [str(node) if node.exists() else (shutil.which("node") or "node"),
            str(shim.parent.joinpath(*match.group(1).split("\\")))]


def kill_tree(pid: int) -> None:
    """Stop a process and everything it spawned: there are no process groups to signal on Windows."""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
