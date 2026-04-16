# TextCAD

面向论文原型的 Text2CAD 单机研究系统。当前仓库只实现左侧生产链路：

1. 用户自然语言需求进入 LangGraph 编排图
2. `Clarify / Engineer / Design / QA` 节点负责规格澄清、结构化生成与反馈回路
3. 本地工具链复用已跑通的 `CadQuery -> Gmsh -> SfePy -> PyVista`
4. 右侧 `Math` 评测与微调模块暂不纳入本轮实现

## 环境准备

推荐沿用你已经验证过的 `textcad-mvp` 环境：

```bash
conda create -n textcad-mvp python=3.11 -y
conda activate textcad-mvp
pip install -e ".[dev]"
```

如果你希望显式保留此前的安装方式，也可以先安装底层几何/仿真依赖，再安装本项目：

```bash
conda install -c conda-forge cadquery=2.7 -y
python -m pip install gmsh sfepy pyvista "meshio[all]"
python -m pip install -e ".[dev]"
```

## 环境变量

复制 `.env.example` 为 `.env`，按需填写：

```bash
cp .env.example .env
```

如果你只是想快速切实验配置，也可以直接复制现成模板：

```bash
cp configs/providers/qwen.env .env
```

- 不填任何模型凭证时，系统会自动退回 heuristic/mock 模式，适合本地结构验证
- 默认内置模型是 OpenAI；填写 `OPENAI_API_KEY` 后，`Clarify / Design / Visual QA` 会优先使用真实模型
- 现在支持“多提供商、分角色”配置：可以给 `Clarify / Design / Visual QA` 分别指定不同模型，也可以统一切到 OpenAI-compatible 端点

### Qwen 示例

如果你想把三个角色统一切到 Qwen（经 DashScope OpenAI-compatible 接口），可以这样配置：

```bash
TEXTCAD_DEFAULT_MODEL=qwen-max
TEXTCAD_DEFAULT_PROVIDER=openai
TEXTCAD_DEFAULT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TEXTCAD_DEFAULT_API_KEY=your-dashscope-key
```

如果你想混合使用不同模型，例如：

- `Clarify` 用 `qwen-plus`
- `Design` 用 `qwen-max`
- `Visual QA` 继续用 OpenAI 多模态模型

可以这样写：

```bash
TEXTCAD_CLARIFY_MODEL=qwen-plus
TEXTCAD_CLARIFY_PROVIDER=openai
TEXTCAD_CLARIFY_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TEXTCAD_CLARIFY_API_KEY=your-dashscope-key

TEXTCAD_DESIGN_MODEL=qwen-max
TEXTCAD_DESIGN_PROVIDER=openai
TEXTCAD_DESIGN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TEXTCAD_DESIGN_API_KEY=your-dashscope-key

OPENAI_API_KEY=your-openai-key
TEXTCAD_VISUAL_MODEL=openai:gpt-4.1-mini
```

如果你使用 `qwen3.6-plus` 做视觉审查，建议再补这几个稳定性参数：

```bash
TEXTCAD_VISUAL_TIMEOUT_S=60
TEXTCAD_VISUAL_MAX_IMAGES=3
TEXTCAD_VISUAL_MAX_PIXELS=1310720
```

- `TEXTCAD_VISUAL_TIMEOUT_S`：视觉调用超时时间，默认已经放宽到 60 秒
- `TEXTCAD_VISUAL_MAX_IMAGES`：单次视觉审查最多发送的截图数量，默认 3 张
- `TEXTCAD_VISUAL_MAX_PIXELS`：发送给 DashScope/Qwen 的单张图像像素上限，用于降低延迟和 token 开销

如果使用 Anthropic，也可以直接设置前缀模型名或 provider，例如：

```bash
ANTHROPIC_API_KEY=your-anthropic-key
TEXTCAD_DESIGN_MODEL=anthropic:claude-sonnet-4-5
```

## 目录结构

```text
textcad_agent/
  state.py       # schema 与 LangGraph state
  tools.py       # 本地执行工具与运行目录管理
  nodes.py       # graph node 逻辑
  agent.py       # graph 构建入口
mvp/
  1_build_cad.py
  2_build_mesh.py
  3_solve_fea.py
runs/
  <run_id>/<iteration>/
```

## 使用方式

最小调用示例：

```python
from textcad_agent.agent import create_agent

app = create_agent()
result = app.invoke(
    {
        "user_prompt": "设计一个长 20mm、宽 40mm、高 40mm 的悬臂梁，左端固定，右端承受向下 1N 载荷。"
    }
)

print(result["final_status"])
print(result["feedback_history"])
```

现在更推荐直接输入自由文本产品需求，而不是先手工拆工程字段，例如：

```bash
textcad-run --json "我要一个桌面手机支架，适合竖放看视频，结构尽量简洁，方便 3D 打印。"
```

命令行方式更适合论文实验记录：

```bash
textcad-run "设计一个长 20mm、宽 40mm、高 40mm 的悬臂梁，左端固定，右端承受向下 1N 载荷。"
```

默认情况下，每次 `textcad-run` 都会使用新的 `thread_id`，避免不同命令之间串联上一次的反馈历史。只有在你显式传入 `--thread-id` 时，才会复用同一条 LangGraph 线程。

如果你想保留完整状态输出，便于实验日志落档：

```bash
textcad-run --json "设计一个带孔支架，要求右端受向下 5N 载荷。"
```

推荐的 provider 切换流程：

```bash
cp configs/providers/openai.env .env
textcad-run "设计一个测试梁"

cp configs/providers/qwen.env .env
textcad-run "设计一个测试梁"

cp configs/providers/hybrid.env .env
textcad-run "设计一个测试梁"
```

运行过程中，每一轮都会写入 `runs/<run_id>/<iteration>/`，其中包含：

- `generated_model.py`
- `analysis_config.json`
- `engineering_prompt.txt`
- `design_request.txt`
- `revision_brief.txt`
- `physics_report.txt`
- `physics_review.json`
- `visual_review.json`
- `model.step`
- `model.stl`
- `model.msh`
- `fea_result.vtk`
- `renders/*.png`

## 执行流程

接收到用户需求后，系统按下面的顺序执行：

1. `ingest_request`
   - LangGraph 初始化一次运行的 `run_id`、`iteration`、`feedback_history` 和空工具日志。
   - 后续每一轮迭代都写入 `runs/<run_id>/<iteration>/`。

2. `clarify_spec`
   - 先调用 `Clarify` 角色模型，把自然语言需求转成 `ClarifiedSpec`。
   - 同时把首轮需求整理成稳定的 `engineering_prompt`，作为整个 run 的工程基线说明。
   - 当前更偏向“自由需求理解”而不是“工程表单填写”：像“我要一个手机支架”“做一个收纳托盘”这样的输入也可以直接进入后续生成。
   - 请求里会带独立的 system prompt，并要求模型返回 `json object`。
   - 当前实现不会直接相信 provider 的结构化解析器，而是先取原始文本，再做 `JSON -> 容错字段映射 -> Pydantic 校验`。
   - 这一步兼容 OpenAI-compatible 返回的近似 JSON，例如额外字段、嵌套字段名不一致等情况。
   - 如果模型超时、返回非法 JSON、字段不合格，系统会自动退回 heuristic 规则解析，不会直接中断整条链路。
   - 默认会优先自动补全尺寸、支撑语义和试探性分析参数，而不是因为缺少工程字段就打回用户。

3. `engineer_spec`
   - 把澄清后的规格整理成当前 `mvp/` 后端能消费的 `backend_config`。
   - 这里会把边界盒进一步转成 `fixed_x / load_x / bbox_tol / load_vector_n` 这类求解配置。

4. `design_generate`
   - 调用 `Design` 角色模型，生成 `DesignPayload`，核心包括：
     - `cadquery_code`
     - `analysis_config`
     - `render_config`
     - `self_check_notes`
   - 设计输入固定由三部分组成：
     - `engineering_prompt`
     - `上一轮代码`
     - `当前轮唯一修复摘要 latest_revision_brief`
   - 同样采用“原始响应 -> JSON 提取 -> 容错归一化 -> Pydantic 校验”的方式解析。
   - 如果真实设计模型已启用，设计阶段会 fail-closed；解析失败、超时或非法输出会直接标记本轮失败，不再 silently 回退 heuristic。
   - 只有在未配置设计模型的离线 smoke test 下，才允许 heuristic 设计器兜底。
   - 系统会检查“收到审查反馈后代码是否发生实质变化”；若二轮仍输出相同代码，会直接终止而不是继续消耗 VLM/FEA。

5. `static_validate`
   - 对生成的 `cadquery_code` 做语法与安全检查。
   - 会拒绝危险导入和危险调用，例如 `os / sys / subprocess / eval / exec`。
   - 如果静态检查失败，不进入本地 CAD/FEA，而是把错误写入 `feedback_history`，回到下一轮设计。

6. `materialize_workspace -> build_cad -> build_mesh -> solve_fea`
   - `materialize_workspace` 会把本轮产物写到独立工作目录：
     - `generated_model.py`
     - `analysis_config.json`
     - `render_config.json`
     - `clarified_spec.json`
     - `config.py`
   - `build_cad` 执行 CadQuery 代码并导出 `model.step` 与 `model.stl`。
   - `build_mesh` 复用 `mvp/2_build_mesh.py`，生成 `msh22` 网格。
   - `solve_fea` 复用 `mvp/3_solve_fea.py`，运行 SfePy，输出 `fea_result.vtk` 并提取最大位移等数值摘要。

7. `render_views`
   - 使用 PyVista 读取 `model.stl`，输出固定视角的截图，默认包括：
     - `iso_front`
     - `iso_back`
     - `top`
     - `side`
   - 这些截图会作为后续视觉审查的输入。

8. `physics_qa -> physics_report -> visual_qa -> revision_brief`
   - `physics_qa` 是纯代码节点，不调用外部模型。
   - 当前至少使用 `max_disp_mm` 做硬阈值判断；如果未来有稳定的 stress 输出，也会联合 `max_stress_mpa` 一起判断。
   - `physics_report` 会把数值结果转成一段自然语言工程审查报告，作为下一轮修复输入的一部分。
   - `visual_qa` 优先调用 VLM/多模态模型，对渲染截图做语义审查。
   - `revision_brief` 只汇总**当前轮**工具失败、力学报告和视觉问题，生成简洁修复摘要。
   - 但当前实现有一个很重要的兼容策略：
     - 如果你只配置了共享的 OpenAI-compatible 文本模型，例如把 Qwen 作为 `TEXTCAD_DEFAULT_*`
     - 且没有单独指定 `TEXTCAD_VISUAL_*`
     - 那么视觉审查会自动退回本地 heuristic judge，避免把非多模态文本端点误当成 VLM 调用。

9. `feedback_merge -> decide_next`
   - `feedback_merge` 会把当前轮唯一修复摘要追加到 `feedback_history`，但后续设计不再直接吃整段历史。
   - 如果 `compile_status + physics_review + visual_review` 全部通过，则 `final_status = success`。
   - 如果设计阶段 fail-closed 或“代码未变化守卫”触发，则直接失败结束。
   - 否则带着 `engineering_prompt + latest_revision_brief + previous_code` 回到下一轮 `design_generate`。
   - 默认最多迭代 3 轮，避免 API 调用失控。

简单来说，这条生产链路就是：

```text
用户需求
-> Clarify API
-> Engineering Prompt Cache
-> Engineer Spec
-> Design API
-> Static Validate
-> CadQuery / Gmsh / SfePy / PyVista
-> Physics QA + Physics Report + Visual QA
-> Revision Brief
-> 通过则结束，失败则带修复摘要回到 Design
```

## 说明

- `mvp/` 仍然是唯一物理执行后端，Agent 层不会覆盖这些文件
- `visual_qa` 在无多模态模型时会退回本地 heuristic judge，仅用于流程联调
- 当前 `physics_qa` 强制使用 `max_disp_mm` 作为 gating 指标；`max_stress_mpa` 保留接口，但底层结果若未提供则不会阻塞流程
- `AgentRuntime` 的模型接入层支持 OpenAI、Anthropic，以及任何 OpenAI-compatible 端点（例如 Qwen/DashScope）
- `configs/providers/` 提供了 `openai / qwen / hybrid` 三套实验模板，适合做论文中的多模型对比
- 三个系统级提示词已抽离到 `textcad_agent/prompts/`，便于论文中单独描述 prompt 设计与后续版本管理
- 当前结果状态里会额外返回 `engineering_prompt`、`latest_revision_brief`、`physics_report`、`design_status`，方便直接检查第二轮到底收到了什么输入

## 测试

```bash
pytest tests
```
