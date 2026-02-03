from pathlib import Path
import tempfile
import subprocess
import os
import logging
from tqdm import tqdm  # 导入 tqdm

logger = logging.getLogger(__name__)
cur_dir = Path(__file__).resolve().parent
print("当前目录:", cur_dir)

# 过滤文件列表
files = [file for file in cur_dir.rglob("*") if file.is_file() and file.name != "test.py"]
print(f"找到待验证文件: {len(files)}")

def validate_opengrep_rule(yaml_content: str) -> bool:
    # ... 保持你原有的函数逻辑不变 ...
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tmp_file:
            tmp_file.write(yaml_content)
            tmp_file_path = tmp_file.name
        try:
            result = subprocess.run(
                ["opengrep", "--config", tmp_file_path, "--validate"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    except Exception as e:
        logger.warning(f"验证异常: {e}")
        return False

# --- 使用进度条的核心逻辑 ---
# desc: 进度条左侧的描述文字
# unit: 进度单位
for file in tqdm(files, desc="验证进度", unit="file"):
    try:
        content = file.read_text(encoding="utf-8")
        is_valid = validate_opengrep_rule(content)
        
        if not is_valid:
            # 使用 tqdm.write 避免破坏进度条结构
            tqdm.write(f"❌ 规则文件验证失败: {file}")
            file.unlink()
            
    except Exception as e:
        tqdm.write(f"⚠️ 无法读取文件 {file}: {e}")

print("验证任务完成！")