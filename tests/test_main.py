import pytest

from gentle_stream import main
from tests.test_daemon import runtime  # noqa: F401  (fixture: private runtime dir, fake audio, cleanup)


def test_help_lists_flags_and_controls(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    for text in ("--model", "--mood", "--gentle-shell", "play / pause", "next piece", "describe a mood",
                 "save what is playing", "saved prompts", "presets.json", "the music keeps playing",
                 "quit and stop the music", "ctl", "play|pause|toggle|next|stop|status"):
        assert text in out
    assert "daemon" not in out                     # started automatically, never by hand


def test_an_unavailable_audio_output_is_a_clean_error(runtime, monkeypatch, capsys):
    monkeypatch.setenv("GENTLE_STREAM_AUDIO_FACTORY", "tests.test_daemon:no_device")
    assert main([]) == 1
    err = capsys.readouterr().err
    assert err == "gentle-stream: cannot open the audio output: Error querying device -1\n"


def test_the_tui_attaches_to_the_music_already_playing(runtime, monkeypatch):
    from gentle_stream import client
    from gentle_stream.app import StreamApp

    running = client.ensure()
    seen = []
    monkeypatch.setattr(StreamApp, "run", lambda self: seen.append((self.player.pid, self.initial_mood)))
    assert main(["--mood", "foggy harbour"]) == 0
    assert seen == [(running.pid, "foggy harbour")]   # no second player, the mood goes to the running one


def test_ctl_rejects_an_unknown_action(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["ctl", "louder"])
    assert exit_info.value.code == 2


def test_help_lists_the_setup_samples_command(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "setup-samples" in capsys.readouterr().out


def test_setup_samples_installs_once_and_reports_it(tmp_path, monkeypatch, capsys):
    from gentle_stream import samples
    from tests.test_samples import make_deb

    url, sha = make_deb(tmp_path / "pkg.deb")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(samples, "DEB_URL", url)
    monkeypatch.setattr(samples, "DEB_SHA256", sha)
    assert main(["setup-samples"]) == 0
    out = capsys.readouterr().out
    assert "installed" in out and "FluidR3_GM.sf2" in out and "MIT" in out
    assert main(["setup-samples"]) == 0
    assert "already installed" in capsys.readouterr().out


def test_setup_samples_reports_a_checksum_mismatch(tmp_path, monkeypatch, capsys):
    from gentle_stream import samples
    from tests.test_samples import make_deb

    url, _ = make_deb(tmp_path / "pkg.deb")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(samples, "DEB_URL", url)
    monkeypatch.setattr(samples, "DEB_SHA256", "0" * 64)
    assert main(["setup-samples"]) == 1
    assert "checksum" in capsys.readouterr().err.lower()


# ------------------------------------------------------------ Windows: no background player
@pytest.fixture
def windows(monkeypatch, tmp_path):
    """The Windows path on any OS: no background player, fake audio, no real config."""
    import gentle_stream

    monkeypatch.setattr(gentle_stream, "BACKGROUND_PLAYER", False)
    monkeypatch.setenv("GENTLE_STREAM_AUDIO_FACTORY", "tests.test_daemon:FakeAudio")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))     # no soundfont: fast procedural instruments
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def test_on_windows_the_tui_plays_in_process(windows, monkeypatch):
    from gentle_stream.app import StreamApp
    from gentle_stream.player import Player

    seen = []

    def run(self):
        seen.append((type(self.player), self.player._stream is not None, self.initial_mood))
        self.player.close()

    monkeypatch.setattr(StreamApp, "run", run)
    assert main(["--mood", "foggy harbour"]) == 0
    assert seen == [(Player, True, "foggy harbour")]   # already playing when the TUI opens


def test_on_windows_an_unavailable_audio_output_is_a_clean_error(windows, monkeypatch, capsys):
    monkeypatch.setenv("GENTLE_STREAM_AUDIO_FACTORY", "tests.test_daemon:no_device")
    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "gentle-stream: cannot open the audio output: Error querying device -1\n"


@pytest.mark.parametrize("action", ["play", "pause", "toggle", "next", "stop", "status"])
def test_on_windows_ctl_explains_there_is_no_background_player(windows, capsys, action):
    assert main(["ctl", action]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "gentle-stream: ctl needs the background player, which is not available on Windows\n"


def test_help_explains_the_windows_limits(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "on Windows the music plays inside the app" in capsys.readouterr().out
