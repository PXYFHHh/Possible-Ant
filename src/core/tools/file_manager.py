from langchain_core.tools import tool
import os
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).parent.parent.parent.parent
FILES_DIR = BASE_DIR / "files"


def _ensure_files_dir():
    if not FILES_DIR.exists():
        FILES_DIR.mkdir(parents=True, exist_ok=True)


def _validate_path(filename: str) -> Path:
    _ensure_files_dir()
    
    if not filename or filename.strip() == "":
        raise ValueError("文件名不能为空")
    
    if any(char in filename for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']):
        raise ValueError("文件名包含非法字符")
    
    filename = os.path.basename(filename)
    
    file_path = (FILES_DIR / filename).resolve()
    
    if not str(file_path).startswith(str(FILES_DIR.resolve())):
        raise ValueError("只允许在 files 文件夹内操作")
    
    return file_path


@tool
def create_file(filename: str, content: str) -> str:
    """
    在 files 文件夹中创建文件并写入内容
    
    params:
        filename: 文件名（仅文件名，不包含路径）
        content: 要写入的文件内容
    
    return:
        操作结果信息
    """
    try:
        file_path = _validate_path(filename)
        
        if file_path.exists():
            return f"文件 {filename} 已存在，如需修改请使用 overwrite_file 工具"
        
        file_path.write_text(content, encoding='utf-8')
        
        return f"成功创建文件：{filename}\n文件路径：{file_path}\n文件大小：{len(content)} 字符"
    
    except ValueError as e:
        return f"安全错误：{str(e)}"
    except Exception as e:
        return f"创建文件失败：{str(e)}"


@tool
def overwrite_file(filename: str, content: str) -> str:
    """
    覆盖 files 文件夹中的文件内容
    
    params:
        filename: 文件名（仅文件名，不包含路径）
        content: 要写入的新内容
    
    return:
        操作结果信息
    """
    try:
        file_path = _validate_path(filename)
        
        if not file_path.exists():
            return f"文件 {filename} 不存在，请先使用 create_file 创建文件"
        
        old_size = file_path.stat().st_size
        file_path.write_text(content, encoding='utf-8')
        
        return f"成功覆盖文件：{filename}\n文件路径：{file_path}\n原大小：{old_size} 字节\n新大小：{len(content)} 字符"
    
    except ValueError as e:
        return f"安全错误：{str(e)}"
    except Exception as e:
        return f"覆盖文件失败：{str(e)}"


@tool
def read_file(filename: str) -> str:
    """
    读取 files 文件夹中的文件内容
    
    params:
        filename: 文件名（仅文件名，不包含路径）
    
    return:
        文件内容
    """
    try:
        file_path = _validate_path(filename)
        
        if not file_path.exists():
            return f"文件 {filename} 不存在"
        
        content = file_path.read_text(encoding='utf-8')
        
        return f"文件：{filename}\n内容：\n{content}"
    
    except ValueError as e:
        return f"安全错误：{str(e)}"
    except Exception as e:
        return f"读取文件失败：{str(e)}"


@tool
def delete_file(filename: str) -> str:
    """
    删除 files 文件夹中的文件
    
    params:
        filename: 文件名（仅文件名，不包含路径）
    
    return:
        操作结果信息
    """
    try:
        file_path = _validate_path(filename)
        
        if not file_path.exists():
            return f"文件 {filename} 不存在"
        
        file_size = file_path.stat().st_size
        file_path.unlink()
        
        return f"成功删除文件：{filename}\n文件大小：{file_size} 字节"
    
    except ValueError as e:
        return f"安全错误：{str(e)}"
    except Exception as e:
        return f"删除文件失败：{str(e)}"


@tool
def delete_multiple_files(filenames: str, exclude: Optional[str] = None) -> str:
    """
    批量删除 files 文件夹中的多个文件
    
    params:
        filenames: 要删除的文件名列表，用逗号分隔（如："file1.txt,file2.txt,file3.png"）
                  如果为空字符串，则删除所有文件（除了exclude中指定的文件）
        exclude: 要保留的文件名列表，用逗号分隔（如："README.md,important.txt"）
    
    return:
        批量删除结果统计
    
    示例:
        # 删除指定文件
        delete_multiple_files("file1.txt,file2.txt,file3.png")
        
        # 删除所有文件，但保留README.md
        delete_multiple_files("", "README.md")
        
        # 删除多个文件，但保留某些重要文件
        delete_multiple_files("data1.txt,data2.txt", "README.md,config.json")
    """
    try:
        _ensure_files_dir()
        
        exclude_list = []
        if exclude:
            exclude_list = [name.strip() for name in exclude.split(',') if name.strip()]
        
        files_to_delete = []
        
        if filenames and filenames.strip():
            files_to_delete = [name.strip() for name in filenames.split(',') if name.strip()]
        else:
            all_files = list(FILES_DIR.glob("*"))
            files_to_delete = [f.name for f in all_files if f.is_file() and f.name not in exclude_list]
        
        if not files_to_delete:
            return "没有需要删除的文件"
        
        success_count = 0
        failed_count = 0
        total_size = 0
        failed_files = []
        
        for filename in files_to_delete:
            if filename in exclude_list:
                continue
            
            try:
                file_path = _validate_path(filename)
                
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    success_count += 1
                    total_size += file_size
                else:
                    failed_count += 1
                    failed_files.append(f"{filename} (不存在)")
            except Exception as e:
                failed_count += 1
                failed_files.append(f"{filename} ({str(e)})")
        
        result = f"批量删除完成\n"
        result += f"✅ 成功删除：{success_count} 个文件\n"
        result += f"💾 释放空间：{total_size} 字节 ({total_size/1024:.2f} KB)\n"
        
        if exclude_list:
            result += f"🔒 保留文件：{', '.join(exclude_list)}\n"
        
        if failed_count > 0:
            result += f"❌ 失败：{failed_count} 个文件\n"
            result += f"失败详情：\n"
            for failed in failed_files:
                result += f"  - {failed}\n"
        
        return result
    
    except Exception as e:
        return f"批量删除失败：{str(e)}"


@tool
def list_files() -> str:
    """
    列出 files 文件夹中的所有文件
    
    return:
        文件列表
    """
    try:
        _ensure_files_dir()
        
        files = list(FILES_DIR.glob("*"))
        
        if not files:
            return "files 文件夹为空"
        
        file_list = []
        for file_path in sorted(files):
            if file_path.is_file():
                size = file_path.stat().st_size
                file_list.append(f"{file_path.name} ({size} 字节)")
        
        if not file_list:
            return "files 文件夹中没有文件"
        
        return "files 文件夹内容：\n" + "\n".join(file_list)
    
    except Exception as e:
        return f"列出文件失败：{str(e)}"
