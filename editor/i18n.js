/* MYONL 界面词典（P199b 前置：按键英文适配）
 *
 * 只做「一处开关、全部按键跟着走」，不整站翻译。理由：整站翻要动 20 多个文件，
 * 而且文案散落在各处，翻一次就再也对不上；先把新做的这套收口，以后加一个界面就加一组词。
 *
 * 选词原则（参考 VS Code / Photoshop / Android Studio）：
 *   每个动作优先一个单词；业界已经是固定短语的（Replace All）不硬缩；
 *   剧本语境用 Cast / Lines，不用 Characters / Dialogue —— 短，且行内一眼认得出。
 *
 * 用法：
 *   MYONLI18N.t("find.all")        -> "全部替换" / "Replace All"
 *   MYONLI18N.t("lint.broken", "教室") -> 带一个替换参数
 *   MYONLI18N.set("en")            -> 切语言，派发 myonl:lang 事件让界面重渲染
 */
(function () {
  "use strict";
  var KEY = "myonl:lang";

  var DICT = {
    /* 查找浮层：按钮与占位 */
    "find.ph": { zh: "查找…", en: "Find…" },
    "find.replPh": { zh: "替换为…", en: "Replace with…" },
    "find.close": { zh: "关闭", en: "Close" },
    "find.undo": { zh: "撤销这次替换", en: "Undo" },
    "find.all": { zh: "全部替换", en: "Replace All" },
    "find.check": { zh: "检查全文", en: "Problems" },
    "find.tags": { zh: "包含指令/标签", en: "Include tags" },
    "find.chip.char": { zh: "角色", en: "Cast" },
    "find.chip.scene": { zh: "场景", en: "Scene" },
    "find.chip.say": { zh: "仅台词", en: "Lines" },
    "find.chip.cmd": { zh: "更多指令", en: "Cmds" },
    "find.fab": { zh: "查", en: "Find" },
    "find.top": { zh: "查找", en: "Find" },
    "find.why.char": { zh: "角色 %s", en: "Cast %s" },
    "find.why.cmd": { zh: "指令 @%s", en: "@%s" },
    "find.why.say": { zh: "台词", en: "Line" },
    "find.why.nar": { zh: "旁白", en: "Narration" },
    "find.why.option": { zh: "选项", en: "Choice" },
    "find.why.empty": { zh: "", en: "" },
    "find.title.lines": { zh: "%s 处句子", en: "%s lines" },
    "find.title.hits": { zh: "%s 处命中", en: "%s matches" },
    "find.title.checked": { zh: "检查结果：错误 %s · 提醒 %s · 提示 %s", en: "Problems: %s error · %s warning · %s note" },
    "find.empty": { zh: "没有结果", en: "No results" },

    /* 提示与确认 */
    "msg.needFind": { zh: "先填要查找的内容", en: "Type something to find first" },
    "msg.noMatch": { zh: "没找到「%s」", en: "No match for “%s”" },
    "msg.cmdWarn": { zh: "会连指令行和 label 一起改，label 一改所有 @jump 就断链", en: "This also edits commands and labels — renaming a label breaks every @jump to it" },
    "msg.cmdConfirm": { zh: "会把指令行、label 名和选项一起改。label 改名后所有指向它的 @jump 都会断链，确定？", en: "This will also edit command lines, label names and options. Any @jump pointing at a renamed label will break. Continue?" },
    "msg.replaced": { zh: "替换了 %s 处", en: "Replaced %s" },
    "msg.undone": { zh: "已撤销这次替换", en: "Undo done" },
    "msg.needScript": { zh: "先打开剧本，再查找", en: "Open a script first" },
    "msg.brokenHead": { zh: "替换了 %s 处，但有 %s 处断链：", en: "Replaced %s, but %s broken link(s): " },
    "msg.lineN": { zh: "第 %s 行 · %s", en: "Line %s · %s" },

    /* 体检规则（消息在 UI 层组装，lint 只回 code —— 否则翻译被塞进纯函数里） */
    "lint.unregistered": {
      zh: "「%s」没登记，这行会被静默当旁白渲染，角色名不显示",
      en: "“%s” is not declared — this line renders as narration and the name disappears"
    },
    "lint.bracket-stray": {
      zh: "渲染正常，但角色库里没有「%s」这个条目",
      en: "Renders fine, but “%s” is not in the cast list"
    },
    "lint.char-unused": {
      zh: "「%s」定义了，但没有任何台词用这个角色名",
      en: "“%s” is declared, but no line uses it"
    },
    "lint.jump-broken": {
      zh: "@jump 目标「%s」不存在，玩家走到这里会卡死",
      en: "No label named “%s” — the story dead-ends here"
    },
    "lint.label-orphan": {
      zh: "「%s」没有任何跳转指向它，也不会被自动播放到",
      en: "Nothing jumps to “%s” and it will never play"
    },
    "lint.level.error": { zh: "错误", en: "error" },
    "lint.level.warn": { zh: "提醒", en: "warning" },
    "lint.level.info": { zh: "提示", en: "note" }
  };

  var lang = "zh";
  try {
    var saved = localStorage.getItem(KEY);
    if (saved === "en" || saved === "zh") lang = saved;
  } catch (e) {}

  function t(key, a, b, c) {
    var row = DICT[key];
    var s = row ? (row[lang] != null ? row[lang] : row.zh) : key;
    if (a != null) s = s.replace("%s", a);
    if (b != null) s = s.replace("%s", b);
    if (c != null) s = s.replace("%s", c);
    return s;
  }

  function set(next) {
    if (next !== "en" && next !== "zh") return;
    lang = next;
    try { localStorage.setItem(KEY, lang); } catch (e) {}
    try { document.dispatchEvent(new CustomEvent("myonl:lang", { detail: lang })); } catch (e) {}
  }

  function toggle() { set(lang === "en" ? "zh" : "en"); }

  window.MYONLI18N = {
    t: t, set: set, toggle: toggle,
    get lang() { return lang; },
    DICT: DICT
  };
})();
