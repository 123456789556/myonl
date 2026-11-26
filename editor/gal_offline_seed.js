/* ============================================================
   示范案例自带素材 —— 离线首跑种进本机素材库
   ------------------------------------------------------------
   离线内核（gal_offline.js）的素材只认 IndexedDB：/api/assets
   答名字清单，/api/asset/images/<名字> 取图体。随包没有二进制，
   默认那份「示范案例」打开就是空舞台。这里在首跑时把一张
   夜景站台背景（SVG dataURL）按原名 restore 进素材库，剧本里
   的 @bg bg_夜站 才真有画面。

   只在离线模式跑：有 Python 后端时 window.MYONLAssets 不存在，
   这段直接退出，不碰桌面端工程的素材目录。
   ============================================================ */
(function () {
  "use strict";

  var SEED_FLAG = "myonl:off:seed:v1";
  var SEED_NAME = "bg_夜站";
  var SEED_DATA = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMjgwIiBoZWlnaHQ9IjcyMCIgdmlld0JveD0iMCAwIDEyODAgNzIwIj4KICA8ZGVmcz4KICAgIDxsaW5lYXJHcmFkaWVudCBpZD0ic2t5IiB4MT0iMCIgeTE9IjAiIHgyPSIwIiB5Mj0iMSI+CiAgICAgIDxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzBhMTMyMiIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjAuNTUiIHN0b3AtY29sb3I9IiMxYTMxNTMiLz4KICAgICAgPHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjMzU2MzlhIi8+CiAgICA8L2xpbmVhckdyYWRpZW50PgogICAgPHJhZGlhbEdyYWRpZW50IGlkPSJsYW1wIiBjeD0iMC41IiBjeT0iMC41IiByPSIwLjUiPgogICAgICA8c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNkYmVhZmUiIHN0b3Atb3BhY2l0eT0iMC44NSIvPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiNkYmVhZmUiIHN0b3Atb3BhY2l0eT0iMCIvPgogICAgPC9yYWRpYWxHcmFkaWVudD4KICA8L2RlZnM+CiAgPHJlY3Qgd2lkdGg9IjEyODAiIGhlaWdodD0iNzIwIiBmaWxsPSJ1cmwoI3NreSkiLz4KICA8Y2lyY2xlIGN4PSIxMjAiIGN5PSI5MCIgcj0iMS42IiBmaWxsPSIjY2ZlMGZmIiBvcGFjaXR5PSIwLjc1Ii8+CjxjaXJjbGUgY3g9IjIyMCIgY3k9IjE1MCIgcj0iMS4yIiBmaWxsPSIjY2ZlMGZmIiBvcGFjaXR5PSIwLjc1Ii8+CjxjaXJjbGUgY3g9IjM2MCIgY3k9IjcwIiByPSIxLjgiIGZpbGw9IiNjZmUwZmYiIG9wYWNpdHk9IjAuNzUiLz4KPGNpcmNsZSBjeD0iNDgwIiBjeT0iMTMwIiByPSIxLjEiIGZpbGw9IiNjZmUwZmYiIG9wYWNpdHk9IjAuNzUiLz4KPGNpcmNsZSBjeD0iNjEwIiBjeT0iODAiIHI9IjEuNSIgZmlsbD0iI2NmZTBmZiIgb3BhY2l0eT0iMC43NSIvPgo8Y2lyY2xlIGN4PSI3MjAiIGN5PSIxNjAiIHI9IjEuMiIgZmlsbD0iI2NmZTBmZiIgb3BhY2l0eT0iMC43NSIvPgo8Y2lyY2xlIGN4PSI4MzAiIGN5PSI2MCIgcj0iMS43IiBmaWxsPSIjY2ZlMGZmIiBvcGFjaXR5PSIwLjc1Ii8+CjxjaXJjbGUgY3g9Ijk0MCIgY3k9IjEyMCIgcj0iMS4xIiBmaWxsPSIjY2ZlMGZmIiBvcGFjaXR5PSIwLjc1Ii8+CjxjaXJjbGUgY3g9IjExNjAiIGN5PSI5MCIgcj0iMS42IiBmaWxsPSIjY2ZlMGZmIiBvcGFjaXR5PSIwLjc1Ii8+CjxjaXJjbGUgY3g9IjEwODAiIGN5PSIxODAiIHI9IjEuMiIgZmlsbD0iI2NmZTBmZiIgb3BhY2l0eT0iMC43NSIvPgo8Y2lyY2xlIGN4PSIzMDAiIGN5PSIyMTAiIHI9IjEuMCIgZmlsbD0iI2NmZTBmZiIgb3BhY2l0eT0iMC43NSIvPgo8Y2lyY2xlIGN4PSI1NjAiIGN5PSIyMDAiIHI9IjEuMCIgZmlsbD0iI2NmZTBmZiIgb3BhY2l0eT0iMC43NSIvPgogIDxjaXJjbGUgY3g9IjEwNDAiIGN5PSIxNDAiIHI9IjkwIiBmaWxsPSJ1cmwoI2xhbXApIi8+CiAgPGNpcmNsZSBjeD0iMTA0MCIgY3k9IjE0MCIgcj0iNDYiIGZpbGw9IiNlOGYxZmYiLz4KICA8cmVjdCB4PSI0MCIgeT0iNDA2IiB3aWR0aD0iMTIwIiBoZWlnaHQ9IjE5MCIgZmlsbD0iIzBiMTQyNCIvPgo8cmVjdCB4PSI4MiIgeT0iNDI4IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxMDgiIHk9IjQ2MiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNTYiIHk9IjQ5NiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iMTM0IiB5PSI0OTYiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjgyIiB5PSI1MzAiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjEwOCIgeT0iNTY0IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxOTAiIHk9IjQ1NiIgd2lkdGg9IjkwIiBoZWlnaHQ9IjE0MCIgZmlsbD0iIzBiMTQyNCIvPgo8cmVjdCB4PSIyMzIiIHk9IjQ3OCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iMjU4IiB5PSI1MTIiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjIwNiIgeT0iNTQ2IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIzMTAiIHk9IjM3NiIgd2lkdGg9IjE0MCIgaGVpZ2h0PSIyMjAiIGZpbGw9IiMwYjE0MjQiLz4KPHJlY3QgeD0iMzI2IiB5PSIzOTgiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjQwNCIgeT0iMzk4IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIzNTIiIHk9IjQzMiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNDMwIiB5PSI0MzIiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjM3OCIgeT0iNDY2IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIzMjYiIHk9IjUwMCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNDA0IiB5PSI1MDAiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjM1MiIgeT0iNTM0IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSI0MzAiIHk9IjUzNCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iMzc4IiB5PSI1NjgiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjQ4MCIgeT0iNDM2IiB3aWR0aD0iMTAwIiBoZWlnaHQ9IjE2MCIgZmlsbD0iIzBiMTQyNCIvPgo8cmVjdCB4PSI0OTYiIHk9IjQ1OCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNTIyIiB5PSI0OTIiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjU0OCIgeT0iNTI2IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSI0OTYiIHk9IjU2MCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNjEwIiB5PSIzOTYiIHdpZHRoPSIxMzAiIGhlaWdodD0iMjAwIiBmaWxsPSIjMGIxNDI0Ii8+CjxyZWN0IHg9IjY1MiIgeT0iNDE4IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSI2NzgiIHk9IjQ1MiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNjI2IiB5PSI0ODYiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjcwNCIgeT0iNDg2IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSI2NTIiIHk9IjUyMCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNjc4IiB5PSI1NTQiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9Ijc3MCIgeT0iNDY2IiB3aWR0aD0iOTAiIGhlaWdodD0iMTMwIiBmaWxsPSIjMGIxNDI0Ii8+CjxyZWN0IHg9IjgxMiIgeT0iNDg4IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSI4MzgiIHk9IjUyMiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iNzg2IiB5PSI1NTYiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9Ijg5MCIgeT0iMzg2IiB3aWR0aD0iMTUwIiBoZWlnaHQ9IjIxMCIgZmlsbD0iIzBiMTQyNCIvPgo8cmVjdCB4PSI5MDYiIHk9IjQwOCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iOTg0IiB5PSI0MDgiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjkzMiIgeT0iNDQyIiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxMDEwIiB5PSI0NDIiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9Ijk1OCIgeT0iNDc2IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSI5MDYiIHk9IjUxMCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iOTg0IiB5PSI1MTAiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjkzMiIgeT0iNTQ0IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxMDEwIiB5PSI1NDQiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9Ijk1OCIgeT0iNTc4IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxMDcwIiB5PSI0MzYiIHdpZHRoPSIxMTAiIGhlaWdodD0iMTYwIiBmaWxsPSIjMGIxNDI0Ii8+CjxyZWN0IHg9IjEwODYiIHk9IjQ1OCIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iMTE2NCIgeT0iNDU4IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxMTEyIiB5PSI0OTIiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjExMzgiIHk9IjUyNiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iMTA4NiIgeT0iNTYwIiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgo8cmVjdCB4PSIxMTY0IiB5PSI1NjAiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjEyMDAiIHk9IjQwNiIgd2lkdGg9IjgwIiBoZWlnaHQ9IjE5MCIgZmlsbD0iIzBiMTQyNCIvPgo8cmVjdCB4PSIxMjE2IiB5PSI0NjIiIHdpZHRoPSI5IiBoZWlnaHQ9IjEyIiBmaWxsPSIjOWZjMmZmIiBvcGFjaXR5PSIwLjQ1Ii8+CjxyZWN0IHg9IjEyNDIiIHk9IjQ5NiIgd2lkdGg9IjkiIGhlaWdodD0iMTIiIGZpbGw9IiM5ZmMyZmYiIG9wYWNpdHk9IjAuNDUiLz4KPHJlY3QgeD0iMTIxNiIgeT0iNTY0IiB3aWR0aD0iOSIgaGVpZ2h0PSIxMiIgZmlsbD0iIzlmYzJmZiIgb3BhY2l0eT0iMC40NSIvPgogIDxyZWN0IHk9IjU5NiIgd2lkdGg9IjEyODAiIGhlaWdodD0iMTI0IiBmaWxsPSIjMDcwZDE3Ii8+CiAgPHJlY3QgeT0iNTk2IiB3aWR0aD0iMTI4MCIgaGVpZ2h0PSIzIiBmaWxsPSIjMmY1ZmE4Ii8+CiAgPGNpcmNsZSBjeD0iMjUwIiBjeT0iMjM4IiByPSIxMjAiIGZpbGw9InVybCgjbGFtcCkiIG9wYWNpdHk9IjAuNSIvPgogIDxyZWN0IHg9IjI0NiIgeT0iMjUwIiB3aWR0aD0iOCIgaGVpZ2h0PSIzNDYiIGZpbGw9IiMwZDE3MjYiLz4KICA8Y2lyY2xlIGN4PSIyNTAiIGN5PSIyMzgiIHI9IjIyIiBmaWxsPSIjZGJlYWZlIi8+CiAgPHJlY3QgeD0iNzAwIiB5PSI1NDAiIHdpZHRoPSIxODAiIGhlaWdodD0iMTQiIGZpbGw9IiMwYjEzMjAiLz4KICA8cmVjdCB4PSI3MTYiIHk9IjU1NCIgd2lkdGg9IjEyIiBoZWlnaHQ9IjQyIiBmaWxsPSIjMGIxMzIwIi8+CiAgPHJlY3QgeD0iODUyIiB5PSI1NTQiIHdpZHRoPSIxMiIgaGVpZ2h0PSI0MiIgZmlsbD0iIzBiMTMyMCIvPgo8L3N2Zz4=";

  function markDone() {
    try { localStorage.setItem(SEED_FLAG, "1"); } catch (e) { /* 隐私模式写不进就算了 */ }
  }

  try {
    // 桌面端没有 MYONLAssets；离线内核才种素材，别去碰电脑工程目录。
    // 不提前 return：下面的缩略图补丁对老用户导入的素材也要生效。
    if (!localStorage.getItem(SEED_FLAG) && window.MYONLAssets &&
        typeof window.MYONLAssets.restore === "function" &&
        window.MYONLAssets.list().indexOf(SEED_NAME) < 0) {
      var bag = {}; bag[SEED_NAME] = SEED_DATA;
      var kinds = {}; kinds[SEED_NAME] = "image";
      window.MYONLAssets.restore(bag, kinds).then(markDone, markDone);
    }
  } catch (e) { markDone(); }

  // 图片时序救援：场景舞台 / 角色头像 / 素材卡片的 <img> 走浏览器原生取图通道，
  // 绕得过 fetch 劫持；离线静态服务对 /api/asset/images/、/api/thumb 回 404。
  // 舞台图还挂了内联 onerror="this.remove()"，约 100ms 内抢先删节点，轮询到点时
  // 节点已经没了。两道互补：① document 捕获阶段抢在内联处理器之前掐掉事件；
  // ② MutationObserver 扫晚挂载 / lazy 加载、还没发 error 的卡图。
  // 只认 /api/asset/images/ 与 /api/thumb 两类 src，别的图一概不碰。
  function lookupData(am, name) {
    return am
      ? window.MYONLAssets.get(name).then(function (v) { return v && v.dataUrl; })
      : window.MYONLAssets.thumbOf(name);
  }
  function resolveImg(img) {
    if (!img || img.tagName !== "IMG" || !window.MYONLAssets) return;
    var src = String(img.getAttribute("src") || "");
    var am = src.match(/^\/api\/asset\/images\/(.*)$/);
    var tm = src.match(/^\/api\/thumb\?[^#]*name=([^&]+)/);
    if (!am && !tm) return;
    if (img.dataset.offRescue) return;
    img.dataset.offRescue = "1";
    var name = decodeURIComponent(am ? am[1] : tm[1]);
    var orig = img.onerror;
    // 有内联 onerror 的（舞台图）先摘下来：就算捕获阶段挡不住 target 自身处理器，
    // 节点也不会被 this.remove() 抢先删掉；原处理器留着，取不到图时补回。
    if (am && typeof orig === "function") img.onerror = null;
    lookupData(!!am, name).then(function (u) {
      if (u) { img.src = u; return; }
      if (am && typeof orig === "function") orig.call(img);
    }).catch(function () {
      if (am && typeof orig === "function") orig.call(img);
    });
  }
  function sweep(root) {
    if (!window.MYONLAssets) return;
    if (root && root.tagName === "IMG") resolveImg(root);
    var ims = root && root.querySelectorAll ? root.querySelectorAll("img") : [];
    for (var i = 0; i < ims.length; i++) resolveImg(ims[i]);
  }
  function rescueAssetError(e) {
    var img = e.target;
    if (!img || img.tagName !== "IMG" || !window.MYONLAssets) return;
    var src = String(img.getAttribute("src") || "");
    if (/^\/api\/asset\/images\//.test(src) || /^\/api\/thumb\?[^#]*name=/.test(src)) {
      e.stopPropagation();
      resolveImg(img);
    }
  }
  document.addEventListener("error", rescueAssetError, true);
  var mo = new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      var m = muts[i];
      if (m.type === "childList") {
        for (var j = 0; j < m.addedNodes.length; j++) {
          if (m.addedNodes[j].nodeType === 1) sweep(m.addedNodes[j]);
        }
      } else if (m.attributeName === "src" && m.target.tagName === "IMG") {
        resolveImg(m.target);
      }
    }
  });
  mo.observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });
  document.addEventListener("DOMContentLoaded", function () { sweep(document); });
})();
