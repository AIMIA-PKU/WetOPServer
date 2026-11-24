# app：场景、任务与文件结构

这里是 GenManip 的工作目录。服务入口 `ray_eval_server.py` 以本目录作为 `current_dir`，因此下列相对路径均相对于 `app/`。启动服务和 SDK 调用方法见项目根的 [README](../README.md)。

## 当前目录

```text
app/
├── ray_eval_server.py       # GenManip 服务入口
├── ray_server.sh            # 手动启动服务
├── task01_submit.sh         # 加载当前公开 task_01 示例
├── configs/
│   ├── tasks/               # 每个任务的 YAML；提交任务时引用这里的相对路径
│   │   └── scientific_experiments/task_01_pour_flask_to_cylinder/
│   │       └── validation/mixed/mixed_1.yml
│   ├── cameras/             # 相机位姿和内参 YAML
│   ├── robots/              # 机器人相关配置
│   └── miscs/               # 其他运行配置
├── assets/objects/          # GenManip 使用的对象元数据
├── saved/
│   ├── assets -> /cluster/ssd/DATASETS/InternRobotics/WETOP-Bench-Validation/saved/assets
│   ├── tasks  -> /cluster/ssd/DATASETS/InternRobotics/WETOP-Bench-Validation/saved/tasks
│   ├── diagnostics/         # 历史调试图片（新输出在项目根 client_results）
│   ├── demonstrations/      # 演示生成输出
│   └── eval_results/        # 评测进度与结果
└── logs/                    # server/worker 日志
```

## 一个任务如何关联文件

以 `task_01_pour_flask_to_cylinder` 为例：

| 文件或字段 | 作用 |
| --- | --- |
| `configs/tasks/scientific_experiments/task_01_pour_flask_to_cylinder/validation/mixed/mixed_1.yml` | 任务入口；包含场景、机器人、相机、物理、步数与 seed 数量等配置 |
| YAML `usd_name: scene_usds/scientific_experiments/task_01_pour_flask_to_cylinder/public_validation/scene` | 从 `saved/assets/` 下加载对应的 `scene.usda`，该层再引用场景 USD 等资源 |
| YAML `robots[].usd_path: robot_usds/lift2_scientific_experiments/robot.usd` | 从 `saved/assets/` 下加载 R5a 机器人 USD；`robots[].type` 指定控制实现 |
| YAML `domain_randomization.cameras.config_path` | 指向 `configs/cameras/fixed_camera_lift2_scientific_experiments.yml` |
| YAML `task_name: scientific_experiments/task_01_pour_flask_to_cylinder/validation_mixed_1` | 对应 `saved/tasks/<task_name>/` 下的初态目录 |
| `saved/tasks/scientific_experiments/task_01_pour_flask_to_cylinder/validation_mixed_1/000/meta_info.pkl` | seed `000` 的初态和任务信息；不是 USD 资产清单 |
| `assets/objects/` | GenManip 读取的对象注释和关节物体元数据 |

YAML 中的 `num_test: 1` 表示当前示例使用一个 seed。场景 USD 定义几何、材质和物理对象；`meta_info.pkl` 提供该 seed 的摆放、机器人状态、指令等初态信息。仅添加 USD 而没有与之匹配的初态和任务配置，不能完成 `reset()`。

## 添加新的场景和任务

1. 在 `saved/assets/scene_usds/<benchmark>/<task>/<variant>/` 放场景 `scene.usda`、其引用的 USD、贴图和材质；检查所有引用在容器内都能解析。可复用已有机器人 USD 和控制类型；新机器人需要相应控制实现，不能只添加 USD。
2. 若需新相机，在 `configs/cameras/` 放相机 YAML，并在任务 YAML 的 `domain_randomization.cameras.config_path` 中引用。
3. 在 `saved/tasks/<benchmark>/<task>/<split_variant>/000/meta_info.pkl` 放与场景 prim 名称和任务逻辑一致的 seed 初态。更多 seed 使用 `001`、`002` 等目录，并调整 YAML 的 `num_test`。
4. 复制当前 `mixed_1.yml` 到 `configs/tasks/<benchmark>/<task>/.../`，在新文件中修改 `usd_name`、`task_name`、机器人、相机、评测参数和步骤限制。保留现有官方 task_01 YAML 原样。
5. 按项目根 README 的 `genmanip_client submit` 命令提交新 YAML，再用 SDK `reset()` 检查初态与四路观测，最后用 `step()` 检查动作和终止条件。新任务若需新的评分或成功判据，还必须实现 GenManip 能调用的对应任务逻辑。

当前两条软链直接指向下载的 Validation 数据；在 `saved/assets` 或 `saved/tasks` 下新增文件，会写入该 SSD 数据目录。`diagnostics/`、`demonstrations/`、`eval_results/` 和 `logs/` 留在 HDD，不会写入 Validation 数据。

## 已归档的重建任务 YAML

构建方提供的 17 份 YAML 已原样放在 configs/tasks/scientific_experiments/对应任务/rebuilt/ 下，覆盖 Task02–07、Task13、Task16（z2）和 Task20（z6）。官方 Task01 YAML 保持原样。

这些配置的场景入口和 seed 初态尚未就位；目前不能用它们完成 reset。Task08、09、10、11、12、14、15（z1）、17（z3）、18（z4）、19（z5）未提供 YAML，未创建占位配置。
