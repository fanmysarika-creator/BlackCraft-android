#!/usr/bin/env python3
"""Подготовка проекта BlackCraft к сборке Android-приложения (Capacitor 8).

  python3 prepare_android.py web      — собрать папку www/ из шести файлов игры
  python3 prepare_android.py native   — наложить настройки BlackCraft на android/

Файлы игры в репозитории НЕ изменяются: два небольших исправления для работы
внутри приложения вносятся только в копию www/index.html.
"""
import glob
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ID = "com.blackcraft.game"
MIN_SDK = 24
VERSION_NAME = "1.02"
VERSION_CODE = 3
GAME_FILES = [
    "index.html", "manifest.webmanifest", "sw.js",
    "icon-192.png", "icon-512.png", "icon-maskable-512.png",
]

# (что найти, на что заменить) — только в копии www/index.html
PATCHES = [
    # 1) внутри приложения файлы и так лежат на устройстве: офлайн-кэш (service worker)
    #    не нужен и мог бы показывать старую версию игры после обновления APK
    ('if("serviceWorker" in navigator&&/^https?:$/.test(location.protocol)){',
     'if("serviceWorker" in navigator&&/^https?:$/.test(location.protocol)&&!window.Capacitor){'),
    # 2) полный экран в приложении обеспечивает сам Android (MainActivity)
    ('function goFullscreen(){\n  if(isFull())return;',
     'function goFullscreen(){\n  if(window.Capacitor||isFull())return;'),
]


def p(*parts):
    return os.path.join(ROOT, *parts)


def fail(msg):
    print("::error::" + msg, flush=True)
    sys.exit(1)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------- web
def web():
    missing = [f for f in GAME_FILES if not os.path.isfile(p(f))]
    if missing:
        fail("В корне репозитория не хватает файлов: " + ", ".join(missing) +
             ". Все шесть файлов игры должны лежать рядом с package.json.")
    www = p("www")
    shutil.rmtree(www, ignore_errors=True)
    os.makedirs(www)
    for f in GAME_FILES:
        shutil.copy(p(f), os.path.join(www, f))
    html_path = os.path.join(www, "index.html")
    html = read(html_path)
    for old, new in PATCHES:
        if html.count(old) != 1:
            fail("index.html отличается от ожидаемой версии игры: не найден фрагмент\n" + old)
        html = html.replace(old, new)
    write(html_path, html)
    print("www/ готова: %d файлов, index.html — %d байт" %
          (len(GAME_FILES), os.path.getsize(html_path)))


# ------------------------------------------------------------- native
def patch_manifest(android):
    path = os.path.join(android, "app", "src", "main", "AndroidManifest.xml")
    if not os.path.isfile(path):
        fail("Не найден AndroidManifest.xml")
    s = read(path)
    if "android:screenOrientation" not in s:
        s2 = re.sub(r"<activity(?=[\s>])",
                    '<activity\n            android:screenOrientation="sensorLandscape"', s, count=1)
        if s2 == s:
            fail("В AndroidManifest.xml не найден тег <activity>")
        s = s2
        write(path, s)
    print("AndroidManifest.xml: ориентация sensorLandscape — OK")


def check_gradle_values(android):
    path = os.path.join(android, "variables.gradle")
    if not os.path.isfile(path):
        fail("Не найден android/variables.gradle")
    s = read(path)
    found = {}
    for key in ("minSdkVersion", "compileSdkVersion", "targetSdkVersion"):
        m = re.search(key + r"\s*=\s*(\d+)", s)
        if not m:
            fail("В variables.gradle не найдено значение " + key)
        found[key] = int(m.group(1))
    if found["minSdkVersion"] < MIN_SDK:
        s = re.sub(r"(minSdkVersion\s*=\s*)\d+", lambda m: m.group(1) + str(MIN_SDK), s, count=1)
        write(path, s)
        print("minSdkVersion поднят до %d" % MIN_SDK)
        found["minSdkVersion"] = MIN_SDK
    elif found["minSdkVersion"] > MIN_SDK:
        print("::warning::Шаблон Capacitor использует minSdkVersion=%d (больше %d); оставляю как есть"
              % (found["minSdkVersion"], MIN_SDK))
    print("variables.gradle:", found)

    wp = os.path.join(android, "gradle", "wrapper", "gradle-wrapper.properties")
    if os.path.isfile(wp):
        m = re.search(r"distributionUrl=(.*)", read(wp))
        print("Gradle Wrapper:", m.group(1).replace("\\", "") if m else "?")
    else:
        fail("В android/ нет Gradle Wrapper (gradle-wrapper.properties)")
    for name in ("gradlew", os.path.join("gradle", "wrapper", "gradle-wrapper.jar")):
        if not os.path.isfile(os.path.join(android, name)):
            fail("В android/ нет файла " + name)
    bg = os.path.join(android, "build.gradle")
    if os.path.isfile(bg):
        m = re.search(r"com\.android\.tools\.build:gradle:([\w.\-]+)", read(bg))
        print("Android Gradle Plugin:", m.group(1) if m else "?")
    app_gradle = os.path.join(android, "app", "build.gradle")
    if os.path.isfile(app_gradle) and APP_ID not in read(app_gradle):
        fail("В android/app/build.gradle не найден applicationId " + APP_ID)
    print("applicationId:", APP_ID, "— OK")


def set_version(android):
    path = os.path.join(android, "app", "build.gradle")
    s = read(path)
    s2 = re.sub(r"(versionCode\s+)\d+", lambda m: m.group(1) + str(VERSION_CODE), s, count=1)
    s2 = re.sub(r'(versionName\s+)"[^"]*"', lambda m: m.group(1) + '"%s"' % VERSION_NAME, s2, count=1)
    if s2 == s and ("versionCode %d" % VERSION_CODE) not in s:
        print("::warning::Не удалось записать версию в app/build.gradle (версия останется по умолчанию)")
    else:
        write(path, s2)
        print("Версия приложения: %s (versionCode %d)" % (VERSION_NAME, VERSION_CODE))


def install_keystore():
    src = p("blackcraft-debug.keystore")
    if not os.path.isfile(src):
        print("::warning::Нет blackcraft-debug.keystore: APK будет подписан случайным ключом, "
              "обновление поверх старой версии потребует удалить старую")
        return
    dst_dir = os.path.join(os.path.expanduser("~"), ".android")
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy(src, os.path.join(dst_dir, "debug.keystore"))
    print("Постоянный ключ подписи установлен (обновления ставятся поверх)")


def install_main_activity(android):
    java_root = os.path.join(android, "app", "src", "main", "java")
    dest_dir = os.path.join(java_root, *APP_ID.split("."))
    os.makedirs(dest_dir, exist_ok=True)
    for old in glob.glob(os.path.join(java_root, "**", "MainActivity.*"), recursive=True):
        os.remove(old)
    shutil.copy(p("MainActivity.java"), os.path.join(dest_dir, "MainActivity.java"))
    print("MainActivity.java установлена в", os.path.relpath(dest_dir, android))


def make_icons(android):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        fail("Не установлена библиотека Pillow (pip install pillow)")
    res = os.path.join(android, "app", "src", "main", "res")
    icon = Image.open(p("icon-512.png")).convert("RGBA")
    mask_icon = Image.open(p("icon-maskable-512.png")).convert("RGBA")
    legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    foreground = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
    for dpi, size in legacy.items():
        d = os.path.join(res, "mipmap-" + dpi)
        os.makedirs(d, exist_ok=True)
        for old in glob.glob(os.path.join(d, "ic_launcher*")):
            if old.endswith((".png", ".webp")):
                os.remove(old)
        im = icon.resize((size, size), Image.LANCZOS)
        im.save(os.path.join(d, "ic_launcher.png"))
        big = Image.new("L", (size * 4, size * 4), 0)
        ImageDraw.Draw(big).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
        rnd = im.copy()
        rnd.putalpha(big.resize((size, size), Image.LANCZOS))
        rnd.save(os.path.join(d, "ic_launcher_round.png"))
        fs = foreground[dpi]
        mask_icon.resize((fs, fs), Image.LANCZOS).save(os.path.join(d, "blackcraft_foreground.png"))
    adaptive = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                '    <background android:drawable="@color/blackcraft_icon_bg"/>\n'
                '    <foreground android:drawable="@mipmap/blackcraft_foreground"/>\n'
                '</adaptive-icon>\n')
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        write(os.path.join(res, "mipmap-anydpi-v26", name), adaptive)
    write(os.path.join(res, "values", "blackcraft_icon.xml"),
          '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
          '    <color name="blackcraft_icon_bg">#0B0B0E</color>\n</resources>\n')
    print("Иконки приложения созданы из icon-512.png и icon-maskable-512.png")


def native():
    android = p("android")
    if not os.path.isdir(android):
        fail("Папка android/ не создана (команда npx cap add android не выполнилась)")
    install_main_activity(android)
    patch_manifest(android)
    check_gradle_values(android)
    set_version(android)
    install_keystore()
    make_icons(android)
    print("Настройки BlackCraft применены")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("web", "native"):
        fail("Использование: python3 prepare_android.py web|native")
    web() if sys.argv[1] == "web" else native()
