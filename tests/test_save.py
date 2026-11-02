"""save.py 与 runtime 存档原语验收测试。

每个用例都在 tmp_path 下运行（saves/ 与剧本文件互不干扰）。
"""
import json
from pathlib import Path

import pytest

from engine import save as save_api
from engine.runtime import Runtime
from engine.save import SaveError

pytestmark = [pytest.mark.unit]

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _in_tmp(tmp_path, monkeypatch):
    """所有存档写入当前目录下的 saves/，用例之间完全隔离。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_script(tmp_path, script: str, name="test.gal") -> str:
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return str(path)


def make_rt(tmp_path, script: str) -> Runtime:
    rt = Runtime()
    rt.load(write_script(tmp_path, script))
    return rt


def read_payload(slot="1") -> dict:
    return json.loads((save_api.saves_dir() / f"slot_{slot}.json").read_text(encoding="utf-8"))


# 1. 存档文件格式：engine/version/saved_at/label/state/anchor_stack
def test_save_file_format(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@label label_hello\n"
                           "@bg classroom\n@music bgm_main\n@show lin normal\n"
                           "@ 甲 你好。\n@ 甲 再见。\n")
    for _ in range(4):
        rt.step()
    path = rt.save(1)
    assert Path(path) == save_api.saves_dir() / "slot_1.json"

    data = read_payload()
    assert data["engine"] == "moyul" and data["version"] == save_api.SCHEMA_VERSION
    assert data["saved_at"]  # ISO 时间非空
    assert data["label"] == "label_hello"
    assert data["state"]["bg"] == "classroom" and data["state"]["music"] == "bgm_main"
    assert data["state"]["history"] == [{"char": "甲", "text": "你好。"}]
    assert data["anchor_stack"][-1]["kind"] == "label"
    json.dumps(data["anchor_stack"], ensure_ascii=False)  # 锚点必须纯 JSON 类型


# 2. 往返一致：save → 新 Runtime load_save → 全部字段深比较
def test_roundtrip_identical(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@set 好感 += 2\n@bg classroom\n"
                           "@show lin normal\n@ 甲 你好。\n@sfx knock\n")
    for _ in range(4):
        rt.step()
    rt.save(1)
    before = rt.snapshot()

    rt2 = Runtime()
    after = rt2.load_save(1)
    assert after == before
    assert after["vars"] == {"好感": 2}
    assert after["sprites"] == [{"char": "lin", "expr": "normal", "anim": "呼吸"}]
    json.dumps(after, ensure_ascii=False)


# 3. 锚点精确：存档后继续 step，事件与存档前预测一致
def test_anchor_precision(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@label label_x\n"
                           "@ 甲 一。\n@ 甲 二。\n@ 甲 三。\n@ 甲 四。\n@ 甲 五。\n")
    for _ in range(4):  # character/label 被静默跳过：step1 一、step2 二、step3 三、step4 四
        rt.step()
    rt.save(1)

    rt2 = Runtime()
    rt2.load_save(1)
    # 两个运行时从同一点继续，事件应逐条一致（seq 各自独立，不比）
    while not rt.snapshot()["finished"]:
        e1, e2 = rt.step(), rt2.step()
        assert {k: v for k, v in e1.items() if k != "seq"} == \
               {k: v for k, v in e2.items() if k != "seq"}


# 4. if body 内存档：递归锚到父 if，读档后从 body 第 3 条继续
def test_if_body_anchor(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@label label_start\n@set x = 1\n"
                           "@if x == 1:\n    @ 甲 第一句。\n    @ 甲 第二句。\n"
                           "    @ 甲 第三句。\n@ 甲 之后。\n")
    for _ in range(4):  # set / if / 第一句 / 第二句
        rt.step()
    rt.save(1)

    anchors = read_payload()["anchor_stack"]
    assert anchors[-1]["kind"] == "ifbody"
    assert anchors[-1]["offset"] == 2
    assert anchors[-1]["parent"]["kind"] == "label"
    assert anchors[-1]["parent"]["name"] == "label_start"

    rt2 = Runtime()
    snap = rt2.load_save(1)
    assert snap["vars"] == {"x": 1}
    assert rt2.step()["text"] == "第三句。"
    assert rt2.step()["text"] == "之后。"
    assert rt2.snapshot()["finished"] is False  # @end 之前还有一步 end 事件


# 5. choice 暂停点存档：pending_choice 恢复，choose 正常
def test_choice_pending_roundtrip(tmp_path):
    rt = Runtime()
    rt.load(str(FIXTURES / "基础流程.gal"))
    while rt.step()["type"] != "choice":
        pass
    rt.save(1)
    before = rt.snapshot()
    assert before["pending_choice"] is not None

    rt2 = Runtime()
    snap = rt2.load_save(1)
    assert snap["pending_choice"] == before["pending_choice"]
    with pytest.raises(RuntimeError, match="choose"):
        rt2.step()
    rt2.choose(1)  # 不理她 → label_ignore
    while not rt2.snapshot()["finished"]:
        rt2.step()
    assert rt2.snapshot()["history"][-1] == {"char": "林晚", "text": "……"}


# 6. 快存覆盖：两次 save("quick") 只保留最新一份
def test_quick_overwrite(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@ 甲 第一句。\n@ 甲 第二句。\n")
    rt.step()
    rt.save("quick")
    rt.step()
    rt.save("quick")

    slots = save_api.list_slots()
    assert len(slots) == 1 and slots[0]["slot"] == "quick"
    assert save_api.load("quick")["state"]["history"] == \
        [{"char": "甲", "text": "第一句。"}, {"char": "甲", "text": "第二句。"}]


# 7. 10 位互不干扰：交替读档结果各自正确
def test_ten_slots_independent(tmp_path):
    rt = make_rt(tmp_path, "@character 甲 #ffffff\n@ 甲 一。\n@ 甲 二。\n@ 甲 三。\n")
    rt.step()
    rt.save(1)
    rt.step()
    rt.save(2)

    assert save_api.load(1)["state"]["history"] == [{"char": "甲", "text": "一。"}]
    assert save_api.load(2)["state"]["history"] == [{"char": "甲", "text": "一。"},
                                                   {"char": "甲", "text": "二。"}]
    rt2 = Runtime()
    assert rt2.load_save(1)["history"] == [{"char": "甲", "text": "一。"}]
    rt3 = Runtime()
    assert len(rt3.load_save(2)["history"]) == 2


# 8. list_slots：3 个存档、字段齐全、快存最前且数字位升序
def test_list_slots(tmp_path):
    rt = make_rt(tmp_path, "@label label_a\n@ 旁白一。\n@ 旁白二。\n")
    rt.step()
    rt.save(2)
    rt.save("quick")
    rt.step()
    rt.save(1)

    slots = save_api.list_slots()
    assert [s["slot"] for s in slots] == ["quick", "1", "2"]
    for s in slots:
        assert set(s) >= {"slot", "saved_at", "label", "file"}  # ⑨ 新增 thumbnail_path/chapter_name/last_text
        assert s["saved_at"] and Path(s["file"]).is_file()
    # slot 1 存于剧本末尾（执行栈已空），没有“当前位置”，label 为 None
    assert {s["slot"]: s["label"] for s in slots} == {"quick": "label_a", "2": "label_a",
                                                       "1": None}

    assert save_api.list_slots() != []  # 有存档
    for s in slots:
        save_api.delete_slot(s["slot"])
    assert save_api.list_slots() == []


# 9. 损坏存档：load 抛中文 SaveError，不崩；list_slots 不受牵连
def test_corrupt_save(tmp_path):
    rt = make_rt(tmp_path, "@ 旁白。\n")
    rt.save(1)
    (Path("saves") / "slot_9.json").write_text("{这不是 JSON", encoding="utf-8")
    with pytest.raises(SaveError, match="损坏"):
        save_api.load(9)
    with pytest.raises(SaveError, match="损坏"):  # 读档入口同样给出中文错误、不崩
        Runtime().load_save(9)
    assert [s["slot"] for s in save_api.list_slots()] == ["1"]


# 10. 越界/非法 slot：SaveError（中文）
@pytest.mark.parametrize("slot", [0, 11, -1, "abc", True, 3.5, None])
def test_invalid_slot(tmp_path, slot):
    rt = make_rt(tmp_path, "@ 旁白。\n")
    with pytest.raises(SaveError, match="存档位"):
        rt.save(slot)
    with pytest.raises(SaveError, match="存档位"):
        save_api.load(slot)


def test_numeric_string_slot_allowed(tmp_path):
    rt = make_rt(tmp_path, "@ 旁白。\n")
    path = rt.save("3")  # 菜单回传字符串也可用
    assert path.endswith("slot_3.json")
    assert save_api.load("3")["state"]["history"] == []


# 11. 删档：删后不再出现；删不存在的抛 SaveError
def test_delete_slot(tmp_path):
    rt = make_rt(tmp_path, "@ 旁白。\n")
    rt.save(1)
    rt.save(2)
    save_api.delete_slot(1)
    assert [s["slot"] for s in save_api.list_slots()] == ["2"]
    with pytest.raises(SaveError, match="没有存档"):
        save_api.delete_slot(1)
    with pytest.raises(SaveError, match="没有存档"):
        save_api.load(1)


# 12. 锚点失效：存档后删掉锚点 label → load_save 抛中文“存档失效”
def test_anchor_invalid_after_script_edit(tmp_path):
    path = write_script(tmp_path, "@character 甲 #ffffff\n@label anchor_x\n"
                                  "@ 甲 一。\n@ 甲 二。\n")
    rt = Runtime()
    rt.load(path)
    rt.step()  # 一。
    rt.save(1)

    Path(path).write_text("@character 甲 #ffffff\n@ 甲 一。\n@ 甲 二。\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="存档失效"):
        Runtime().load_save(1)


# 13. 偏移越界：剧本删短 → 钳制到列表末尾，不抛错
def test_offset_clamped_when_script_shrinks(tmp_path):
    path = write_script(tmp_path, "@label lb\n@ 旁白一。\n@ 旁白二。\n@ 旁白三。\n"
                                  "@ 旁白四。\n@ 旁白五。\n")
    rt = Runtime()
    rt.load(path)
    for _ in range(4):  # 已说出一~四，当前位置在「五」
        rt.step()
    rt.save(1)

    Path(path).write_text("@label lb\n@ 旁白一。\n", encoding="utf-8")
    rt2 = Runtime()
    snap = rt2.load_save(1)  # 不抛错
    lid, idx = snap["stack"][-1]
    assert idx == len(rt2._lists[lid]) - 1


# 14. 旧格式 / 缺锚点：中文提示要求重新存档
def test_old_format_without_anchor(tmp_path):
    script = write_script(tmp_path, "@ 旁白。\n")
    rt = Runtime()
    rt.load(script)
    Path("saves").mkdir()
    (Path("saves") / "slot_4.json").write_text(json.dumps({
        "engine": "galengine", "version": 1, "saved_at": "2026-01-01T00:00:00",
        "label": None, "state": rt.snapshot(),
    }, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="版本过旧"):
        Runtime().load_save(4)


# 15. 剧本文件丢失：load_save 抛中文 RuntimeError
def test_missing_script_after_save(tmp_path):
    path = write_script(tmp_path, "@ 旁白。\n")
    rt = Runtime()
    rt.load(path)
    rt.step()
    rt.save(1)
    Path(path).unlink()
    with pytest.raises(RuntimeError, match="剧本文件不存在"):
        Runtime().load_save(1)


# 16. 未 load 就存档：RuntimeError；存档目录自动创建
def test_save_requires_loaded_script(tmp_path):
    with pytest.raises(RuntimeError, match="尚未加载剧本"):
        Runtime().save(1)
    assert not Path("saves").exists()


# 17. 版本迁移：旧存档逐级升级、未来版本拦截
def test_version_migration(tmp_path, monkeypatch):
    rt = make_rt(tmp_path, "@ 旁白。\n")
    base = {
        "engine": "galengine", "version": 0, "saved_at": "2026-01-01T00:00:00",
        "label": None, "state": rt.snapshot(), "anchor_stack": [],
    }
    Path("saves").mkdir(exist_ok=True)
    (Path("saves") / "slot_1.json").write_text(
        json.dumps(base, ensure_ascii=False), encoding="utf-8")

    # 没有迁移路径：明确报错，不静默
    with pytest.raises(SaveError, match="没有可用的迁移路径"):
        save_api.load(1)

    # 注册迁移函数：v0 → v1 补一个字段
    def up_v0(d):
        d["state"] = {**d["state"], "extra_field": "补上了"}
        return d

    monkeypatch.setitem(save_api.MIGRATIONS, 0, up_v0)
    data = save_api.load(1)
    assert data["version"] == save_api.SCHEMA_VERSION  # v0 →（测试迁移）→ v1 → v2 → v3 →（内置迁移）→ v4
    assert data["state"]["extra_field"] == "补上了"
    assert data["state"]["gallery"] == []  # v3 迁移补默认值

    # 未来版本（version 99）→ 中文拦截
    (Path("saves") / "slot_2.json").write_text(
        json.dumps({**base, "version": 99}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SaveError, match="更新的引擎版本"):
        save_api.load(2)


# 18. 缺 version 字段的旧存档按 0 处理，走迁移链
def test_missing_version_treated_as_zero(tmp_path, monkeypatch):
    rt = make_rt(tmp_path, "@ 旁白。\n")
    Path("saves").mkdir(exist_ok=True)
    (Path("saves") / "slot_1.json").write_text(json.dumps({
        "engine": "galengine", "saved_at": "2026-01-01T00:00:00",
        "label": None, "state": rt.snapshot(), "anchor_stack": [],
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setitem(save_api.MIGRATIONS, 0, lambda d: {**d, "migrated": True})
    data = save_api.load(1)
    assert data["version"] == save_api.SCHEMA_VERSION and data.get("migrated") is True
