"""存档原子写与坏档兜底验收（P119）。

背景：以前 save() 直接 write_text 覆盖，进程被杀或断电会留下半截 JSON，
玩家下次读档就是"存档损坏"。这组用例守住三件事：
  1. 写盘走临时文件 + replace，中途失败不碰坏主文件；
  2. 主文件坏了能从同目录 .bak 退回上一版；
  3. 主文件整个丢了、.bak 还在，也当成"有存档"。
"""
import json
from pathlib import Path

import pytest

from engine import save as save_api
from engine.save import SaveError

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _state(text="第一句"):
    return {"label": "序章", "history": [{"speaker": "", "text": text}], "pc": 0}


def _slot_file(tmp_path) -> Path:
    return Path(save_api.slot_path(1))


def test_写盘不留临时文件(tmp_path):
    save_api.save(_state(), 1)
    slot = _slot_file(tmp_path)
    assert slot.is_file()
    assert not slot.with_name(slot.name + ".tmp").exists(), "临时文件应该已经被 replace 掉"


def test_第二次写会留上一版bak(tmp_path):
    save_api.save(_state("旧内容"), 1)
    save_api.save(_state("新内容"), 1)
    slot = _slot_file(tmp_path)
    bak = slot.with_name(slot.name + ".bak")
    assert bak.is_file(), "覆盖写之前应该先把旧档备份一份"
    assert "旧内容" in bak.read_text(encoding="utf-8")
    assert "新内容" in slot.read_text(encoding="utf-8")


def test_主文件半截损坏时自动退回bak(tmp_path):
    save_api.save(_state("第一版"), 1)
    save_api.save(_state("第二版"), 1)
    slot = _slot_file(tmp_path)
    # 模拟写到一半断电：主文件只剩半个 JSON
    slot.write_text('{"engine": "moyul", "state": {"histo', encoding="utf-8")
    data = save_api.load(1)
    assert isinstance(data["state"], dict), "应该从 .bak 把上一版读回来"
    # 救回来之后主文件应该被重写成完整 JSON，下次不用再兜底
    json.loads(slot.read_text(encoding="utf-8"))


def test_主文件丢失但bak还在时算有存档(tmp_path):
    save_api.save(_state("第一版"), 1)
    save_api.save(_state("第二版"), 1)
    slot = _slot_file(tmp_path)
    slot.unlink()  # 替换中途被打断：主文件没了、备份还在
    data = save_api.load(1)
    assert isinstance(data["state"], dict)


def test_两个都没有才报没有存档(tmp_path):
    with pytest.raises(SaveError, match="没有存档"):
        save_api.load(1)


def test_两个都坏时报损坏而不是静默成功(tmp_path):
    save_api.save(_state(), 1)
    save_api.save(_state(), 1)
    slot = _slot_file(tmp_path)
    bak = slot.with_name(slot.name + ".bak")
    slot.write_text("不是 json", encoding="utf-8")
    bak.write_text("也不是 json", encoding="utf-8")
    with pytest.raises(SaveError):
        save_api.load(1)


def test_最老的存档没有version字段也要能读(tmp_path):
    """v0 存档：最早的格式没写 version。以前会报"过旧、没有迁移路径"。"""
    slot = _slot_file(tmp_path)
    slot.parent.mkdir(parents=True, exist_ok=True)
    old = {
        "engine": "galengine",
        "state": {"label": "序章", "history": [{"speaker": "", "text": "很老的档"}], "pc": 0},
    }
    slot.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    data = save_api.load(1)
    assert data["version"] == save_api.SCHEMA_VERSION, "应该一路迁移到当前版本"
    assert data["state"]["history"][0]["text"] == "很老的档"
    assert data["state"]["gallery"] == [], "v2→v3 应该补上 gallery"


def test_来自更新引擎的存档要拒绝而不是乱读(tmp_path):
    slot = _slot_file(tmp_path)
    slot.parent.mkdir(parents=True, exist_ok=True)
    future = {"engine": "moyul", "version": save_api.SCHEMA_VERSION + 1, "state": {"label": "x"}}
    slot.write_text(json.dumps(future, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SaveError, match="更新的引擎版本"):
        save_api.load(1)
