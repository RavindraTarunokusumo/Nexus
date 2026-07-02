"""Unit tests for `nexus eval memory run` / `nexus eval memory report` (T-F4).

The memory-benchmark runner (scripts/benchmarks/run_memory_benchmark.py) is a
sibling deliverable landing separately; these tests stub it via sys.modules so
they pass regardless of whether that file exists yet on disk.
"""

from __future__ import annotations

import sys
import types

import pytest
from typer.testing import CliRunner

from app.cli import eval as eval_cli
from app.cli.eval import eval_app


@pytest.fixture
def runner():
    return CliRunner()


def _install_fake_runner_module(monkeypatch, fn):
    """Inject a fake scripts.benchmarks.run_memory_benchmark module."""
    scripts_mod = types.ModuleType("scripts")
    benchmarks_mod = types.ModuleType("scripts.benchmarks")
    runner_mod = types.ModuleType("scripts.benchmarks.run_memory_benchmark")
    runner_mod.run_benchmark = fn
    monkeypatch.setitem(sys.modules, "scripts", scripts_mod)
    monkeypatch.setitem(sys.modules, "scripts.benchmarks", benchmarks_mod)
    monkeypatch.setitem(sys.modules, "scripts.benchmarks.run_memory_benchmark", runner_mod)


def _install_missing_runner_module(monkeypatch):
    """Force ImportError for scripts.benchmarks.run_memory_benchmark deterministically."""
    scripts_mod = types.ModuleType("scripts")
    benchmarks_mod = types.ModuleType("scripts.benchmarks")
    monkeypatch.setitem(sys.modules, "scripts", scripts_mod)
    monkeypatch.setitem(sys.modules, "scripts.benchmarks", benchmarks_mod)
    monkeypatch.setitem(sys.modules, "scripts.benchmarks.run_memory_benchmark", None)


def test_memory_run_unknown_benchmark_errors(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(eval_cli, "_EVALS_MEMORY_DIR", tmp_path / "evals" / "memory")
    result = runner.invoke(eval_app, ["memory", "run", "--benchmark", "does_not_exist"])
    assert result.exit_code == 1
    assert "Unknown benchmark" in result.output


def test_memory_run_missing_runner_module_errors(runner, tmp_path, monkeypatch):
    fixtures_dir = tmp_path / "evals" / "memory" / "nexus_synthetic"
    fixtures_dir.mkdir(parents=True)
    monkeypatch.setattr(eval_cli, "_EVALS_MEMORY_DIR", tmp_path / "evals" / "memory")
    monkeypatch.setattr(eval_cli, "_BENCHMARK_RUNS_DIR", tmp_path / "runs")
    _install_missing_runner_module(monkeypatch)

    result = runner.invoke(eval_app, ["memory", "run", "--benchmark", "nexus_synthetic"])

    assert result.exit_code == 1
    assert "Benchmark runner not available" in result.output


def test_memory_run_invokes_entry_and_reports_run_id(runner, tmp_path, monkeypatch):
    fixtures_dir = tmp_path / "evals" / "memory" / "nexus_synthetic"
    fixtures_dir.mkdir(parents=True)
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(eval_cli, "_EVALS_MEMORY_DIR", tmp_path / "evals" / "memory")
    monkeypatch.setattr(eval_cli, "_BENCHMARK_RUNS_DIR", runs_dir)

    captured_kwargs = {}

    async def fake_entry(**kwargs):
        captured_kwargs.update(kwargs)
        return {"ok": True}

    _install_fake_runner_module(monkeypatch, fake_entry)

    result = runner.invoke(
        eval_app,
        [
            "memory",
            "run",
            "--benchmark",
            "nexus_synthetic",
            "--k",
            "3",
            "--out",
            str(runs_dir / "myrun"),
            "--skip-ingest",
            "--domain",
            "ai_tech",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "myrun" in result.output
    assert captured_kwargs["fixtures"] == fixtures_dir
    assert captured_kwargs["k"] == 3
    assert captured_kwargs["out"] == runs_dir / "myrun"
    assert captured_kwargs["skip_ingest"] is True
    assert captured_kwargs["domain"] == "ai_tech"


def test_memory_run_default_out_dir_is_timestamped(runner, tmp_path, monkeypatch):
    fixtures_dir = tmp_path / "evals" / "memory" / "nexus_synthetic"
    fixtures_dir.mkdir(parents=True)
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(eval_cli, "_EVALS_MEMORY_DIR", tmp_path / "evals" / "memory")
    monkeypatch.setattr(eval_cli, "_BENCHMARK_RUNS_DIR", runs_dir)

    async def fake_entry(**kwargs):
        return None

    _install_fake_runner_module(monkeypatch, fake_entry)

    result = runner.invoke(eval_app, ["memory", "run", "--benchmark", "nexus_synthetic"])

    assert result.exit_code == 0, result.output
    assert runs_dir.exists()
    created = list(runs_dir.iterdir())
    assert len(created) == 1
    assert created[0].name in result.output


def test_memory_run_entry_failure_reported_as_cli_error(runner, tmp_path, monkeypatch):
    fixtures_dir = tmp_path / "evals" / "memory" / "nexus_synthetic"
    fixtures_dir.mkdir(parents=True)
    monkeypatch.setattr(eval_cli, "_EVALS_MEMORY_DIR", tmp_path / "evals" / "memory")
    monkeypatch.setattr(eval_cli, "_BENCHMARK_RUNS_DIR", tmp_path / "runs")

    async def failing_entry(**kwargs):
        raise RuntimeError("qwen endpoint unreachable")

    _install_fake_runner_module(monkeypatch, failing_entry)

    result = runner.invoke(eval_app, ["memory", "run", "--benchmark", "nexus_synthetic"])

    assert result.exit_code == 1
    assert "Benchmark run failed" in result.output
    assert "qwen endpoint unreachable" in result.output


def test_memory_report_missing_run_errors(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(eval_cli, "_BENCHMARK_RUNS_DIR", tmp_path / "runs")
    result = runner.invoke(eval_app, ["memory", "report", "--run-id", "nope"])
    assert result.exit_code == 1
    assert "No report found" in result.output


def test_memory_report_prints_content_and_summary(runner, tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "20260702T120000Z"
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text("# Report\n\nOverall: 0.9\n")
    (run_dir / "run_meta.json").write_text('{"k": 5, "git_rev": "abc123"}')
    monkeypatch.setattr(eval_cli, "_BENCHMARK_RUNS_DIR", runs_dir)

    result = runner.invoke(eval_app, ["memory", "report", "--run-id", "20260702T120000Z"])

    assert result.exit_code == 0, result.output
    assert "Overall: 0.9" in result.output
    assert "Summary:" in result.output
    assert "k=5" in result.output
    assert "git_rev=abc123" in result.output
