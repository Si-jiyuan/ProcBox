from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from procbox.platforms.macos import _is_user_application, app_bundle_from_executable

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only helpers")


def fake_proc(name: str, exe: str, username: str = "sijiyuan") -> SimpleNamespace:
    return SimpleNamespace(info={"name": name, "exe": exe, "username": username})


def test_bundle_path_from_executable() -> None:
    exe = "/Applications/WeChat.app/Contents/MacOS/WeChat"
    assert app_bundle_from_executable(exe) == "/Applications/WeChat.app"


def test_nested_helper_bundle_resolves_to_outer_app() -> None:
    exe = "/Applications/WeChat.app/Contents/Frameworks/WeChat Helper.app/Contents/MacOS/helper"
    assert app_bundle_from_executable(exe) == "/Applications/WeChat.app"


def test_non_bundle_executable_is_ignored() -> None:
    assert app_bundle_from_executable("/usr/local/bin/node") is None


def test_user_gui_app_is_included() -> None:
    proc = fake_proc("WeChat", "/Applications/WeChat.app/Contents/MacOS/WeChat")
    assert _is_user_application(proc) == "/Applications/WeChat.app"


def test_root_process_is_excluded() -> None:
    proc = fake_proc("Foo", "/Applications/Foo.app/Contents/MacOS/Foo", username="root")
    assert _is_user_application(proc) is None


def test_system_path_is_excluded() -> None:
    proc = fake_proc(
        "Finder",
        "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
    )
    assert _is_user_application(proc) is None


def test_blacklisted_daemon_is_excluded() -> None:
    proc = fake_proc(
        "com.apple.WebKit.Networking",
        "/Applications/Fake.app/Contents/MacOS/WebKit.Networking",
    )
    assert _is_user_application(proc) is None


def test_daemon_without_bundle_is_excluded() -> None:
    proc = fake_proc("networkserviceproxyd", "/usr/libexec/networkserviceproxyd")
    assert _is_user_application(proc) is None


def test_info_plist_selects_the_real_app_icon(tmp_path) -> None:
    import plistlib

    from procbox.platforms.macos import MacOSAdapter

    bundle = tmp_path / "Demo.app"
    resources = bundle / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "aaa.icns").write_bytes(b"wrong")
    (resources / "Demo AppIcon.icns").write_bytes(b"right")
    with (bundle / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump({"CFBundleIconFile": "Demo AppIcon"}, handle)

    selected = MacOSAdapter._preferred_icns_path(resources, str(bundle))

    assert selected is not None
    assert selected.name == "Demo AppIcon.icns"
