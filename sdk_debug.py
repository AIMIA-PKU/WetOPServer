#!/usr/bin/env python3
"""Minimal local task_01_pour_flask_to_cylinder example: reset, read the returned observation, and optionally step."""

import argparse
import os
from time import perf_counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from genmanip_client import EvalClient, fake_action

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-id", default="wetop_task_01")
parser.add_argument("--step", action="store_true", help="Run one example action after reset")
args = parser.parse_args()

output = Path(os.environ.get("GENMANIP_RESULT_DIR", "client_results")).expanduser().resolve() / "sdk_debug"
output /= datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
output.mkdir(parents=True, exist_ok=True)

client = EvalClient(
    "http://127.0.0.1:18087",
    worker_ids=["0"],
    run_id=args.run_id,
    save_result=False,
    save_process=False,
    verbose=False,
    reset_timeout=3000,
    step_timeout=600,
)
try:
    # 1. SDK reset(): load seed 000 and return the first observation.
    print("Calling reset() (cold start may take several minutes)...", flush=True)
    result = client.reset()

    # 2. There is no SDK get_obs() call. Read the observation returned by reset().
    obs = result["0"]["obs"]
    print("instruction:", obs["instruction"])
    print("state.joints:", obs["state.joints"])
    print("state.gripper:", obs["state.gripper"])
    print("state.base:", obs["state.base"])
    for key, frame in obs.items():
        if key.startswith("video."):
            Image.fromarray(frame).save(output / f"reset_{key[6:]}.png")
            print(key, frame.shape)

    if args.step:
        # 3. SDK step(): one example action, then read its new observation.
        action = fake_action("r5a", "lift2", "joint_position")
        step_start = perf_counter()
        result, done = client.step({"0": action})
        print("step wall time (s):", round(perf_counter() - step_start, 3))
        obs = result["0"]["obs"]
        print("done:", done)
        print("next state.joints:", obs["state.joints"])
        for key, frame in obs.items():
            if key.startswith("video."):
                Image.fromarray(frame).save(output / f"step_{key[6:]}.png")
                print(key, frame.shape)
finally:
    client.close()

print("Images saved to:", output)
