#!/usr/bin/env python3
"""Build a separate GenManip reset state for Task01 train episode 30.

The LeRobot first frame supplies robot state. Vessel and liquid state comes
from the separately delivered reconstructed Task01 episode JSON; those fields
cannot be recovered from the LeRobot Parquet alone.
"""

import copy
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
TASK = "task_01_pour_flask_to_cylinder"
SOURCE = ROOT / "app/configs/initial_states/task01/train_ep30.json"
TRAIN = Path(
    "/cluster/ssd/DATASETS/InternRobotics/WETOP-Bench-Train/"
    "task_01_pour_flask_to_cylinder/data/chunk-000/episode_000030.parquet"
)
PUBLIC_META = (
    ROOT / "app/saved/tasks/scientific_experiments" / TASK
    / "validation_mixed_1/000/meta_info.pkl"
)
OUTPUT_DIR = (
    ROOT / "app/derived_tasks/scientific_experiments" / TASK
    / "train_ep30/000"
)
LEFT_ARM = [10, 12, 14, 16, 18, 20]
LEFT_GRIPPER = [23, 24]
RIGHT_ARM = [9, 11, 13, 15, 17, 19]
RIGHT_GRIPPER = [21, 22]


def main() -> None:
    source = json.loads(SOURCE.read_text())
    if source.get("source_episode") != 30:
        raise ValueError("Source JSON is not Task01 train episode 30")
    first = pq.read_table(
        TRAIN, columns=["state.joints", "state.gripper", "state.base"]
    ).slice(0, 1).to_pydict()
    joints = np.asarray(first["state.joints"][0], dtype=np.float32)
    gripper = np.asarray(first["state.gripper"][0], dtype=np.float32)
    base = np.asarray(first["state.base"][0], dtype=np.float32)
    if joints.shape != (12,) or gripper.shape != (4,) or base.shape != (3,):
        raise ValueError("Unexpected LeRobot first-frame state dimensions")

    q = np.asarray(source["robot"]["joint_positions"], dtype=np.float32)
    if q.shape != (25,):
        raise ValueError("Expected 25 Lift2 articulation joints in source JSON")
    reconstructed = np.concatenate(
        [q[LEFT_ARM], q[RIGHT_ARM], q[LEFT_GRIPPER], q[RIGHT_GRIPPER], q[:3]]
    )
    observed = np.concatenate([joints, gripper, base])
    source_max_abs_diff = float(np.max(np.abs(reconstructed - observed)))
    q[:3] = base
    q[LEFT_ARM], q[RIGHT_ARM] = joints[:6], joints[6:]
    q[LEFT_GRIPPER], q[RIGHT_GRIPPER] = gripper[:2], gripper[2:]

    with PUBLIC_META.open("rb") as handle:
        meta = copy.deepcopy(pickle.load(handle))
    layout = meta["task_data"]["initial_layout"]
    robot = source["robot"]
    layout["lift2"]["position"] = robot["position"]
    layout["lift2"]["orientation"] = robot["orientation"]
    layout["lift2"]["joint_positions"] = q

    for uid in ("conical_flask", "graduated_cylinder"):
        obj = source["objects"][uid]
        if obj["prim_path"] != layout[uid]["prim_path"]:
            raise ValueError(f"Prim path mismatch for {uid}")
        for key in ("position", "orientation", "scale"):
            layout[uid][key] = obj[key]

    particles = source["particles"]
    if len(particles) != 1:
        raise ValueError("Expected one Task01 liquid particle set")
    target_particles = meta["task_data"]["initial_particle_states"]["0"]
    if particles[0]["prim_path"] != target_particles["prim_path"]:
        raise ValueError("Liquid prim path mismatch")
    points = np.asarray(particles[0]["points"], dtype=np.float32)
    if points.shape != (1535, 3):
        raise ValueError(f"Unexpected liquid particle array: {points.shape}")
    target_particles["points"] = points

    meta["task_data"]["instruction"] = source["instruction"]
    meta["language_instruction"] = source["instruction"]
    meta["episode_name"] = (
        f"scientific_experiments/{TASK}/train_ep30/000"
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "meta_info.pkl"
    with output.open("wb") as handle:
        pickle.dump(meta, handle, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {
        "episode": 30,
        "robot_source": str(TRAIN),
        "object_and_liquid_source": str(SOURCE),
        "object_and_liquid_provenance": source["_source"],
        "source_json_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "train_parquet_sha256": hashlib.sha256(TRAIN.read_bytes()).hexdigest(),
        "reconstructed_robot_max_abs_diff_before_override": source_max_abs_diff,
        "liquid_particle_count": len(points),
        "output": str(output),
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
