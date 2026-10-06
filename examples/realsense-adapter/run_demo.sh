#!/usr/bin/env bash
# run_demo.sh — RealSense × OpenRoIS デモを一括起動する
#
# 起動するもの:
#   1. OpenRoIS Gateway        (examples/gateway/gateway.py)
#   2. RealSense アダプタ      (examples/realsense-adapter/realsense_adapter.py)
#   3. ROS2 知覚パイプライン   (perception_bringup: カメラ + YOLO人物検知 + FastSAM)
#   4. RoIS クライアントデモ   (demo_client.py: 人数/3D位置/追跡IDをライブ表示)
#
# 使い方:
#   ./run_demo.sh                 # クライアントは Ctrl+C で終了、残りも順次停止
#   ./run_demo.sh --duration 30   # 30秒で自動終了
#   ./run_demo.sh --no-client     # Gateway/アダプタ/パイプラインのみ起動
#   ./run_demo.sh --rviz          # RViz2 も起動 (/segmentation/mask の可視化)
#
# 停止:
#   クライアントを Ctrl+C すると、Gateway・アダプタ・パイプラインも
#   まとめて停止します（trap で後始末）。カメラが次回起動時に
#   VIDIOC_S_FMT エラーで失敗する場合は pkill -9 -f realsense2_camera_node。

set -euo pipefail

# ---------------------------------------------------------------- paths
OPENROIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADAPTER_DIR="$OPENROIS_DIR/examples/realsense-adapter"
GATEWAY_DIR="$OPENROIS_DIR/examples/gateway"
VENV_PY="$HOME/ros2_ws/.venv/bin/python3"
ROS2_WS="$HOME/ros2_ws"

# ---------------------------------------------------------------- args
# --duration N | --duration=N | bare N all set the client auto-exit time.
DURATION=""
RUN_CLIENT=1
RUN_RVIZ=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --duration)
            [[ $# -ge 2 ]] || { echo "ERROR: --duration requires a value" >&2; exit 2; }
            DURATION="$2"; shift 2;;
        --duration=*)
            DURATION="${1#--duration=}"; shift;;
        [0-9]*)
            DURATION="$1"; shift;;
        --no-client)
            RUN_CLIENT=0; shift;;
        --rviz)
            RUN_RVIZ=1; shift;;
        *)
            echo "unknown option: $1 (use --duration N | --no-client | --rviz)" >&2; exit 2;;
    esac
done

# ---------------------------------------------------------------- checks
fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -x "$VENV_PY" ]] || fail "venv python not found: $VENV_PY"
[[ -f "$GATEWAY_DIR/gateway.py" ]] || fail "gateway.py not found — run inside the openrois repo"
[[ -f "$ADAPTER_DIR/realsense_adapter.py" ]] || fail "realsense_adapter.py not found"
[[ -f "$ROS2_WS/run_perception.sh" ]] || fail "run_perception.sh not found: $ROS2_WS"
[[ -f "$ADAPTER_DIR/openrois-profile.yaml" ]] || \
    { cp "$ADAPTER_DIR/openrois-profile.yaml.example" "$ADAPTER_DIR/openrois-profile.yaml"
      echo "created openrois-profile.yaml from example"; }

"$VENV_PY" -c "import openrois_core, openrois_components.realsense" 2>/dev/null || \
    fail "openrois packages not installed in venv — run: $VENV_PY -m pip install -e $OPENROIS_DIR/interfaces/python -e $OPENROIS_DIR/core -e $OPENROIS_DIR/components/core -e $OPENROIS_DIR/components/realsense"

# RealSense camera check: the D435 overheats and drops off the USB bus
# when run repeatedly. Refuse to start the pipeline if it is missing so
# we never spin up the launch stack against a dead camera.
if ! lsusb | grep -q "8086:0b07"; then
    fail "RealSense D435 not found on the USB bus (8086:0b07).
  The camera may have overheated and dropped off the bus.
  Let it cool down, reconnect the USB cable, and verify with:  lsusb | grep 8086"
fi

# ---------------------------------------------------------------- cleanup
PIDS=()
CLIENT_PID=""
LOG_DIR="/tmp/openrois-demo"
mkdir -p "$LOG_DIR"
PIPELINE_LOG="$LOG_DIR/pipeline.log"
ADAPTER_LOG="$LOG_DIR/adapter.log"
GATEWAY_LOG="$LOG_DIR/gateway.log"
cleanup() {
    # guard against double invocation (EXIT trap fires again after INT)
    [[ -n "${CLEANED_UP:-}" ]] && return 0
    CLEANED_UP=1
    echo ""
    echo "--- stopping demo ---"
    # SIGINT the foreground client first so it exits promptly
    [[ -n "${CLIENT_PID:-}" ]] && kill -INT "$CLIENT_PID" 2>/dev/null || true
    for pid in "${PIDS[@]:-}"; do
        kill "$pid" 2>/dev/null || true
    done
    # wait briefly, then force-kill leftovers
    sleep 2
    for pid in "${PIDS[@]:-}"; do
        kill -9 "$pid" 2>/dev/null || true
    done
    # camera device can stay occupied if the driver lingers
    pkill -9 -f realsense2_camera_node 2>/dev/null || true
    echo "demo stopped. logs: $GATEWAY_LOG $ADAPTER_LOG $PIPELINE_LOG"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# ---------------------------------------------------------------- launch
echo "=== 1/4 OpenRoIS Gateway ==="
( cd "$GATEWAY_DIR" && exec "$VENV_PY" gateway.py --host 127.0.0.1 --port 8765 \
  > "$GATEWAY_LOG" 2>&1 ) &
PIDS+=($!)
sleep 1

echo "=== 2/4 RealSense adapter ==="
# NOTE: ROS 2 setup.bash references unset variables (AMENT_TRACE_SETUP_FILES),
# which aborts under `set -u`. Relax it around the source, then restore.
(
    set +u
    cd "$ADAPTER_DIR"
    source /opt/ros/jazzy/setup.bash
    set -u
    exec "$VENV_PY" realsense_adapter.py --config openrois-profile.yaml \
        > "$ADAPTER_LOG" 2>&1
) &
PIDS+=($!)

# wait for the adapter to register with the gateway (max 15 s)
for _ in $(seq 1 30); do
    if "$VENV_PY" - <<'EOF' 2>/dev/null
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": "1",
                                  "method": "rois.command.search", "params": {}}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        refs = msg["result"]["component_ref_list"]
        assert "realsense-1/PersonDetection" in refs, refs
asyncio.run(main())
EOF
    then
        echo "adapter registered: PersonDetection / PersonLocalization / PersonIdentification"
        break
    fi
    sleep 0.5
done

echo "=== 3/4 ROS2 perception pipeline (camera + YOLO + FastSAM) ==="
# run_perception.sh sources ROS 2 setup files too — same set -u caveat.
# Pipeline logs go to a file so the demo output stays readable.
(
    set +u
    exec "$ROS2_WS/run_perception.sh" \
        ros2 launch perception_bringup perception_bringup.launch.py \
        > "$PIPELINE_LOG" 2>&1
) &
PIDS+=($!)

# wait for the person topics to appear (max 30 s: model load + camera start)
echo -n "waiting for /person_detection/count"
for _ in $(seq 1 60); do
    if ( set +u; "$ROS2_WS/run_perception.sh" ros2 topic list 2>/dev/null; ) | grep -q '^/person_detection/count$'; then
        echo " found"
        break
    fi
    echo -n "."
    sleep 0.5
done
echo ""

if [[ $RUN_RVIZ -eq 1 ]]; then
    echo "=== RViz2 (/segmentation/mask) ==="
    (
        set +u
        exec "$ROS2_WS/run_perception.sh" rviz2
    ) &
    PIDS+=($!)
    echo "RViz2: Add -> By topic -> /segmentation/mask -> Image"
    echo "       (set Reliability Policy = Best Effort on the Image display)"
fi

if [[ $RUN_CLIENT -eq 1 ]]; then
    echo "=== 4/4 RoIS client demo ==="
    if [[ -n "$DURATION" ]]; then
        "$VENV_PY" "$ADAPTER_DIR/demo_client.py" ws://127.0.0.1:8765 --duration "$DURATION" &
    else
        "$VENV_PY" "$ADAPTER_DIR/demo_client.py" ws://127.0.0.1:8765 &
    fi
    CLIENT_PID=$!
    wait "$CLIENT_PID" || true
else
    echo "=== all background services up (Ctrl+C to stop everything) ==="
    wait
fi

echo "demo finished."