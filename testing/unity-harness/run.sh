#!/usr/bin/env bash
# Builds the harness in a fresh copy of the tree, and runs a desktop player against a live
# gateway with the mock adapter and the scripted server. With editor-playmode it builds nothing,
# and proves in the Editor that a client does not outlive Play Mode. See README.md.
#
# usage: run.sh <new-folder> <editor-version> <linux-il2cpp|linux-mono|android|editor-playmode>
#
# OPENROIS_VENV    virtual environment with openrois-gateway and the components (desktop, Editor)
# OPENROIS_GATEWAY_URL    the address a device uses to reach the gateway (android)
# OPENROIS_SCRIPTED_URL    the address a device uses to reach the scripted server (android)
# UNITY_EDITORS    where the Editors are, by default ~/Unity/Hub/Editor
set -euo pipefail

if [ "$#" -ne 3 ]; then
  sed -n 2,11p "$0" >&2
  exit 2
fi
work=$1
editor=${UNITY_EDITORS:-$HOME/Unity/Hub/Editor}/$2/Editor/Unity
target=$3
repo=$(cd "$(dirname "$0")/../.." && pwd)
project=$work/testing/unity-harness

case "$target" in
  linux-il2cpp | linux-mono)
    build_target=Linux64
    output=$work/player/harness.x86_64
    : "${OPENROIS_VENV:?needs the virtual environment that holds the gateway}"
    ;;
  android)
    build_target=Android
    output=$work/player/harness.apk
    : "${OPENROIS_GATEWAY_URL:?needs the address a device uses to reach the gateway}"
    : "${OPENROIS_SCRIPTED_URL:?needs the address a device uses to reach the scripted server}"
    ;;
  editor-playmode)
    build_target=Linux64
    : "${OPENROIS_VENV:?needs the virtual environment that holds the gateway}"
    ;;
  *)
    echo "Unknown target: $target" >&2
    exit 2
    ;;
esac

# Unity writes .meta files and a Library folder into a file: package, so it only ever opens
# a copy. mkdir without -p refuses a folder that exists, which keeps every run fresh.
mkdir -p "$(dirname "$work")"
mkdir "$work"
mkdir "$work/testing" "$work/testing/conformance" "$work/sdk" "$work/interfaces" "$work/player"
cp -R "$repo/testing/unity-harness" "$work/testing/"
cp -R "$repo/sdk/unity" "$work/sdk/"
cp -R "$repo/interfaces/fixtures" "$work/interfaces/"
cp "$repo/testing/conformance/README.md" "$work/testing/conformance/"

# With no version file Unity takes the copy for a new project and adds its default packages
# to the manifest, and the player would no longer be the minimal project in this folder.
mkdir "$project/ProjectSettings"
echo "m_EditorVersion: $2" >"$project/ProjectSettings/ProjectVersion.txt"

free_port() {
  "$OPENROIS_VENV/bin/python" -c \
    'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

# Each server is stopped by its own process id, whichever way this script ends.
servers=()
trap 'kill "${servers[@]}" 2>/dev/null || true' EXIT

start_stack() {
  local port
  port=$(free_port)
  url=ws://127.0.0.1:$port
  "$OPENROIS_VENV/bin/openrois-gateway" --port "$port" --log-level warning >"$work/gateway.log" 2>&1 &
  servers+=("$!")
  "$OPENROIS_VENV/bin/python" "$repo/testing/mock-adapter/mock_adapter.py" \
    --config "$repo/testing/mock-adapter/adapter.fast.yaml" --gateway-url "$url" >"$work/adapter.log" 2>&1 &
  servers+=("$!")
}

if [ "$target" = editor-playmode ]; then
  start_stack
  peer_port=$(free_port)
  record=$work/lifecycle.record
  "$OPENROIS_VENV/bin/python" "$repo/testing/unity-harness/lifecycle_server.py" \
    --port "$peer_port" --record "$record" >"$work/lifecycle.log" 2>&1 &
  servers+=("$!")

  # A hang inside the Editor stops the pump that would report it, so the limit is out here.
  # It covers the first import of the packages as well.
  echo "editor: Play Mode with domain reload off on $2 in $work"
  status=0
  OPENROIS_GATEWAY_URL=$url OPENROIS_LIFECYCLE_URL=ws://127.0.0.1:$peer_port OPENROIS_LIFECYCLE_RECORD=$record \
    timeout --kill-after=30 900 "$editor" -batchmode -nographics -buildTarget "$build_target" \
    -projectPath "$project" \
    -executeMethod OpenRoIS.Harness.Editor.HarnessPlayMode.Run \
    -logFile "$work/playmode.log" || status=$?
  grep '^HARNESS ' "$work/playmode.log" || true
  echo "editor exit code $status"
  exit "$status"
fi

echo "build: $target on $2 in $work"
status=0
OPENROIS_HARNESS_TARGET=$target OPENROIS_HARNESS_OUTPUT=$output \
  "$editor" -batchmode -nographics -buildTarget "$build_target" \
  -projectPath "$project" \
  -executeMethod OpenRoIS.Harness.Editor.HarnessBuild.Run \
  -logFile "$work/build.log" || status=$?
grep '^HARNESS BUILD' "$work/build.log" || true
if [ "$status" -ne 0 ]; then
  echo "build failed with exit code $status, see $work/build.log" >&2
  exit "$status"
fi
if [ "$target" = android ]; then
  echo "built $output for $OPENROIS_GATEWAY_URL and $OPENROIS_SCRIPTED_URL"
  exit 0
fi

start_stack
scripted_port=$(free_port)
"$OPENROIS_VENV/bin/python" "$repo/testing/conformance/scripted_server.py" \
  --port "$scripted_port" >"$work/scripted.log" 2>&1 &
servers+=("$!")

status=0
OPENROIS_GATEWAY_URL=$url OPENROIS_SCRIPTED_URL=ws://127.0.0.1:$scripted_port \
  "$output" -batchmode -nographics -logFile "$work/player.log" \
  >"$work/player.stdout" 2>&1 || status=$?
grep '^HARNESS ' "$work/player.log" || true
echo "player exit code $status"
exit "$status"
