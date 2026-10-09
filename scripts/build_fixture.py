"""Build the isolated device fixture using an installed Android SDK and JDK.

No Gradle, network downloads or production signing keys are needed.
"""

import argparse
import os
import shutil
import subprocess
import zipfile
from pathlib import Path


def run(*args: str | Path) -> None:
    subprocess.run([str(arg) for arg in args], check=True)


def build(sdk: Path, java_home: Path | None, output: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "tests" / "device_app"
    suffix = ".exe" if os.name == "nt" else ""
    tools = sorted(
        (sdk / "build-tools").iterdir(), key=lambda p: tuple(map(int, p.name.split(".")))
    )[-1]
    platforms = [p for p in (sdk / "platforms").iterdir() if (p / "android.jar").is_file()]
    android = (
        sorted(platforms, key=lambda p: int(p.name.split("-")[1].split(".")[0]))[-1] / "android.jar"
    )

    def java_tool(name: str) -> str:
        value = str(java_home / "bin" / (name + suffix)) if java_home else shutil.which(name)
        if not value or not Path(value).is_file():
            raise RuntimeError(f"Missing {name}; set JAVA_HOME to a JDK 17 or newer")
        return value

    output.mkdir(parents=True, exist_ok=True)
    generated = output / "generated"
    classes = output / "classes"
    dex = output / "dex"
    for folder in (generated, classes, dex):
        folder.mkdir(exist_ok=True)
    unsigned = output / "unsigned.apk"
    run(
        tools / ("aapt" + suffix),
        "package",
        "-f",
        "-M",
        source / "AndroidManifest.xml",
        "-S",
        source / "res",
        "-I",
        android,
        "-J",
        generated,
        "-F",
        unsigned,
    )
    java_sources = sorted(source.rglob("*.java")) + sorted(generated.rglob("*.java"))
    run(
        java_tool("javac"),
        "-encoding",
        "UTF-8",
        "-source",
        "8",
        "-target",
        "8",
        "-bootclasspath",
        android,
        "-d",
        classes,
        *java_sources,
    )
    class_jar = output / "classes.jar"
    with zipfile.ZipFile(class_jar, "w") as archive:
        for file in classes.rglob("*.class"):
            archive.write(file, file.relative_to(classes).as_posix())
    run(
        java_tool("java"),
        "-cp",
        tools / "lib" / "d8.jar",
        "com.android.tools.r8.D8",
        "--lib",
        android,
        "--min-api",
        "23",
        "--output",
        dex,
        class_jar,
    )
    with zipfile.ZipFile(unsigned, "a") as archive:
        archive.write(dex / "classes.dex", "classes.dex")
    aligned = output / "aligned.apk"
    run(tools / ("zipalign" + suffix), "-f", "4", unsigned, aligned)
    key = output / "fixture.keystore"
    if not key.exists():
        run(
            java_tool("keytool"),
            "-genkeypair",
            "-keystore",
            key,
            "-storepass",
            "android",
            "-keypass",
            "android",
            "-alias",
            "fixture",
            "-keyalg",
            "RSA",
            "-validity",
            "3650",
            "-dname",
            "CN=Android Use Test Fixture",
        )
    apk = output / "fixture.apk"
    run(
        java_tool("java"),
        "-jar",
        tools / "lib" / "apksigner.jar",
        "sign",
        "--ks",
        key,
        "--ks-pass",
        "pass:android",
        "--key-pass",
        "pass:android",
        "--out",
        apk,
        aligned,
    )
    run(java_tool("java"), "-jar", tools / "lib" / "apksigner.jar", "verify", apk)
    return apk


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk", type=Path, default=os.getenv("ANDROID_HOME") or os.getenv("ANDROID_SDK_ROOT")
    )
    parser.add_argument("--java-home", type=Path, default=os.getenv("JAVA_HOME"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/fixture"))
    args = parser.parse_args()
    if args.sdk is None:
        parser.error("Set ANDROID_HOME or pass --sdk")
    print(build(args.sdk, args.java_home, args.output).resolve())
