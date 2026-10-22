"""【资源路径】统一定位仓库与文档模板，避免功能目录层级变化影响资源查找。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor" / "chemistry"
