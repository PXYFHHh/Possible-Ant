"""
模型工具模块 —— 模型路径解析的公共函数

embedding.py 和 reranker.py 共用，避免代码冗余。
模型查找优先级：本地文件 → 本地缓存目录 → ModelScope 下载 → HuggingFace 自动下载。
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent.rag.model_utils")


def _resolve_model_path(model_name: str, modelscope_id: str, use_modelscope: bool, model_cache_dir: Path) -> str:
    """
    解析模型路径，按优先级查找：
      1. 本地绝对路径直接使用
      2. MODEL_CACHE_DIR 下的缓存目录
      3. ModelScope 缓存目录
      4. ModelScope 下载（需要联网）
      5. 回退到原始模型名（由 HuggingFace 自动下载）
    """
    if Path(model_name).exists():
        return model_name

    if use_modelscope:
        cache_dir = model_cache_dir / model_name.replace("/", "_")
        if cache_dir.exists() and cache_dir.is_dir():
            resolved = _find_model_in_dir(cache_dir, model_name)
            if resolved:
                return resolved

        modelscope_cache_name = modelscope_id.replace(".", "___")
        modelscope_cache_dir = model_cache_dir / modelscope_cache_name.replace("/", os.sep)
        if modelscope_cache_dir.exists():
            resolved = _find_model_in_dir(modelscope_cache_dir, model_name)
            if resolved:
                return resolved

        parent_dir = model_cache_dir / model_name.split("/")[0]
        if parent_dir.exists():
            parts = model_name.split("/")
            if len(parts) == 2:
                org, model = parts
                model_normalized = model.replace(".", "___")
                for child in parent_dir.iterdir():
                    if child.is_dir():
                        resolved = _find_model_in_dir(child, model_name)
                        if resolved:
                            return resolved

        try:
            from modelscope import snapshot_download

            cache_dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(modelscope_id, cache_dir=str(cache_dir))
            return str(cache_dir)
        except Exception:
            pass

    return model_name


def _find_model_in_dir(base_dir: Path, model_name: str) -> Optional[str]:
    """在目录中递归查找模型目录，匹配 org/model 格式的模型名"""
    parts = model_name.split("/")
    if len(parts) != 2:
        return None
    org, model = parts
    model_normalized = model.replace(".", "___")

    def matches(child_name: str) -> bool:
        return child_name.replace("___", ".") == model or child_name == model_normalized

    if matches(base_dir.name):
        if _is_valid_model_dir(base_dir):
            return str(base_dir)

    for child in base_dir.iterdir():
        if child.is_dir():
            if matches(child.name):
                if _is_valid_model_dir(child):
                    return str(child)
            found = _find_model_in_dir(child, model_name)
            if found:
                return found

    return None


def _is_valid_model_dir(path: Path) -> bool:
    """检查目录是否是有效的模型目录（至少包含 config.json 和模型权重文件）"""
    if not path.is_dir():
        return False
    required_files = ["config.json", "model.safetensors", "pytorch_model.bin"]
    has_model = any((path / f).exists() for f in required_files if f != "pytorch_model.bin" or not (path / "model.safetensors").exists())
    return has_model or (path / "config.json").exists()
