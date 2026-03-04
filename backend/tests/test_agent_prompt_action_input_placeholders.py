from pathlib import Path


TARGET_FILES = [
    "app/services/agent/agents/recon.py",
    "app/services/agent/agents/analysis.py",
    "app/services/agent/agents/orchestrator.py",
    "app/services/agent/prompts/system_prompts.py",
]


def test_action_input_placeholders_are_removed_from_prompts():
    backend_root = Path(__file__).resolve().parents[1]
    forbidden_tokens = ("参数名", "参数值", '{"参数"', '{"参数1"', '{"参数2"')

    for rel_path in TARGET_FILES:
        file_path = backend_root / rel_path
        content = file_path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"{rel_path} still contains placeholder token: {token}"
