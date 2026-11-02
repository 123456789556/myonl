"""角色库（characters.json，引擎级角色资产）单元测试。"""
from __future__ import annotations

import json

import pytest

from engine import characters
from engine.runtime import Runtime

pytestmark = [pytest.mark.unit]


def test_规整_去重与非法颜色回退():
    data = {"characters": [
        {"id": "林晚", "color": "#ffb3c8", "kind": "default", "avatars": {"微笑": "林晚_微笑"}},
        {"id": "林晚", "color": "#000000"},
        {"id": "我", "color": "不是颜色"},
    ]}
    out = characters.normalize(data)
    assert [c['id'] for c in out['characters']] == ['林晚', '我']
    assert out['characters'][0]['avatars'] == {'微笑': '林晚_微笑'}
    assert out['characters'][1]['color'] == '#ffffff'


def test_保存后读取一致(tmp_path):
    p = tmp_path
    characters.save(str(p), {"characters": [{"id": "林晚", "color": "#112233"}]})
    assert (p / 'characters.json').is_file()
    data = characters.load(str(p))
    assert data['characters'][0]['id'] == '林晚'
    assert data['characters'][0]['color'] == '#112233'


def test_load_for_script_向上查找(tmp_path):
    (tmp_path / 'characters.json').write_text(json.dumps({'characters': [{'id': '林晚', 'color': '#abcdef'}]}), encoding='utf-8')
    sub = tmp_path / 'chapters'
    sub.mkdir()
    script = sub / '第一章.gal'
    script.write_text('@ 你好\n@end\n', encoding='utf-8')
    found = characters.load_for_script(str(script))
    assert found['林晚']['color'] == '#abcdef'


def test_runtime_启动时播种角色库(tmp_path):
    (tmp_path / 'characters.json').write_text(json.dumps({'characters': [{'id': '林晚', 'color': '#ffb3c8'}]}), encoding='utf-8')
    script = tmp_path / 'script.gal'
    script.write_text('@label start\n@ 你好\n@end\n', encoding='utf-8')
    rt = Runtime()
    snap = rt.load(str(script))
    assert snap['characters']['林晚']['color'] == '#ffb3c8'


def test_批量改名同步剧本引用(tmp_path):
    (tmp_path / 'characters.json').write_text(json.dumps({'characters': [{'id': '林晚', 'color': '#ffb3c8'}]}), encoding='utf-8')
    script = tmp_path / 'script.gal'
    script.write_text('@character 林晚 #ffb3c8\n@label start\n@show 林晚 微笑\n@ 林晚 你好\n@hide 林晚\n@end\n', encoding='utf-8')
    out = characters.rename_in_project(str(tmp_path), '林晚', '晚晚')
    text = script.read_text(encoding='utf-8')
    assert '晚晚' in text and '林晚' not in text
    assert out['files'] == 1 and out['lines'] == 4
    assert characters.load(str(tmp_path))['characters'][0]['id'] == '晚晚'
