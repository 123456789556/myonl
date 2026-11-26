/* 场景设置二级收纳（P280）：素材/角色/图层/选项/跳转/变量与条件全收进一条折叠。
 *
 * 为什么单独一个文件：editor_scene.js 顶到 1282 行预算上限，包装层与摘要逻辑放这里，
 * scene.js 只留一句 wrap 调用。
 *
 * 契约：
 *   summary(model)  收起时那一行摘要（背景 · 音乐 · N 分支），没内容给兜底文案
 *   wrap(inner, sum) 把二级表单包进一条 details，同一处进、同一处出
 *   watch(form)     盯住表单：mobile 层注入的「变量与条件」入口一出现就挪进折叠里，
 *                   不在表单根部散出第二个入口
 */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function summary(model) {
    var parts = [];
    if (model.bg) parts.push("背景 " + model.bg.name);
    if (model.music) parts.push("音乐 " + model.music.name);
    var n = (model.options || []).filter(function (o) { return !o.del; }).length;
    if (n) parts.push(n + " 分支");
    return parts.length ? parts.join(" · ") : "背景 / 视频 / 音乐 · 角色 · 选项 · 跳转";
  }

  function wrap(inner, sum) {
    return '<details class="sf-fold sf-setup"><summary class="sf-sec">场景设置 ' +
      '<span class="sf-hint">' + esc(sum) + "</span></summary>" + inner + "</details>";
  }

  function moveVarEntry(form) {
    var box = form && form.querySelector(".sf-setup");
    var ve = form && form.querySelector("#mVarEntry");
    if (box && ve) box.appendChild(ve);
  }

  function watch(form) {
    if (!form || form.dataset.setupHook) return;
    form.dataset.setupHook = "1";
    new MutationObserver(function () { moveVarEntry(form); }).observe(form, { childList: true });
  }

  window.MYONLSetup = { summary: summary, wrap: wrap, watch: watch, moveVarEntry: moveVarEntry };
})();
