/* 分镜带 —— 台词区改成「一句一张卡」。
 *
 * 为什么单独一个文件：editor_scene.js 已经顶到 1215 行预算上限，
 * 预算表的规矩是「要加功能就加在新文件里」，不是把天花板往上抬。
 *
 * 契约：只产出 DOM，不接管事件。所有 class 与 data-i 与旧结构一致，
 * editor_scene.js 的 wire()/collect() 靠 querySelectorAll(".sf-say") 取值，
 * 换了内部排版也照样能存回去。
 */
(function () {
  "use strict";

  var SAY_TIPS = ["她推开门。", "「你终于来了。」", "雨还在下。"];

  function tipsHtml(tools) {
    var esc = tools.esc;
    return '<div class="sf-tipbox"><span class="sf-hint">试一句：</span>' +
      SAY_TIPS.map(function (t) {
        return '<button type="button" class="sf-tip">' + esc(t) + "</button>";
      }).join("") + "</div>";
  }

  function card(s, i, pool, tools) {
    var esc = tools.esc, optsHtml = tools.optsHtml;
    var label = pool.length ? "角色…" : "（还没建角色）";
    return '<div class="sf-say sf-card" data-i="' + i + '">' +
      '<div class="sf-card-head">' +
        '<span class="sf-card-no">' + (i + 1) + "</span>" +
        '<select class="sf-who">' + optsHtml(pool, s.who, label) + "</select>" +
        '<button type="button" class="icon-btn sf-del" data-kind="say" data-i="' + i + '" title="删掉这句">✕</button>' +
      "</div>" +
      '<textarea class="sf-text" rows="2" placeholder="台词内容">' + esc(s.text) + "</textarea>" +
      (s.text ? "" : tipsHtml(tools)) +
      "</div>";
  }

  window.MYONLStrip = {
    card: card,
    render: function (model, pool, tools) {
      var h = [];
      h.push('<div class="sf-sec sf-sec-say">台词 <span class="sf-hint">一句一张卡</span> ' +
        '<button type="button" class="icon-btn" id="sfAddSay">＋ 加一句</button></div>');
      h.push('<div id="sfSays" class="sf-cards">');
      model.says.forEach(function (s, i) {
        if (s.del) return;
        h.push(card(s, i, pool, tools));
      });
      h.push("</div>");
      return h.join("");
    }
  };
})();
