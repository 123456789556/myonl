/* 素材缩略图 —— 只生成「列表里显示用的小图」，绝不替换原图。
 *
 * 为什么分开：原图是作品的一部分，缩了画质就永久没了；
 * 而素材列表一屏要铺十几张，每张都按原尺寸解码，4000×3000 的一张就是 48MB，
 * 打开素材库那一下足够让低端机闪退。
 *
 * 所以存两份：原图（导出用）+ 240 边的缩略图（列表用）。
 * 缩略图丢了也没关系，取不到就退回原图。
 */
(function () {
  "use strict";
  var EDGE = 240;

  function fromDataUrl(url, edge) {
    return new Promise(function (res, rej) {
      var img = new Image();
      img.onload = function () {
        var w = img.naturalWidth || img.width;
        var h = img.naturalHeight || img.height;
        var m = Math.max(w, h), e = edge || EDGE;
        if (m > e) { var k = e / m; w = Math.round(w * k); h = Math.round(h * k); }
        var cv = document.createElement("canvas");
        cv.width = w; cv.height = h;
        var cx = cv.getContext("2d");
        // 透明底（png/webp）铺黑：素材卡本来就是深色底，白底会炸出来
        var isPng = /png|webp/i.test(String(url).slice(0, 30));
        if (!isPng) { cx.fillStyle = "#000"; cx.fillRect(0, 0, w, h); }
        if ("imageSmoothingQuality" in cx) cx.imageSmoothingQuality = "high";
        cx.drawImage(img, 0, 0, w, h);
        res(isPng ? cv.toDataURL("image/png") : cv.toDataURL("image/jpeg", 0.72));
      };
      img.onerror = function () { rej(new Error("这张图读不出来")); };
      img.src = url;
    });
  }

  window.MYONLThumb = { EDGE: EDGE, fromDataUrl: fromDataUrl };
})();
