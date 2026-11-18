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
