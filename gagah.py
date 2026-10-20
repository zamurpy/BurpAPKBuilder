#!/usr/bin/env python3
import os, sys, shutil, subprocess
PROJECT_SRC = os.environ.get("PROJECT_SRC", "BurpSuiteAndroid")
BUILD_DIR   = os.environ.get("BUILD_DIR",   "BurpAndroidAPK")
PACKAGE_ID  = "org.zamur.burpsuiteandroid"
APP_NAME    = "BurpSuiteAndroid"
FLASK_PORT  = 5000
FLASK_FILE  = "app.py"

def run(cmd, cwd=None):
    print(f">>> {cmd}")
    if subprocess.run(cmd, shell=True, cwd=cwd).returncode != 0:
        sys.exit(f"FAILED: {cmd}")

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(content)

if not os.path.isfile(os.path.join(PROJECT_SRC, FLASK_FILE)):
    sys.exit(f"{FLASK_FILE} tidak ada di {PROJECT_SRC}")

if os.path.exists(BUILD_DIR):
    shutil.rmtree(BUILD_DIR)
os.makedirs(BUILD_DIR)

pkg_path = PACKAGE_ID.replace(".", "/")
py_dst = f"{BUILD_DIR}/app/src/main/python"

write(f"{BUILD_DIR}/settings.gradle", f"""
pluginManagement {{ repositories {{ google(); mavenCentral(); gradlePluginPortal() }} }}
dependencyResolutionManagement {{
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {{ google(); mavenCentral() }}
}}
rootProject.name = "{APP_NAME}"
include ':app'
""")

write(f"{BUILD_DIR}/build.gradle", """
buildscript {
    repositories { google(); mavenCentral() }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.3.2'
        classpath 'com.chaquo.python:gradle:17.0.0'
    }
}
""")

write(f"{BUILD_DIR}/app/build.gradle", f"""
plugins {{ id 'com.android.application'; id 'com.chaquo.python' }}
android {{
    namespace '{PACKAGE_ID}'
    compileSdk 34
    ndkVersion "25.2.9519653"
    defaultConfig {{
        applicationId "{PACKAGE_ID}"
        minSdk 24; targetSdk 34
        versionCode 1; versionName "1.0"
        ndk {{ abiFilters "arm64-v8a" }}
        python {{
            version "3.11" // Menyamakan versi runtime dengan Python di CI
            pip {{
                install "flask>=2.3.0"
                install "cryptography==42.0.8"
                install "requests"
            }}
        }}
    }}
    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
    sourceSets {{ main {{ python.srcDirs = ['src/main/python'] }} }}
}}
""")

write(f"{BUILD_DIR}/gradle.properties",
      "android.useAndroidX=true\nandroid.enableJetifier=true\norg.gradle.jvmargs=-Xmx3072m\n")

os.makedirs(py_dst, exist_ok=True)
for item in os.listdir(PROJECT_SRC):
    if item in (".git", "bin", ".buildozer", "BurpAndroidAPK", "__pycache__", "history.db"):
        continue
    src = os.path.join(PROJECT_SRC, item)
    dst = os.path.join(py_dst, item)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    elif not item.endswith(".pyc"):
        shutil.copy2(src, dst)

write(f"{BUILD_DIR}/app/src/main/AndroidManifest.xml", f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
    <uses-permission android:name="android.permission.WAKE_LOCK"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
    <application android:label="{APP_NAME}" android:usesCleartextTraffic="true"
                 android:theme="@android:style/Theme.Material.Light">
        <activity android:name=".MainActivity" android:exported="true"
                  android:configChanges="orientation|screenSize|keyboardHidden">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
    </application>
</manifest>
""")

write(f"{BUILD_DIR}/app/src/main/java/{pkg_path}/MainActivity.java", f"""package {PACKAGE_ID};
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.appcompat.app.AppCompatActivity;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends AppCompatActivity {{
    private WebView webView;
    @Override protected void onCreate(Bundle b) {{
        super.onCreate(b);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
        new Thread(() -> {{
            try {{
                PyObject runner = Python.getInstance().getModule("app_runner");
                runner.callAttr("run_server", {FLASK_PORT});
            }} catch (Exception e) {{ e.printStackTrace(); }}
        }}).start();
        webView = new WebView(this);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.setWebViewClient(new WebViewClient());
        setContentView(webView);
        webView.postDelayed(() -> webView.loadUrl("http://127.0.0.1:{FLASK_PORT}"), 3000);
    }}
    @Override public void onBackPressed() {{
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }}
}}
""")

write(f"{py_dst}/app_runner.py", f"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
def run_server(port={FLASK_PORT}):
    app_obj = None
    for modname in ["app", "main", "server"]:
        try:
            mod = __import__(modname)
            for attr in ["app", "application", "flask_app", "server"]:
                if hasattr(mod, attr):
                    app_obj = getattr(mod, attr); break
            if app_obj: break
        except Exception as e:
            print("skip", modname, e)
    if not app_obj:
        print("Flask app tidak ditemukan"); return
    app_obj.run(host="127.0.0.1", port=port, debug=False,
                use_reloader=False, threaded=True)
""")

run("gradle wrapper --gradle-version 8.5", cwd=BUILD_DIR)
run("./gradlew --no-daemon assembleDebug", cwd=BUILD_DIR)
print("BUILD OK")
