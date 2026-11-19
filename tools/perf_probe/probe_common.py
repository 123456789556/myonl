# -*- coding: utf-8 -*-
"""手机端性能实测共用件：浏览器启动、低端条件注入、帧时间/内存采样、结果落盘。

所有实测数字都来自这里跑出来的真浏览器读数；不在 Python 侧估算帧时间或内存。
测量口径（三套脚本保持一致）：
  - 首屏：导航开始（performance.timeOrigin）→ 首帧可交互（标题页画布已画出且可点）。
  - 帧时间：页面内挂 rAF 采样器，记录每两帧间隔 ms；报表给中位 / p95 / 超 50ms 帧数。
  - 内存：performance.memory（Chromium 非标准，桌面 Chromium 可用）+ MYONL_DEBUG.assets 的位图 MB。
  - 视频释放：MYONL_DEBUG.video.movie.count（活的 <video> 数）/ readyState / paused，
    外加 document.querySelectorAll('video') 的 DOM 节点数，与 heap 采样。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tools" / "perf_probe"

# 低端条件档：每条结论必须带这组参数名。
# deviceMemory / hardwareConcurrency 用 add_init_script 覆写（页面脚本读到的是覆写值）；
# CPU 降速走 CDP Emulation.setCPUThrottlingRate；网络限速走 CDP Network.emulateNetworkConditions。
PROFILES = {
    # 桌面满血对照
    "desktop": {"deviceMemory": 8, "hardwareConcurrency": 8, "cpu": 1.0,
                "net": {"throughput": -1, "latency": 0, "downloadKbps": 10_000_000}},
    # 低端安卓：2GB / 4 核 / CPU 4x，弱网
    "low-end-4x": {"deviceMemory": 2, "hardwareConcurrency": 4, "cpu": 4.0,
                    "net": {"throughput": -1, "latency": 200, "downloadKbps": 1_500}},
    # 更苛刻：1GB / 2 核 / CPU 6x
    "very-low-6x": {"deviceMemory": 1, "hardwareConcurrency": 2, "cpu": 6.0,
                     "net": {"throughput": -1, "latency": 350, "downloadKbps": 800}},
}

VIEWPORTS = {
    "phone-portrait": {"width": 412, "height": 915},
    "phone-landscape": {"width": 915, "height": 412},
    "tablet-portrait": {"width": 800, "height": 1280},
    "tablet-landscape": {"width": 1280, "height": 800},
}


def init_script(mem: int, cores: int) -> str:
    """在页面任何脚本之前覆写设备能力读数。播放器在加载时读这两个值定低端档。"""
    return f"""
      Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {mem} }});
      Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {cores} }});
      window.__PROBE_PROFILE__ = {{ deviceMemory: {mem}, hardwareConcurrency: {cores} }};
    """


FRAME_PROBE_JS = r"""
// 挂在页面里的帧时间采样器：rAF 每帧记间隔；同时记录 canvas 是否有非黑像素。
(function () {
  if (window.__FRAME_PROBE__) return;
  const gaps = [];
  let last = null;
  let nonBlackSeen = 0;
  function tick(now) {
    if (last != null) gaps.push(now - last);
    last = now;
    const c = document.getElementById('game');
    if (c) {
      try {
        const g = c.getContext('2d');
        const d = g.getImageData(0, 0, c.width, c.height).data;
        let nb = 0;
        for (let i = 0; i < d.length; i += 4 * 97) {
          if (d[i] > 40 || d[i+1] > 40 || d[i+2] > 40) { nb++; }
        }
        if (nb > 0) nonBlackSeen++;
      } catch (e) {}
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  window.__FRAME_PROBE__ = {
    gaps: gaps,
    nonBlackFrames: () => nonBlackSeen,
    summary: function () {
      const g = gaps.slice();
      if (!g.length) return {n: 0, median: 0, p95: 0, max: 0, over50: 0};
      const s = g.slice().sort((a, b) => a - b);
      const med = s[Math.floor((s.length - 1) / 2)];
      const p95 = s[Math.floor(Math.min(s.length - 1, Math.ceil(s.length * 0.95) - 1))];
      return {
        n: g.length,
        median: Math.round(med * 100) / 100,
        p95: Math.round(p95 * 100) / 100,
        max: Math.round(Math.max(...g) * 100) / 100,
        over50: g.filter(x => x > 50).length,
      };
    },
  };
})();
"""


def launch_context(pw, profile_key: str, viewport_key: str, headless: bool = True):
    """起浏览器 + 上下文，注入低端条件并接 CDP 做 CPU/网络限速。返回 (browser, context, page, cdp)。"""
    prof = PROFILES[profile_key]
    vp = VIEWPORTS[viewport_key]
    browser = pw.chromium.launch(headless=headless,
                                  args=["--disable-dev-shm-usage", "--no-sandbox",
                                        "--window-position=0,0"])
    ctx = browser.new_context(
        viewport={"width": vp["width"], "height": vp["height"]},
        device_scale_factor=2, has_touch=True, is_mobile=True,
        user_agent="Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    )
    # 每次全新上下文：清掉上一轮残留的存档/设置，保证向导与首屏口径一致。
    ctx.add_init_script("try { localStorage.clear(); } catch (e) {}")
    ctx.add_init_script(init_script(prof["deviceMemory"], prof["hardwareConcurrency"]))
    page = ctx.new_page()

    cdp = ctx.new_cdp_session(page)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": prof["cpu"]})
    net = prof["net"]
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False,
        "latency": net["latency"],
        "downloadThroughput": net["downloadKbps"] * 1024,
        "uploadThroughput": net["downloadKbps"] * 1024,
    })
    return browser, ctx, page, cdp


def read_debug(page) -> dict[str, Any]:
    """从 MYONL_DEBUG 读状态；页面还没就绪时返回空。"""
    return page.evaluate("""() => {
      const d = window.MYONL_DEBUG;
      if (!d) return null;
      const v = d.video || {};
      const a = d.assets || {};
      let heap = null;
      try { if (performance.memory) heap = {
        usedMb: Math.round(performance.memory.usedJSHeapSize / 1048576),
        totalMb: Math.round(performance.memory.totalJSHeapSize / 1048576),
        limitMb: Math.round(performance.memory.jsHeapSizeLimit / 1048576)}; } catch (e) {}
      const domVideos = document.querySelectorAll('video').length;
      // 帧序列视频当前帧号（播放器内部时钟推算），转屏前后对比用
      let frameIdx = null, vlen = null, vfps = null;
      try {
        const sv = d.state && d.state.video;
        if (sv && !sv.file) {
          vfps = sv.fps;
          const seq = (window.__MYONL_PACK__ && window.__MYONL_PACK__.videos &&
                       window.__MYONL_PACK__.videos[sv.name]) || [];
          vlen = seq.length;
          if (vlen) frameIdx = Math.floor(((performance.now() - sv.t0) / 1000) * sv.fps) % vlen;
        }
      } catch (e) { frameIdx = "err:" + e.message; }
      // 调试口 video.name 可能滞后于 state.video，这里直接补一份 state 侧名字/file
      const stateVideoName = d.state && d.state.video ? d.state.video.name : "";
      const stateVideoFile = !!(d.state && d.state.video && d.state.video.file);
      const stateVideoT0 = d.state && d.state.video ? d.state.video.t0 : null;      return {
        scene: d.state && d.state.scene,
        say: d.state && d.state.say && d.state.say.text,
        ended: d.state && d.state.ended,
        error: d.state && d.state.error,
        video: {name: stateVideoName || v.name, fps: vfps, cached: v.cached, ready: v.ready,
                frameIdx: frameIdx, len: vlen, t0: stateVideoT0,
                file: stateVideoFile,
                movie: v.movie},
        assets: a,
        heap: heap,
        domVideos: domVideos,
        layout: d.layout ? {viewW: d.layout.viewW, viewH: d.layout.viewH,
                             landscape: d.layout.landscape} : null,
      };
    }""")


def heap_mb(page) -> dict:
    return page.evaluate("""() => {
      if (!performance.memory) return null;
      return {usedMb: Math.round(performance.memory.usedJSHeapSize / 1048576),
              totalMb: Math.round(performance.memory.totalJSHeapSize / 1048576),
              limitMb: Math.round(performance.memory.jsHeapSizeLimit / 1048576)};
    }""")


def frame_summary(page) -> dict:
    return page.evaluate("() => window.__FRAME_PROBE__ ? window.__FRAME_PROBE__.summary() : null")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def median(xs: list[float]) -> float:
    return round(statistics.median(xs), 2) if xs else 0.0
