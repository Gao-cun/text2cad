from __future__ import annotations

import json
import re
from types import SimpleNamespace

from textcad_agent.run import main


class _FakeApp:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, payload, config=None):
        self.calls.append((payload, config))
        return self.result


class _StreamingFakeApp:
    def __init__(self, result, events):
        self.result = result
        self.events = events
        self.stream_calls = []

    def stream(self, payload, config=None, stream_mode=None):
        self.stream_calls.append((payload, config, stream_mode))
        for event in self.events:
            yield event

    def get_state(self, config=None):
        return SimpleNamespace(values=self.result)


def test_cli_prints_summary(monkeypatch, capsys):
    fake_app = _FakeApp(
        {
            "final_status": "success",
            "iteration": 1,
            "workspace_path": "/tmp/textcad/run-1",
            "fea_results": {"max_disp_mm": 1.25},
            "feedback_history": [],
        }
    )
    monkeypatch.setattr("textcad_agent.run.create_agent", lambda: fake_app)

    exit_code = main(["设计一个测试梁"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "status: success" in output
    assert "max_disp_mm: 1.250000" in output
    assert fake_app.calls[0][0] == {"user_prompt": "设计一个测试梁"}
    assert re.fullmatch(r"textcad-cli-[0-9a-f]{8}", fake_app.calls[0][1]["configurable"]["thread_id"])


def test_cli_prints_json(monkeypatch, capsys):
    fake_app = _FakeApp(
        {
            "final_status": "failed",
            "iteration": 3,
            "feedback_history": ["视觉审查未通过"],
        }
    )
    monkeypatch.setattr("textcad_agent.run.create_agent", lambda: fake_app)

    exit_code = main(["--json", "设计一个失败示例"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["final_status"] == "failed"
    assert payload["feedback_history"] == ["视觉审查未通过"]


def test_cli_respects_explicit_thread_id(monkeypatch, capsys):
    fake_app = _FakeApp({"final_status": "success", "iteration": 1, "feedback_history": []})
    monkeypatch.setattr("textcad_agent.run.create_agent", lambda: fake_app)

    exit_code = main(["--thread-id", "custom-thread", "设计一个测试梁"])

    assert exit_code == 0
    assert fake_app.calls[0][1]["configurable"]["thread_id"] == "custom-thread"


def test_cli_runs_tasks_file_and_prints_json(monkeypatch, capsys, tmp_path):
    class _BatchFakeApp:
        def invoke(self, payload, config=None):
            prompt = payload["user_prompt"]
            return {
                "final_status": "success",
                "iteration": 1,
                "workspace_path": f"/tmp/{abs(hash(prompt))}",
                "feedback_history": [],
            }

    monkeypatch.setattr("textcad_agent.run.create_agent", lambda: _BatchFakeApp())
    tasks_file = tmp_path / "tasks.txt"
    tasks_file.write_text("任务一\n\n# 忽略注释\n任务二\n", encoding="utf-8")

    exit_code = main(["--tasks-file", str(tasks_file), "--parallel-workers", "2", "--json", "--no-progress"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 2
    assert payload[0]["prompt"] == "任务一"
    assert payload[1]["prompt"] == "任务二"
    assert payload[0]["result"]["final_status"] == "success"
    assert payload[1]["result"]["final_status"] == "success"


def test_cli_batch_mode_prints_progress_bar(monkeypatch, capsys, tmp_path):
    class _BatchFakeApp:
        def invoke(self, payload, config=None):
            return {
                "final_status": "success",
                "iteration": 1,
                "feedback_history": [],
            }

    monkeypatch.setattr("textcad_agent.run.create_agent", lambda: _BatchFakeApp())
    tasks_file = tmp_path / "tasks.txt"
    tasks_file.write_text("任务A\n任务B\n", encoding="utf-8")

    exit_code = main(["--tasks-file", str(tasks_file), "--parallel-workers", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "batch progress" in captured.err
    assert "100.0%" in captured.err


def test_cli_single_mode_prints_stream_progress_and_tokens(monkeypatch, capsys):
    fake_app = _StreamingFakeApp(
        {
            "final_status": "success",
            "iteration": 1,
            "feedback_history": [],
            "token_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
            },
        },
        [
            {"clarify_spec": {"iteration": 1, "token_usage": {"total_tokens": 40}}},
            {"design_generate": {"iteration": 1, "token_usage": {"total_tokens": 140}}},
            {"visual_qa": {"iteration": 1, "token_usage": {"total_tokens": 200}}},
            {"decide_next": {"final_status": "success"}},
        ],
    )
    monkeypatch.setattr("textcad_agent.run.create_agent", lambda: fake_app)

    exit_code = main(["设计一个桌面手机支架"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "progress" in captured.err
    assert "澄清需求" in captured.err
    assert "生成/修复 CadQuery" in captured.err
    assert "视觉审查" in captured.err
    assert "tokens=200" in captured.err
    assert "status=success" in captured.err
    assert "stream_mode" not in captured.out
    assert fake_app.stream_calls[0][2] == "updates"
