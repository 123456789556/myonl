/* 素材缩图 —— 编辑器两端（电脑 / 手机）共用一份。
 *
 * 为什么必须缩：相册原图 4000×3000 解码进内存是 48MB，手机上直接炸；
 * 就算电脑扛得住，导出的单文件也会被原图撑到几十兆，发给谁都打不开。
 *
 * 最长边 1920：1080p 横屏铺满不糊，一张 jpg 约 200~400KB。
 * png / webp 保留原格式 —— 立绘要透明底，转 jpg 会在黑舞台上炸出白边。
 *
 * 两个入口：
 *   shrinkImage(file) → { dataUrl, w, h, type }   手机端落库用（IndexedDB 存 dataURL）
 *   prepFile(file)    → File                      电脑端用（缩完继续走 base64 上传）
 * 两者失败都退回原图，绝不阻断导入。
 */
(function () {
  "use strict";
  var MAX_SIDE = 1920;

  function shrinkImage(file) {
    return new Promise(function (res, rej) {
      var fr = new FileReader();
      fr.onload = function () {
        var img = new Image();
        img.onload = function () {
          var w = img.naturalWidth || img.width;
          var h = img.naturalHeight || img.height;
          var m = Math.max(w, h);
          if (m > MAX_SIDE) { var k = MAX_SIDE / m; w = Math.round(w * k); h = Math.round(h * k); }
          var cv = document.createElement("canvas");
          cv.width = w; cv.height = h;
          var cx = cv.getContext("2d");
          // 透明底（png/webp）铺黑：播放器舞台本来就是深色，白底会在黑边里炸出来
          var isPng = /png|webp/i.test(file.type || "");
          if (!isPng) { cx.fillStyle = "#000"; cx.fillRect(0, 0, w, h); }
          if ("imageSmoothingQuality" in cx) cx.imageSmoothingQuality = "high";
          cx.drawImage(img, 0, 0, w, h);
          var out = isPng ? cv.toDataURL("image/png") : cv.toDataURL("image/jpeg", 0.82);
          res({ dataUrl: out, w: w, h: h, type: isPng ? "image/png" : "image/jpeg" });
        };
        img.onerror = function () { rej(new Error("这张图读不出来（可能不是图片）")); };
        img.src = fr.result;
      };
      fr.onerror = function () { rej(new Error("读文件失败")); };
      fr.readAsDataURL(file);
    });
  }

  // 电脑端用：缩完转回 File，好继续走原来的 base64 上传链路
  function prepFile(file) {
    return shrinkImage(file).then(function (r) {
      return fetch(r.dataUrl).then(function (x) { return x.blob(); }).then(function (blob) {
        if (!blob || blob.size >= file.size) return file;   // 缩了反而更大就用原图
        var stem = String(file.name || "图片").replace(/\.[^.]+$/, "");
        return new File([blob], stem + (r.type === "image/png" ? ".png" : ".jpg"), { type: r.type });
      });
    }).catch(function () { return file; });
  }

  window.MYONLShrink = { MAX_SIDE: MAX_SIDE, shrinkImage: shrinkImage, prepFile: prepFile };
})();
