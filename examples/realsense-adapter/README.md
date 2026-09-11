# realsense-adapter

OpenRoIS adapter for the ROS 2 perception pipeline
(`realsense2_camera` + `yolo_person_perception`). Registers the three
canonical RoIS camera components and publishes the pipeline output as
RoIS events:

| RoIS component | Source topic | Event |
|---|---|---|
| PersonDetection | `/person_detection/count` | `person_detected` |
| PersonLocalization | `/person_tracks` | `person_localized` |
| PersonIdentification | `/person_tracks` | `person_identified` |

## Prerequisites

1. ROS 2 (Jazzy) environment sourced — the adapter imports `rclpy`,
   `vision_msgs`, and `tf2_ros` at connect() time.
2. The OpenRoIS Python packages installed in the same environment:

       pip install -e core -e components/core -e components/realsense

3. The perception pipeline running (see `~/ros2_ws/run_perception.sh`),
   or stopped — the adapter works either way; events simply do not fire
   when the pipeline is down.

## Run

### One-shot demo (recommended)

`run_demo.sh` starts everything (gateway, adapter, ROS 2 pipeline,
client demo) in one command and stops them all on exit:

```bash
./run_demo.sh                 # Ctrl+C stops the client; everything shuts down
./run_demo.sh --duration 30   # auto-exit after 30 s
./run_demo.sh --rviz          # also start RViz2 for /segmentation/mask
./run_demo.sh --no-client     # background services only
```

The client demo prints the person count, 3D positions, and tracking
IDs live, plus event rates every 10 s.

### Manual startup (one terminal each)

```bash
# Terminal 1: start the gateway
cd ../gateway && python gateway.py

# Terminal 2: start the adapter
python realsense_adapter.py --config openrois-profile.yaml

# Terminal 3: start the ROS 2 pipeline
~/ros2_ws/run_perception.sh ros2 launch perception_bringup perception_bringup.launch.py

# Terminal 4: run the client demo
python demo_client.py ws://127.0.0.1:8765
```

## Verify

1. With the ROS 2 pipeline **stopped**: connect the hri-client
   (`examples/hri-client`) to `ws://localhost:8765` and confirm the
   three components appear in the search results and that `bind` /
   `start` succeed. This validates the wiring.
2. With the ROS 2 pipeline **running**: subscribe to `person_detected`,
   `person_localized`, and `person_identified` and confirm events
   arrive (~12 Hz). This validates the data path.

## Configuration

See `openrois-profile.yaml.example`. Topic names and TF frames are
per-component config entries — nothing is hardcoded.

| Key | Component | Default | Meaning |
|---|---|---|---|
| `person_count_topic` | PersonDetection | `/person_detection/count` | Count topic |
| `person_tracks_topic` | PersonLocalization, PersonIdentification | `/person_tracks` | Tracks topic |
| `person_tracks_frame` | PersonLocalization | `camera_color_optical_frame` | Source TF frame |
| `person_position_frame` | PersonLocalization | `camera_link` | Target TF frame |

## Notes

- Positions are transformed from the camera optical frame into
  `camera_link` (REP-103 body convention) using `/tf_static`.
- Tracking IDs are session-scoped: they reset when the perception
  pipeline restarts and may switch under occlusion. Do not treat them
  as persistent personal identities.