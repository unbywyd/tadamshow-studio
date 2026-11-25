"""`tadam doctor` against a fake computer: nothing here touches the real PATH, Godot or ffmpeg."""
from __future__ import annotations

import os

import pytest

from tadam import cli, doctor

SECRET = "FAKE-OPENAI-KEY-must-never-be-printed-0123456789"
GODOT_47 = "4.7.2.stable.official.ed1daf0bf\n"
FFMPEG = "ffmpeg version 7.1-full_build Copyright (c) 2000-2024 the FFmpeg developers\n"
FFPROBE = "ffprobe version 7.1-full_build Copyright (c) 2007-2024 the FFmpeg developers\n"
ENCODERS = " V....D libx264  libx264 H.264 / AVC / MPEG-4 AVC (codec h264)\n"


def fake(tmp_path, *, env=None, tools=None, outputs=None, version=(3, 12, 4), platform="linux",
         files=(), dirs=None):
    """A System where only the given tools exist and every command answers from `outputs`."""
    tools = {"godot": "/usr/bin/godot", "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"} \
        if tools is None else tools
    outputs = {
        ("/usr/bin/godot", "--version"): GODOT_47,
        ("/usr/bin/ffmpeg", "-version"): FFMPEG,
        ("/usr/bin/ffprobe", "-version"): FFPROBE,
        ("/usr/bin/ffmpeg", "-hide_banner", "-encoders"): ENCODERS,
    } if outputs is None else outputs
    env = {"OPENAI_API_KEY": SECRET, "PATH": ""} if env is None else env
    calls = []

    def run(cmd):
        calls.append(tuple(cmd))
        return outputs.get(tuple(cmd))

    s = doctor.System(environ=env, which=lambda n: tools.get(n), run=run, version_info=version,
                      platform=platform, is_file=lambda p: p in files,
                      list_dir=lambda d: list((dirs or {}).get(d, [])), temp_dir=lambda: str(tmp_path))
    s.calls = calls
    return s


def by_name(results):
    return {r.name: r for r in results}


def test_all_present_exit_0(tmp_path, capsys):
    code = doctor.main(fake(tmp_path))
    out = capsys.readouterr().out
    assert code == 0
    assert "[MISS]" not in out and "[warn]" not in out
    assert "4.7.2" in out and "Ready." in out


def test_key_value_is_never_printed(tmp_path, capsys):
    doctor.main(fake(tmp_path))
    out = capsys.readouterr().out
    assert SECRET not in out
    assert SECRET[:8] not in out
    assert "set (value hidden)" in out


def test_key_missing_is_a_warning_not_a_failure(tmp_path, capsys):
    code = doctor.main(fake(tmp_path, env={"PATH": ""}))
    out = capsys.readouterr().out
    assert code == 0
    assert "[warn] OPENAI_API_KEY: not set" in out
    assert "platform.openai.com/api-keys" in out


def test_key_with_odd_characters_warns_without_echo(tmp_path, capsys):
    bad = "fake-\u043a\u043b\u044e\u0447 SECRETPART"
    doctor.main(fake(tmp_path, env={"OPENAI_API_KEY": bad, "PATH": ""}))
    out = capsys.readouterr().out
    assert "does not look like a key" in out
    assert "SECRETPART" not in out


def test_old_python_fails(tmp_path, capsys):
    code = doctor.main(fake(tmp_path, version=(3, 10, 11)))
    out = capsys.readouterr().out
    assert code == 1
    assert "[MISS] Python: 3.10.11 (need 3.11 or newer)" in out
    assert "python.org" in out


def test_no_godot_fails_with_hint(tmp_path, capsys):
    tools = {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}
    code = doctor.main(fake(tmp_path, tools=tools))
    out = capsys.readouterr().out
    assert code == 1
    assert "[MISS] Godot 4.7: not found" in out
    assert "godotengine.org/download" in out and "TADAM_GODOT" in out


def test_wrong_godot_version_fails(tmp_path):
    s = fake(tmp_path)
    s.run = lambda cmd: "4.6.1.stable.official.abc\n" if cmd[-1] == "--version" else FFMPEG + ENCODERS
    r = by_name(doctor.run_checks(s))["Godot 4.7"]
    assert r.status == "missing" and "found 4.6.1" in r.detail


def test_godot_from_env_wins_over_path(tmp_path):
    path = "/opt/godot/Godot_v4.7.2-stable_linux.x86_64"
    outs = {(path, "--version"): GODOT_47, ("/usr/bin/ffmpeg", "-version"): FFMPEG,
            ("/usr/bin/ffprobe", "-version"): FFPROBE}
    s = fake(tmp_path, env={"TADAM_GODOT": path, "PATH": ""}, outputs=outs, files={path})
    r = by_name(doctor.run_checks(s))["Godot 4.7"]
    assert r.status == "ok" and "TADAM_GODOT" in r.detail and path in r.detail
    assert ("/usr/bin/godot", "--version") not in s.calls


def test_godot_env_pointing_nowhere_fails(tmp_path):
    s = fake(tmp_path, env={"TADAM_GODOT": "/nope/godot", "PATH": ""})
    r = by_name(doctor.run_checks(s))["Godot 4.7"]
    assert r.status == "missing" and "no file" in r.detail


def test_godot_exe_found_in_a_path_folder_on_windows(tmp_path):
    folder = r"C:\Tools\Godot"
    exe = folder + r"\Godot_v4.7.2-stable_win64_console.exe"
    gui = folder + r"\Godot_v4.7.2-stable_win64.exe"
    tools = {"ffmpeg": "ffmpeg.exe", "ffprobe": "ffprobe.exe"}
    outs = {(exe, "--version"): GODOT_47, ("ffmpeg.exe", "-version"): FFMPEG, ("ffprobe.exe", "-version"): FFPROBE,
            ("ffmpeg.exe", "-hide_banner", "-encoders"): ENCODERS}
    s = fake(tmp_path, env={"PATH": folder}, tools=tools, outputs=outs, platform="win32",
             dirs={folder: [gui, exe, folder + r"\readme.txt"]})
    r = by_name(doctor.run_checks(s))["Godot 4.7"]
    assert r.status == "ok", r.detail
    assert "console" in r.detail                       # the console build is preferred


def test_godot_app_on_macos(tmp_path):
    app = "/Applications/Godot.app/Contents/MacOS/Godot"
    outs = {(app, "--version"): GODOT_47, ("/usr/bin/ffmpeg", "-version"): FFMPEG,
            ("/usr/bin/ffprobe", "-version"): FFPROBE}
    tools = {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}
    s = fake(tmp_path, env={"PATH": ""}, tools=tools, outputs=outs, platform="darwin", files={app})
    assert by_name(doctor.run_checks(s))["Godot 4.7"].status == "ok"


def test_godot_that_does_not_start(tmp_path):
    s = fake(tmp_path, outputs={})
    r = by_name(doctor.run_checks(s))["Godot 4.7"]
    assert r.status == "missing" and "does not start" in r.detail


def test_dotnet_godot_is_a_warning(tmp_path):
    s = fake(tmp_path)
    s.run = lambda cmd: "4.7.2.stable.mono.official.abc\n" if cmd[-1] == "--version" else FFMPEG + ENCODERS
    r = by_name(doctor.run_checks(s))["Godot 4.7"]
    assert r.status == "warn" and not r.required


@pytest.mark.parametrize("missing", ["ffmpeg", "ffprobe"])
def test_missing_ffmpeg_or_ffprobe_fails(tmp_path, capsys, missing):
    tools = {"godot": "/usr/bin/godot", "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}
    del tools[missing]
    code = doctor.main(fake(tmp_path, tools=tools))
    out = capsys.readouterr().out
    assert code == 1
    assert f"[MISS] {missing}: not found on PATH" in out
    assert "ffmpeg.org/download" in out


def test_ffmpeg_without_x264_warns(tmp_path):
    s = fake(tmp_path)
    s.run = lambda cmd: {"--version": GODOT_47, "-version": FFMPEG}.get(cmd[-1], " V..... libx265 x265\n")
    r = by_name(doctor.run_checks(s))["ffmpeg H.264"]
    assert r.status == "warn" and not r.required


def test_unwritable_temp_fails(tmp_path, capsys):
    s = fake(tmp_path)
    s.temp_dir = lambda: str(tmp_path / "does" / "not" / "exist")
    code = doctor.main(s)
    assert code == 1
    assert "[MISS] temp folder" in capsys.readouterr().out


def test_temp_check_leaves_nothing_behind(tmp_path):
    doctor.run_checks(fake(tmp_path))
    assert os.listdir(tmp_path) == []


def test_cli_dispatches_doctor(monkeypatch):
    monkeypatch.setattr(doctor, "main", lambda: 7)
    assert cli.main(["doctor"]) == 7


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert "tadam 0.0.1" in capsys.readouterr().out
