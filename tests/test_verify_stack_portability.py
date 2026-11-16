from pathlib import Path

from ops.mlops import verify_stack


def test_native_compose_uses_checkout_and_preserves_explicit_path(monkeypatch):
    monkeypatch.setattr(verify_stack.sys, "platform", "darwin")
    command = verify_stack.compose_command()
    assert command[:3] == ["docker", "compose", "-f"]
    assert Path(command[3]).is_file()
    assert Path(command[3]).name == "docker-compose.yml"
    assert verify_stack.compose_command("/tmp/project with spaces/compose.yaml")[-1] == "/tmp/project with spaces/compose.yaml"


def test_windows_preserves_wsl_bench_command(monkeypatch):
    monkeypatch.setattr(verify_stack.sys, "platform", "win32")
    command = verify_stack.compose_command("/mnt/c/clone/ops/mlops/compose.yaml")
    assert command == ["wsl", "-d", "Ubuntu", "--", "docker", "compose", "-f",
                       "/mnt/c/clone/ops/mlops/compose.yaml"]
    assert verify_stack.compose_command()[-1] == "/mnt/y/src/ChickenLittle/ops/mlops/compose.yaml"
