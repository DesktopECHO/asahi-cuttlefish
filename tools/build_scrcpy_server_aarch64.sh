#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRCPY_DIR="$ROOT_DIR/scrcpy"
BUILD_DIR="${BUILD_DIR:-$ROOT_DIR/out/build-scrcpy-server}"
ANDROID_CACHE_DIR="${ANDROID_CACHE_DIR:-$ROOT_DIR/out/android-sdk-cache}"
JDK_DIR="${JDK_DIR:-$ROOT_DIR/out/toolchain/jdk-17.0.18+8}"
R8_JAR="${R8_JAR:-$ROOT_DIR/out/toolchain/r8.jar}"

JAVA="$JDK_DIR/bin/java"
JAVAC="$JDK_DIR/bin/javac"
JAR="$JDK_DIR/bin/jar"

PLATFORM_ZIP="$ANDROID_CACHE_DIR/platform-36_r02.zip"
BUILD_TOOLS_ZIP="$ANDROID_CACHE_DIR/build-tools_r36_linux.zip"
ANDROID_JAR="$BUILD_DIR/sdk/platforms/android-36/android.jar"
LAMBDA_JAR="$BUILD_DIR/sdk/build-tools/36.0.0/core-lambda-stubs.jar"

CLASSES_DIR="$BUILD_DIR/classes"
GEN_DIR="$BUILD_DIR/gen"
SERVER_BINARY="$BUILD_DIR/scrcpy-server"

usage() {
    cat <<'EOF'
Build scrcpy-server on aarch64 Linux without relying on x86 Android host tools.

Required inputs:
  out/toolchain/jdk-17.0.18+8
  out/toolchain/r8.jar
  out/android-sdk-cache/platform-36_r02.zip
  out/android-sdk-cache/build-tools_r36_linux.zip

Optional env vars:
  BUILD_DIR
  ANDROID_CACHE_DIR
  JDK_DIR
  R8_JAR
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

for path in "$JAVA" "$JAVAC" "$JAR" "$R8_JAR" "$PLATFORM_ZIP" "$BUILD_TOOLS_ZIP"; do
    if [[ ! -e "$path" ]]; then
        echo "Missing required input: $path" >&2
        exit 1
    fi
done

rm -rf "$CLASSES_DIR" "$GEN_DIR" "$SERVER_BINARY" "$BUILD_DIR/classes.zip" "$BUILD_DIR/sdk"
mkdir -p "$CLASSES_DIR" "$GEN_DIR/com/genymobile/scrcpy" "$GEN_DIR/android/view" \
    "$BUILD_DIR/sdk/platforms/android-36" "$BUILD_DIR/sdk/build-tools/36.0.0"

unzip -oj "$PLATFORM_ZIP" 'android-36/android.jar' -d "$BUILD_DIR/sdk/platforms/android-36" >/dev/null
unzip -oj "$BUILD_TOOLS_ZIP" 'android-16/core-lambda-stubs.jar' -d "$BUILD_DIR/sdk/build-tools/36.0.0" >/dev/null

cat > "$GEN_DIR/com/genymobile/scrcpy/BuildConfig.java" <<'EOF'
package com.genymobile.scrcpy;

public final class BuildConfig {
    public static final boolean DEBUG = false;
    public static final String VERSION_NAME = "3.3.4";

    private BuildConfig() {
    }
}
EOF

cat > "$GEN_DIR/android/view/IDisplayWindowListener.java" <<'EOF'
package android.view;

import android.content.res.Configuration;
import android.os.Binder;
import android.os.IBinder;
import android.os.IInterface;
import android.os.Parcel;
import android.os.RemoteException;

public interface IDisplayWindowListener extends IInterface {
    void onDisplayAdded(int displayId) throws RemoteException;

    void onDisplayConfigurationChanged(int displayId, Configuration newConfig) throws RemoteException;

    void onDisplayRemoved(int displayId) throws RemoteException;

    abstract class Stub extends Binder implements IDisplayWindowListener {
        public Stub() {
        }

        public static IDisplayWindowListener asInterface(IBinder binder) {
            throw new UnsupportedOperationException("compile-time stub only");
        }

        @Override
        public IBinder asBinder() {
            return this;
        }

        @Override
        public boolean onTransact(int code, Parcel data, Parcel reply, int flags) throws RemoteException {
            return super.onTransact(code, data, reply, flags);
        }
    }
}
EOF

mapfile -t SRC_FILES < <(find \
    "$SCRCPY_DIR/server/src/main/java/android" \
    "$SCRCPY_DIR/server/src/main/java/com/genymobile/scrcpy" \
    "$GEN_DIR" \
    -name '*.java' | sort)

"$JAVAC" -encoding UTF-8 \
    -bootclasspath "$ANDROID_JAR" \
    -cp "$LAMBDA_JAR:$GEN_DIR" \
    -d "$CLASSES_DIR" \
    -source 8 \
    -target 8 \
    "${SRC_FILES[@]}"

mapfile -t CLASS_FILES < <(find "$CLASSES_DIR" -name '*.class' | sort)

"$JAVA" -cp "$R8_JAR" com.android.tools.r8.D8 \
    --lib "$ANDROID_JAR" \
    --min-api 21 \
    --output "$BUILD_DIR/classes.zip" \
    "${CLASS_FILES[@]}"

mv "$BUILD_DIR/classes.zip" "$SERVER_BINARY"

echo "Built $SERVER_BINARY"
"$JAR" tf "$SERVER_BINARY"
