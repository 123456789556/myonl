package net.myonl.player;

import android.app.Activity;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;

import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewClientCompat;

/**
 * 一个壳：把所有东西塞进 WebView，游戏本体是 assets/index.html（单文件，素材全内嵌）。
 *
 * 关键的一条是**origin**：直接用 file:// 加载 assets 时，localStorage 的行为不保证持久，
 * 而存档全在 localStorage 里 —— 换个壳存档就没了。这里用 WebViewAssetLoader 把 assets
 * 挂到 https://appassets.androidplatform.net，origin 稳定是 https，Storage 才跨启动活着。
 *
 * 不申任何网络权限：素材全内嵌，不需要联网，也就不需要声明 INTERNET。
 */
public class MainActivity extends Activity {

    private static final String START_URL =
            "https://appassets.androidplatform.net/assets/index.html";

    private WebView web;

    // FileProvider authority：必须与 Manifest 里 <provider authorities> 逐字一致。
    private static final String AUTHORITY = "net.myonl.player.fileprovider";

    // ---------- 导出：让文件真的落到手机里 ----------
    // WebView 不处理 <a download> + blob：点了什么都不会发生，而网页那边还会提示「已导出」。
    // 所以开一条桥：JS 把内容转成 base64 递过来，这里走系统「保存到」（SAF），用户选位置，真落地。
    private static final int REQ_SAVE = 1001;
    private String pendingName, pendingMime, pendingB64;

    // 一次导出能塞多大。
    // base64 字符串本身占一份，decode 出来的 byte[] 又占一份 —— 峰值约两倍。
    // 中低端机 WebView 拿不到几百 MB，不设这条线的时候大作品导出就是闪退，
    // 用户以为是存档坏了，实际是内存被自己吃光了。
    // 真超过这个量，该走「文件夹 / zip 发行」，不是单文件 HTML。
    private static final int MAX_SAVE_B64_CHARS = 64 * 1024 * 1024;

    public class SaveBridge {
        @android.webkit.JavascriptInterface
        public void save(final String filename, final String mime, final String base64) {
            if (base64 == null || base64.isEmpty()) {
                say("没内容可存");
                return;
            }
            if (base64.length() > MAX_SAVE_B64_CHARS) {
                say("成品太大（" + (base64.length() / 1024 / 1024) + " MB），先精简素材再导出");
                return;
            }
            pendingName = filename;
            pendingMime = mime;
            pendingB64 = base64;
            runOnUiThread(() -> {
                try {
                    android.content.Intent i = new android.content.Intent(
                            android.content.Intent.ACTION_CREATE_DOCUMENT);
                    i.addCategory(android.content.Intent.CATEGORY_OPENABLE);
                    i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
                    i.putExtra(android.content.Intent.EXTRA_TITLE, filename);
                    startActivityForResult(i, REQ_SAVE);
                } catch (Throwable t) {
                    say("打不开系统的保存窗口");
                }
            });
        }

        @android.webkit.JavascriptInterface
        public String platform() {
            return "android";
        }

        // P136：导出落地后直接「发给朋友」。WebView 没有系统分享面板，只能由 Java 走
        // ACTION_SEND。文件先写进应用私有 cache/exports/，再用 FileProvider 转 content://
        // —— file:// URI 在 Android 7+ 会被系统拒掉（FileUriExposedException）。
        @android.webkit.JavascriptInterface
        public void share(final String filename, final String mime, final String base64) {
            if (base64 == null || base64.isEmpty()) {
                say("没内容可发");
                return;
            }
            if (base64.length() > MAX_SAVE_B64_CHARS) {
                say("成品太大（" + (base64.length() / 1024 / 1024) + " MB），先精简素材再分享");
                return;
            }
            runOnUiThread(() -> {
                try {
                    byte[] bytes = android.util.Base64.decode(base64, android.util.Base64.DEFAULT);
                    java.io.File dir = new java.io.File(getCacheDir(), "exports");
                    if (!dir.exists()) dir.mkdirs();
                    String safe = (filename == null || filename.isEmpty()) ? "myonl.html" : filename;
                    java.io.File file = new java.io.File(dir, safe);
                    try (java.io.FileOutputStream out = new java.io.FileOutputStream(file)) {
                        out.write(bytes);
                        out.flush();
                    }
                    android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(
                            MainActivity.this, AUTHORITY, file);
                    android.content.Intent i = new android.content.Intent(
                            android.content.Intent.ACTION_SEND);
                    i.setType(mime == null || mime.isEmpty() ? "text/html" : mime);
                    i.putExtra(android.content.Intent.EXTRA_STREAM, uri);
                    i.addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    i.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
                    android.content.Intent chooser = android.content.Intent.createChooser(
                            i, "把这份 MYONL 成品发给朋友");
                    chooser.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(chooser);
                } catch (Throwable t) {
                    say("分享没打开：" + t.getMessage());
                }
            });
        }
    }

    private void say(String msg) {
        try {
            android.widget.Toast.makeText(this, msg, android.widget.Toast.LENGTH_SHORT).show();
        } catch (Throwable ignored) { }
    }

    /** 页面弹窗的统一外壳：跟播放器的深色底一致，别让一行浅色系统框突然跳出来。 */
    private android.app.AlertDialog.Builder buildDialog() {
        return new android.app.AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert);
    }

    @Override
    protected void onActivityResult(int req, int res, android.content.Intent data) {
        super.onActivityResult(req, res, data);
        if (req != REQ_SAVE) return;
        if (res != RESULT_OK || data == null || data.getData() == null) {
            say("没有保存");
            pendingB64 = null;     // 用户取消就要立刻松手，别一直占着几十 MB
            return;
        }
        if (pendingB64 == null) {
            say("没有待存的内容");
            return;
        }
        byte[] bytes;
        try {
            bytes = android.util.Base64.decode(pendingB64, android.util.Base64.DEFAULT);
        } catch (Throwable t) {
            say("内容坏了，没写进去");
            return;
        }
        try (java.io.OutputStream out = getContentResolver().openOutputStream(data.getData())) {
            if (out == null) { say("写不进去"); return; }
            out.write(bytes);
            out.flush();
            say("已保存到手机：" + pendingName);
        } catch (Throwable t) {
            say("写入失败：" + t.getMessage());
        } finally {
            pendingB64 = null;
        }
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);

        web = new WebView(this);
        web.setBackgroundColor(0xFF04060C);

        // 关键：状态栏和导航栏是被 hideBars() 主动藏掉的，所以 systemBars 的 inset 常常是 0；
        // 而底部那根手势条**不会跟着藏**，它一直浮在页面最下面吃掉点击 —— 表现的正是
        // "按钮看得见、按不到"。systemGestures 报的才是这条手势区域，即使栏藏了也有效。
        // 顶部同理：无刘海的机器全靠 systemBars（藏了就是 0，顶到边正好），有刘海的靠 cutout。
        // 横屏时挖孔跑到左边/右边，cutout 报的才是 left/right —— 只处理 top/bottom 会让侧边挖孔压住内容。
        ViewCompat.setOnApplyWindowInsetsListener(web, (v, wi) -> {
            androidx.core.graphics.Insets bars = wi.getInsets(WindowInsetsCompat.Type.systemBars());
            androidx.core.graphics.Insets cut = wi.getInsets(WindowInsetsCompat.Type.displayCutout());
            androidx.core.graphics.Insets ges = wi.getInsets(WindowInsetsCompat.Type.systemGestures());
            int t = Math.max(bars.top, cut.top);
            int b = Math.max(bars.bottom, Math.max(ges.bottom, cut.bottom));
            int l = Math.max(bars.left, cut.left);
            int r = Math.max(bars.right, cut.right);
            v.setPadding(l, t, r, b);
            return wi;
        });

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);   // BGM 要能自己起
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);

        // 只给"保存文件"这一个能力：页面本身来自 appassets（自家 asset），不加载外部站点，
        // 所以这里开接口是收得住口的 —— 页面能调到的只有 save/platform 两个方法。
        web.addJavascriptInterface(new SaveBridge(), "__MYONLSave");

        final WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        web.setWebViewClient(new WebViewClientCompat() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                return loader.shouldInterceptRequest(req.getUrl());
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                // 冷启动时分享进来的文件早就读好了，等页面能跑 JS 了再递过去
                flushShare();
                // WebView 本体已经按挖孔让过位（见 setOnApplyWindowInsetsListener），
                // 告诉页面别再自己加一遍顶部安全带，否则顶出双倍空白。
                view.evaluateJavascript(
                        "document.documentElement.classList.add('native-shell')", null);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req,
                                        androidx.webkit.WebResourceErrorCompat err) {
                // 主页没加载出来不能只留一片黑屏：玩家只会以为 App 坏了
                // 注意：第三个参数必须是 WebResourceErrorCompat。
                // WebViewClientCompat 里 (WebView, WebResourceRequest, WebResourceError)
                // 那个重载是 final（它只负责转调本方法），照着写会直接编译失败。
                if (req != null && req.isForMainFrame()) {
                    say("界面没加载出来，重开一次试试");
                }
            }
        });

        // 没有 WebChromeClient，页面里的 alert / confirm / prompt 会被 WebView 直接吞掉 ——
        // 不弹窗、不报错、直接返回 undefined。播放器「导入备份」那一步用的是 confirm，
        // 结果就是点了没反应，玩家以为导入成功了其实什么都没发生。
        web.setWebChromeClient(new android.webkit.WebChromeClient() {
            @Override
            public boolean onJsAlert(WebView view, String url, String message,
                                     android.webkit.JsResult result) {
                buildDialog().setMessage(message)
                        .setPositiveButton("知道了", (d, w) -> result.confirm())
                        .setOnCancelListener(d -> result.confirm())
                        .show();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView view, String url, String message,
                                       android.webkit.JsResult result) {
                buildDialog().setMessage(message)
                        .setPositiveButton("确定", (d, w) -> result.confirm())
                        .setNegativeButton("取消", (d, w) -> result.cancel())
                        .setOnCancelListener(d -> result.cancel())
                        .show();
                return true;
            }

            @Override
            public boolean onJsPrompt(WebView view, String url, String message,
                                      String defaultValue, android.webkit.JsPromptResult result) {
                android.widget.EditText input = new android.widget.EditText(MainActivity.this);
                input.setText(defaultValue == null ? "" : defaultValue);
                buildDialog().setMessage(message)
                        .setView(input)
                        .setPositiveButton("确定", (d, w) -> result.confirm(input.getText().toString()))
                        .setNegativeButton("取消", (d, w) -> result.cancel())
                        .setOnCancelListener(d -> result.cancel())
                        .show();
                return true;
            }
        });

        setContentView(web, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        hideBars();
        ingest(getIntent());
        web.loadUrl(START_URL);
    }

    // ---------- 从别的 App 分享文件进来 ----------
    // 素材库住在网页的 IndexedDB 里，Java 这边只能把文件递过去。
    // 走 base64 直推 JS 是最短的一条路：不用再开 file:// 或自定义 scheme 的第二套入口。
    // 单个 24MB 封顶 —— 再大一个 JS 字符串就能把 WebView 压崩，宁可在门口拒掉并说清楚。
    private static final long MAX_SHARE_BYTES = 24L * 1024 * 1024;
    private final java.util.ArrayDeque<String> shareQueue = new java.util.ArrayDeque<>();

    private void ingest(android.content.Intent it) {
        if (it == null) return;
        String act = it.getAction();
        if (act == null) return;
        // P136：别人用「用 MYONL 打开」发来的作品文件。以前壳只接 SEND 的图片音频，
        // VIEW 进来直接被丢掉，文件打不开。
        if (android.content.Intent.ACTION_VIEW.equals(act)) {
            ingestView(it);
            return;
        }
        if (!android.content.Intent.ACTION_SEND.equals(act)
                && !android.content.Intent.ACTION_SEND_MULTIPLE.equals(act)) return;

        java.util.ArrayList<android.net.Uri> uris = new java.util.ArrayList<>();
        if (android.content.Intent.ACTION_SEND.equals(act)) {
            android.net.Uri u = it.getParcelableExtra(android.content.Intent.EXTRA_STREAM);
            if (u != null) uris.add(u);
        } else {
            java.util.ArrayList<android.net.Uri> many =
                    it.getParcelableArrayListExtra(android.content.Intent.EXTRA_STREAM);
            if (many != null) uris.addAll(many);
        }
        if (uris.isEmpty()) return;

        org.json.JSONArray arr = new org.json.JSONArray();
        for (android.net.Uri u : uris) {
            try {
                String type = getContentResolver().getType(u);
                if (type == null) continue;
                if (!type.startsWith("image/") && !type.startsWith("audio/")) continue;
                byte[] raw = readCapped(u);
                if (raw == null) continue;
                org.json.JSONObject o = new org.json.JSONObject();
                o.put("name", guessName(type));
                o.put("type", type);
                o.put("dataUrl", "data:" + type + ";base64,"
                        + android.util.Base64.encodeToString(raw, android.util.Base64.NO_WRAP));
                arr.put(o);
            } catch (Throwable ignored) {
                // 单个文件坏了不该连累其他几个，跳过继续
            }
        }
        if (arr.length() == 0) return;
        shareQueue.add("window.__MYONLShareReceive && window.__MYONLShareReceive(" + arr + ")");
        flushShare();
    }

    private byte[] readCapped(android.net.Uri u) throws java.io.IOException {
        try (java.io.InputStream in = getContentResolver().openInputStream(u)) {
            if (in == null) return null;
            java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                bo.write(buf, 0, n);
                // 边读边卡：不读完全程才判断，免得一个视频先把内存吃光
                if (bo.size() > MAX_SHARE_BYTES) return null;
            }
            return bo.toByteArray();
        }
    }

    // P136：接住「用本应用打开」的作品文件，接已有导入链路：
    //   .json 作品库备份 -> window.__myonlImportLib（恢复作品 + 素材）
    //   .gal 单剧本      -> 封成作品库 JSON，走同一条 __myonlImportLib
    //   .html 成品       -> 推给素材接收回调并提示（成品直玩链路不在本次范围）
    private void ingestView(android.content.Intent it) {
        android.net.Uri uri = it.getData();
        if (uri == null) return;
        byte[] raw;
        try {
            raw = readCapped(uri);
        } catch (Throwable t) {
            say("这个文件读不出来");
            return;
        }
        if (raw == null) { say("文件太大或读不动，最多收 " + (MAX_SHARE_BYTES / 1024 / 1024) + " MB"); return; }

        String name = guessName(it.getType(), uri);
        String lower = name.toLowerCase(java.util.Locale.ROOT);
        String mime = it.getType();
        if (mime == null) mime = "application/octet-stream";

        if (lower.endsWith(".json") || mime.contains("json")) {
            String text;
            try { text = new String(raw, "UTF-8"); }
            catch (Throwable t) { say("备份文件不是文本，打不开"); return; }
            shareQueue.add("(window.__myonlImportLib ? window.__myonlImportLib("
                    + org.json.JSONObject.quote(text) + ") : Promise.resolve(false))"
                    + ".then(function(ok){});");
            flushShare();
            return;
        }
        if (lower.endsWith(".gal") || "text/plain".equals(mime)) {
            String text;
            try { text = new String(raw, "UTF-8"); }
            catch (Throwable t) { say("剧本不是文本，打不开"); return; }
            String base = name.replaceAll("\\.[^.]+$", "");
            org.json.JSONObject proj = new org.json.JSONObject();
            try {
                proj.put("name", base.isEmpty() ? "从文件打开的作品" : base);
                proj.put("text", text);
                long nowSec = System.currentTimeMillis() / 1000;
                proj.put("ctime", nowSec);
                proj.put("mtime", nowSec);
                org.json.JSONArray arr = new org.json.JSONArray();
                arr.put(proj);
                org.json.JSONObject lib = new org.json.JSONObject();
                lib.put("myonl", "lib");
                lib.put("v", 1);
                lib.put("projects", arr);
                shareQueue.add("(window.__myonlImportLib ? window.__myonlImportLib("
                        + org.json.JSONObject.quote(lib.toString()) + ") : Promise.resolve(false))"
                        + ".then(function(ok){});");
            } catch (Throwable t) {
                say("剧本封装备份失败");
                return;
            }
            flushShare();
            return;
        }
        if (lower.endsWith(".html") || mime.contains("html")) {
            String b64 = android.util.Base64.encodeToString(raw, android.util.Base64.NO_WRAP);
            shareQueue.add("window.__MYONLShareReceive && window.__MYONLShareReceive("
                    + "[{name:" + org.json.JSONObject.quote(name)
                    + ",type:" + org.json.JSONObject.quote(mime)
                    + ",dataUrl:\"data:" + mime + ";base64," + b64 + "\"}]);");
            say("收到一份成品 HTML；在作品库里查看，试玩入口见内置示例");
            flushShare();
            return;
        }
        say("这种文件 MYONL 打不开（" + mime + "）");
    }

    private String guessName(String type, android.net.Uri uri) {
        String fromUri = (uri != null) ? uri.getLastPathSegment() : null;
        if (fromUri != null && !fromUri.isEmpty()) return fromUri;
        return guessName(type);
    }
    private String guessName(String type) {
        String ext = "dat";
        int slash = type.indexOf('/');
        if (slash >= 0 && slash + 1 < type.length()) ext = type.substring(slash + 1);
        if ("mpeg".equals(ext)) ext = "mp3";
        if ("x-wav".equals(ext) || "wave".equals(ext)) ext = "wav";
        if ("x-m4a".equals(ext)) ext = "m4a";
        if ("jpeg".equals(ext)) ext = "jpg";
        return "分享_" + (System.currentTimeMillis() % 100000) + "." + ext;
    }

    private void flushShare() {
        if (web == null) return;
        while (!shareQueue.isEmpty()) {
            web.evaluateJavascript(shareQueue.poll(), null);
        }
    }

    @Override
    protected void onNewIntent(android.content.Intent it) {
        super.onNewIntent(it);
        setIntent(it);
        ingest(it);   // singleTask：App 已经开着时再从相册分享，走这条
    }

    private void hideBars() {
        WindowInsetsControllerCompat c =
                WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        c.hide(WindowInsetsCompat.Type.systemBars());
        c.setSystemBarsBehavior(
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
    }

    @Override
    public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        // 下拉通知栏/切出去回来之后，系统会把栏还回来，这里再收一次
        if (focused) hideBars();
    }

    @Override
    protected void onResume() {
        super.onResume();
        hideBars();
        if (web != null) web.onResume();
    }

    @Override
    protected void onPause() {
        if (web != null) web.onPause();
        super.onPause();
    }

    @Override
    public void onBackPressed() {
        // 先让游戏自己处理（关面板 / 开菜单），它说不用才退出 Activity
        if (web == null) {
            finish();
            return;
        }
        web.evaluateJavascript(
                "(window.myonlBack && window.myonlBack()) ? '1' : '0'",
                value -> {
                    if (value == null || !value.contains("1")) finish();
                });
    }
}
