"""P91 守护：升级不毁玩家数据。

玩家升级 = 把新版解压覆盖旧目录。只要存档/设置还躺在被覆盖的那堆文件里，
就一定会有人某天更新完发现档没了。这里把几条硬约束钉住：

1. 打包形态默认把玩家数据落到 %APPDATA%/Moyul/<游戏名>（不在安装目录里）；
2. 开发形态保持就地，不往 AppData 塞开发垃圾；
3. 工程里显式写 data_dir=game 的，仍按作者说的来；
4. 老版本留在安装目录里的 saves/、settings.json 第一次启动时**复制**过去，原件不动；
5. 发行包本身不带玩家存档（带了就等于每次解压都换档）。
"""
import os
import zipfile
from pathlib import Path

import pytest

from engine import data

ROOT = Path(__file__).resolve().parents[1]

pytestmark = [pytest.mark.unit]


@pytest.fixture
def install_dir(tmp_path):
    """一个"安装目录"：出厂 settings.json + 玩家已经写下的 saves/。"""
    g = tmp_path / "install" / "MYONL游戏"
    (g / "saves").mkdir(parents=True)
    (g / "images").mkdir()
    (g / "settings.json").write_text('{"volume": 80, "text_speed": 30}', encoding="utf-8")
    (g / "saves" / "slot_1.json").write_text('{"slot": 1, "anchor": 12}', encoding="utf-8")
    (g / "saves" / "persistent.json").write_text('{"seen": ["a"]}', encoding="utf-8")
    (g / "images" / "bg_x.png").write_bytes(b"png")
    return g


def _as_frozen(monkeypatch, install: Path) -> None:
    """把进程伪装成 PyInstaller 成品（sys.frozen + sys.executable 指向安装目录里的 exe）。"""
    exe = install / "MYONL游戏.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(data.sys, "frozen", True, raising=False)
    monkeypatch.setattr(data.sys, "executable", str(exe), raising=False)


def test_打包形态默认落到appdata(monkeypatch, tmp_path, install_dir):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _as_frozen(monkeypatch, install_dir)
    got = data.data_root(str(install_dir))
    assert got == str(tmp_path / "appdata" / "Moyul" / "MYONL游戏")
    # 关键：不在安装目录里。在就是"升级覆盖 = 丢档"
    assert os.path.normcase(os.path.abspath(got)) != os.path.normcase(
        os.path.abspath(str(install_dir)))


def test_开发形态仍然就地(monkeypatch, tmp_path):
    monkeypatch.delattr(data.sys, "frozen", raising=False)
    assert data.default_data_dir(str(tmp_path)) == "game"
    assert data.data_root(str(tmp_path)) == str(tmp_path)


def test_作者显式写game时不改它的意思(monkeypatch, tmp_path, install_dir):
    (install_dir / "settings.json").write_text('{"data_dir": "game"}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _as_frozen(monkeypatch, install_dir)
    assert data.data_root(str(install_dir)) == str(install_dir)


def test_老存档第一次启动只复制不删除(monkeypatch, tmp_path, install_dir):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _as_frozen(monkeypatch, install_dir)
    moved = data.migrate_legacy_data(str(install_dir))
    target = Path(data.data_root(str(install_dir)))

    assert "saves/slot_1.json" in moved
    copied = target / "saves" / "slot_1.json"
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == '{"slot": 1, "anchor": 12}'
    # 原件必须还在：复制到一半崩了、或者玩家想退回旧版，都不能两头空
    assert (install_dir / "saves" / "slot_1.json").is_file()
    # 第二次调用不重复搬
    assert data.migrate_legacy_data(str(install_dir)) == []


def test_迁移不覆盖新版本已经写下的存档(monkeypatch, tmp_path, install_dir):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _as_frozen(monkeypatch, install_dir)
    target = Path(data.data_root(str(install_dir)))
    (target / "saves").mkdir(parents=True, exist_ok=True)
    (target / "saves" / "slot_1.json").write_text('{"slot": 1, "anchor": 99}', encoding="utf-8")
    data.migrate_legacy_data(str(install_dir))
    # 以新版写的为准（99），不被旧目录里的 12 盖掉
    assert '"anchor": 99' in (target / "saves" / "slot_1.json").read_text(encoding="utf-8")


def test_玩家设置首次接管后以玩家的为准(monkeypatch, tmp_path, install_dir):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    _as_frozen(monkeypatch, install_dir)
    first = data.player_settings_path(str(install_dir))
    assert Path(first).is_file()
    Path(first).write_text('{"volume": 30}', encoding="utf-8")
    again = data.player_settings_path(str(install_dir))
    assert again == first
    # 出厂那份改了也不该盖掉玩家这份
    (install_dir / "settings.json").write_text('{"volume": 100}', encoding="utf-8")
    assert data.player_settings_path(str(install_dir)) == first
    assert '"volume": 30' in Path(first).read_text(encoding="utf-8")


def test_发行包不带玩家存档(tmp_path, install_dir):
    """包里混进 saves/ 就等于每次解压都换档。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_build_zip", ROOT / "tools" / "build_release_zip.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = tmp_path / "rel.zip"
    with zipfile.ZipFile(out, "w") as zf:
        mod._add_tree(zf, install_dir, "prefix/games/演示")
    names = zipfile.ZipFile(out).namelist()
    assert not any("/saves/" in n for n in names), names
    assert not any(n.endswith("persistent.json") for n in names), names
    assert any(n.endswith("bg_x.png") for n in names), names
    assert any(n.endswith("settings.json") for n in names), "出厂配置该跟着版本走"
