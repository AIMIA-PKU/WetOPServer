#!/usr/bin/env python3
"""Replay Task01 LeRobot actions against a loaded local GenManip run.

This is an interface/metric diagnostic when the training trajectory and reset
seed do not share the same initial state. It is not an official success rate.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from genmanip_client import EvalClient

TASK = "task_01_pour_flask_to_cylinder"
TRAIN_ROOT = Path("/cluster/ssd/DATASETS/InternRobotics/WETOP-Bench-Train")


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def action_at(columns, index):
    joints = [float(x) for x in columns["action.joints"][index]]
    gripper = [float(x) for x in columns["action.gripper"][index]]
    base = [float(x) for x in columns["action.base"][index]]
    if len(joints) != 12 or len(gripper) != 4 or len(base) != 3:
        raise ValueError(f"Bad action dimensions at frame {index}")
    return {
        "action": joints[:6] + gripper[:2] + joints[6:] + gripper[2:],
        "base_motion": base,
        "base_is_rel": False,
        "control_type": "joint_position",
        "is_rel": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=int, default=30)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18087")
    parser.add_argument("--run-id", default="wetop_task_01")
    parser.add_argument("--initial-state-source", type=Path,
                        help="Reconstructed scene state JSON loaded by a derived task")
    parser.add_argument("--worker-id", default="0")
    parser.add_argument("--chunk-size", type=int, default=32,
                        help="1 uses individual SDK step() calls; larger values use step_chunk()")
    parser.add_argument("--max-actions", type=int, default=0,
                        help="Limit training actions for a short interface check")
    parser.add_argument("--horizon", type=int, default=3500,
                        help="Hold the last target to this step count to obtain a terminal score")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("client_results/replay_task01"))
    args = parser.parse_args()
    if args.chunk_size < 1 or args.horizon < 1:
        parser.error("chunk-size and horizon must be positive")

    task_dir = TRAIN_ROOT / TASK
    info = json.loads((task_dir / "meta/info.json").read_text())
    episode_chunk = args.episode // info["chunks_size"]
    parquet = task_dir / info["data_path"].format(
        episode_chunk=episode_chunk, episode_index=args.episode
    )
    columns = pq.read_table(
        parquet, columns=["state.joints", "state.gripper",
                          "action.joints", "action.gripper", "action.base"]
    ).to_pydict()
    total_actions = len(columns["action.joints"])
    limit = min(total_actions, args.max_actions) if args.max_actions else total_actions
    if limit == 0:
        raise ValueError("No actions selected")

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    summary = {
        "task": TASK, "train_episode": args.episode,
        "train_frames": total_actions, "selected_actions": limit,
        "train_parquet": str(parquet), "run_id": args.run_id,
        "endpoint": args.endpoint, "chunk_size": args.chunk_size,
        "initial_state_source": (str(args.initial_state_source.resolve())
                                 if args.initial_state_source else None),
        "warning": (
            "Scene state is reconstructed and must be validated against the "
            "training video; this is not an official success rate."
            if args.initial_state_source else
            "Public seed-000 does not match the training episode initial state; "
            "this is only a replay diagnostic."
        ),
        "started_at": started,
    }

    client = EvalClient(
        args.endpoint, worker_ids=[args.worker_id], run_id=args.run_id,
        save_result=True, save_process=False, verbose=False,
        reset_timeout=3000, step_timeout=600,
    )
    result = None
    done = False
    episode_terminal = False
    submitted_training = 0
    submitted_hold = 0
    last_action = action_at(columns, limit - 1)
    try:
        result = client.reset()
        worker = result[args.worker_id]
        obs = worker["obs"]
        reset_joints = np.asarray(obs["state.joints"], dtype=float)
        reset_gripper = np.asarray(obs["state.gripper"], dtype=float)
        train_joints = np.asarray(columns["state.joints"][0], dtype=float)
        train_gripper = np.asarray(columns["state.gripper"][0], dtype=float)
        summary["reset_instruction"] = obs["instruction"]
        summary["joint_initial_max_abs_diff"] = float(
            np.max(np.abs(reset_joints - train_joints))
        )
        summary["gripper_initial_max_abs_diff"] = float(
            np.max(np.abs(reset_gripper - train_gripper))
        )
        summary["robot_initial_state_match"] = (
            summary["joint_initial_max_abs_diff"] < 1e-3
            and summary["gripper_initial_max_abs_diff"] < 1e-3
        )
        print("train frames:", total_actions, flush=True)
        print("initial joint max abs diff:", summary["joint_initial_max_abs_diff"], flush=True)
        print("initial gripper max abs diff:", summary["gripper_initial_max_abs_diff"], flush=True)
        print("reset worker fields:", sorted(worker.keys()), flush=True)

        for start in range(0, limit, args.chunk_size):
            batch = [action_at(columns, i) for i in range(
                start, min(limit, start + args.chunk_size)
            )]
            if len(batch) == 1:
                result, done = client.step({args.worker_id: batch[0]})
            else:
                result, done = client.step_chunk(
                    [{args.worker_id: action} for action in batch]
                )
            episode_terminal = result[args.worker_id].get("episode_result") is not None
            submitted_training += len(batch)
            if submitted_training % 128 < len(batch) or done or episode_terminal:
                print("training submitted:", submitted_training,
                      "executed:", client.step_count,
                      "episode_terminal:", episode_terminal, flush=True)
            if done or episode_terminal:
                break

        while not done and not episode_terminal and client.step_count < args.horizon:
            count = min(args.chunk_size, args.horizon - client.step_count)
            batch = [last_action] * count
            if count == 1:
                result, done = client.step({args.worker_id: last_action})
            else:
                result, done = client.step_chunk(
                    [{args.worker_id: action} for action in batch]
                )
            episode_terminal = result[args.worker_id].get("episode_result") is not None
            submitted_hold += count
            if client.step_count % 128 < count or done or episode_terminal:
                print("hold submitted:", submitted_hold,
                      "executed:", client.step_count,
                      "episode_terminal:", episode_terminal, flush=True)

        worker = result.get(args.worker_id, {}) if isinstance(result, dict) else {}
        summary.update({
            "training_actions_submitted": submitted_training,
            "hold_actions_submitted": submitted_hold,
            "executed_steps": client.step_count,
            "client_done": bool(done),
            "episode_terminal": bool(episode_terminal),
            "worker_fields": sorted(worker.keys()),
            "metric": clean(worker.get("metric")),
            "episode_result": clean(worker.get("episode_result")),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["executed_steps"] = client.step_count
        raise
    finally:
        client.close()
        path = output / f"task01_ep{args.episode:06d}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n")
        print("summary:", path, flush=True)


if __name__ == "__main__":
    main()
