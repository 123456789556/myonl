package net.myonl.player;

import android.app.Activity;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;

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
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req,
                                        android.webkit.WebResourceError err) {
                // 主页没加载出来不能只留一片黑屏：玩家只会以为 App 坏了
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
