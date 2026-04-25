"""
文档分块模块 —— 三层嵌套分块 + Markdown 结构感知

分块策略：
  1. 三层嵌套分块 (L1→L2→L3)：
     L1 (大块, ~1200字) → L2 (中块, ~600字) → L3 (小块, ~300字)
     每层保留父子关系，支持 Auto-merging 自动合并

  2. Markdown 结构化分块：
     按标题层级 (#, ##, ###) 分割，保留标题路径元数据
     优先用于 Markdown 文档，普通文档使用递归字符分割

  3. 结构保护：
     代码块和表格在分块时不会被截断，使用占位符保护后恢复

支持的文档格式：txt, md, pdf, docx
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import (
    LEVEL_1_CHUNK_SIZE,
    LEVEL_1_CHUNK_OVERLAP,
    LEVEL_2_CHUNK_SIZE,
    LEVEL_2_CHUNK_OVERLAP,
    LEVEL_3_CHUNK_SIZE,
    LEVEL_3_CHUNK_OVERLAP,
    FILES_DIR,
)


MARKDOWN_HEADER_SPLIT_CONFIG = [
    ("#", "header_1"),
    ("##", "header_2"),
    ("###", "header_3"),
    ("####", "header_4"),
]

STRUCTURE_PATTERNS = {
    "code_block": r"```[\s\S]*?```",
    "table": r"\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n?)+",
    "list_item": r"^[ \t]*[-*+]\s+.+$",
    "numbered_list": r"^[ \t]*\d+\.\s+.+$",
    "html_heading": r"<h[1-6][^>]*>.*?</h[1-6]>",
    "definition": r"^[^:\n]+:\s+.+$",
}


class MarkdownStructureSplitter:
    """
    基于 Markdown 标题结构的智能切片器。
    
    按 # ~ #### 标题将文档分割为多个 section，
    每个 section 保留完整的标题层级路径作为元数据。
    """
    
    def __init__(
        self,
        headers_to_split_on: List[Tuple[str, str]] = None,
        strip_headers: bool = False,
    ):
        """
        Args:
            headers_to_split_on: 标题标记与元数据键名的映射列表
            strip_headers: 是否从分块文本中移除标题行
        """
        self.headers_to_split_on = headers_to_split_on or MARKDOWN_HEADER_SPLIT_CONFIG
        self.strip_headers = strip_headers
        self._header_pattern = self._build_header_pattern()
    
    def _build_header_pattern(self) -> re.Pattern:
        """构建匹配所有配置标题级别的正则表达式"""
        header_patterns = []
        for marker, _ in self.headers_to_split_on:
            escaped = re.escape(marker)
            header_patterns.append(f"(^{escaped}\\s+.+$)")
        return re.compile("|".join(header_patterns), re.MULTILINE)
    
    def split_text(self, text: str) -> List[Dict[str, Any]]:
        """
        按 Markdown 标题结构分割文本。

        遍历每一行，遇到标题时：
          1. 将当前累积的文本保存为一个 section
          2. 更新当前标题层级（低级标题会清除同级/更深的标题上下文）
        
        Returns:
            [{"text": "...", "metadata": {"header_1": "...", "header_2": "..."}}, ...]
        """
        if not text or not text.strip():
            return []
        
        lines = text.split("\n")
        sections: List[Dict[str, Any]] = []
        current_section_lines: List[str] = []
        current_headers: Dict[str, str] = {}
        
        header_levels = {}
        for marker, name in self.headers_to_split_on:
            header_levels[marker] = name
        
        for line in lines:
            header_match = None
            header_level = None
            header_text = None
            
            for marker, level_name in self.headers_to_split_on:
                if line.startswith(marker + " "):
                    header_match = marker
                    header_level = level_name
                    header_text = line[len(marker):].strip()
                    break
            
            if header_match:
                if current_section_lines:
                    section_text = "\n".join(current_section_lines).strip()
                    if section_text:
                        sections.append({
                            "text": section_text,
                            "metadata": dict(current_headers),
                        })
                    current_section_lines = []
                
                level_idx = int(header_level.split("_")[-1])
                for lvl_name in list(current_headers.keys()):
                    existing_idx = int(lvl_name.split("_")[-1])
                    if existing_idx >= level_idx:
                        del current_headers[lvl_name]
                
                current_headers[header_level] = header_text
                
                if not self.strip_headers:
                    current_section_lines.append(line)
            else:
                current_section_lines.append(line)
        
        if current_section_lines:
            section_text = "\n".join(current_section_lines).strip()
            if section_text:
                sections.append({
                    "text": section_text,
                    "metadata": dict(current_headers),
                })
        
        return sections
    
    def merge_small_sections(
        self,
        sections: List[Dict[str, Any]],
        min_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        合并过小的分块：将长度 < min_size 的 section 与下一个 section 合并，
        避免产生信息量不足的碎片化分块。
        """
        if not sections:
            return []
        
        merged: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        
        for section in sections:
            text = section.get("text", "")
            
            if current is None:
                current = dict(section)
            elif len(current.get("text", "")) < min_size:
                current["text"] += "\n\n" + text
            else:
                merged.append(current)
                current = dict(section)
        
        if current:
            merged.append(current)
        
        return merged


class StructureAwareSplitter:
    """
    结构感知的文本切片器，保护代码块、表格等结构不被截断。

    工作原理：
      1. 提取需要保护的结构（代码块、表格），用占位符替换
      2. 对替换后的文本执行常规递归字符分割
      3. 将占位符恢复为原始结构
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        preserve_structures: List[str] = None,
    ):
        """
        Args:
            chunk_size: 目标分块大小（字符数）
            chunk_overlap: 分块重叠字符数
            preserve_structures: 需要保护的结构类型列表，可选 "code_block", "table" 等
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.preserve_structures = preserve_structures or ["code_block", "table"]
        self._base_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
    
    def _extract_structures(self, text: str) -> Tuple[str, Dict[int, str]]:
        """
        提取需要保护的结构，用占位符替换。

        Returns:
            (处理后的文本, {占位符索引: 原始结构文本})
        """
        protected: Dict[int, str] = {}
        modified_text = text
        placeholder_idx = 0
        
        for struct_type in self.preserve_structures:
            if struct_type not in STRUCTURE_PATTERNS:
                continue
            
            pattern = STRUCTURE_PATTERNS[struct_type]
            for match in re.finditer(pattern, modified_text, re.MULTILINE):
                original = match.group(0)
                placeholder = f"__STRUCT_PLACEHOLDER_{placeholder_idx}__"
                protected[placeholder_idx] = original
                modified_text = modified_text.replace(original, placeholder, 1)
                placeholder_idx += 1
        
        return modified_text, protected
    
    def _restore_structures(
        self,
        chunks: List[str],
        protected: Dict[int, str],
    ) -> List[str]:
        """恢复被保护的结构：将占位符替换回原始代码块/表格"""
        restored = []
        
        for chunk in chunks:
            restored_chunk = chunk
            for idx, original in protected.items():
                placeholder = f"__STRUCT_PLACEHOLDER_{idx}__"
                if placeholder in restored_chunk:
                    restored_chunk = restored_chunk.replace(placeholder, original)
            restored.append(restored_chunk)
        
        return restored
    
    def split_text(self, text: str) -> List[str]:
        """分割文本，保护特定结构（代码块/表格不会被截断）"""
        modified_text, protected = self._extract_structures(text)
        chunks = self._base_splitter.split_text(modified_text)
        return self._restore_structures(chunks, protected)


class Chunker:
    """
    文档分块服务，支持 Markdown 结构化切片。

    分块层次：
      L1 (大块, ~1200字) → L2 (中块, ~600字) → L3 (小块, ~300字)
      L1/L2 作为父块存入 parent_chunks 表，L3 作为叶块存入 chunks 表并建立向量索引。
      父子关系通过 parent_chunk_id 和 root_chunk_id 维护。
    """
    
    def __init__(
        self,
        use_markdown_structure: bool = False,
        preserve_code_blocks: bool = True,
        preserve_tables: bool = True,
    ):
        """
        Args:
            use_markdown_structure: 是否启用 Markdown 结构化分块
            preserve_code_blocks: 是否保护代码块不被截断
            preserve_tables: 是否保护表格不被截断
        """
        self.use_markdown_structure = use_markdown_structure
        self.preserve_code_blocks = preserve_code_blocks
        self.preserve_tables = preserve_tables
        
        self._splitter_l1 = self._build_splitter(LEVEL_1_CHUNK_SIZE, LEVEL_1_CHUNK_OVERLAP)
        self._splitter_l2 = self._build_splitter(LEVEL_2_CHUNK_SIZE, LEVEL_2_CHUNK_OVERLAP)
        self._splitter_l3 = self._build_splitter(LEVEL_3_CHUNK_SIZE, LEVEL_3_CHUNK_OVERLAP)
        
        self._md_splitter = MarkdownStructureSplitter(
            headers_to_split_on=MARKDOWN_HEADER_SPLIT_CONFIG,
            strip_headers=False,
        )
        
        preserve_structures = []
        if preserve_code_blocks:
            preserve_structures.append("code_block")
        if preserve_tables:
            preserve_structures.append("table")
        
        self._structure_splitter = StructureAwareSplitter(
            chunk_size=LEVEL_3_CHUNK_SIZE,
            chunk_overlap=LEVEL_3_CHUNK_OVERLAP,
            preserve_structures=preserve_structures,
        )
    
    def _build_splitter(self, chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
        """构建递归字符分割器，使用中英文友好的分隔符优先级"""
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
    
    def _is_markdown_file(self, file_path: Path) -> bool:
        """判断是否为 Markdown 文件"""
        return file_path.suffix.lower() in {".md", ".markdown"}
    
    def _detect_text_structure(self, text: str) -> Dict[str, Any]:
        """检测文本的结构特征（标题、代码块、表格、列表等），用于选择分块策略"""
        features = {
            "has_markdown_headers": bool(re.search(r"^#{1,6}\s+.+$", text, re.MULTILINE)),
            "has_code_blocks": bool(re.search(r"```", text)),
            "has_tables": bool(re.search(r"\|.+\|", text)),
            "has_lists": bool(re.search(r"^[ \t]*[-*+]\s+.+$", text, re.MULTILINE)),
            "has_numbered_lists": bool(re.search(r"^[ \t]*\d+\.\s+.+$", text, re.MULTILINE)),
            "has_html_tags": bool(re.search(r"<[a-zA-Z][^>]*>", text)),
        }
        return features
    
    def load_document(self, file_path: Path):
        """
        加载文档，根据文件扩展名选择合适的 Loader。

        支持：txt/md/markdown (TextLoader), pdf (PyPDFLoader), docx (Docx2txtLoader)
        """
        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            return TextLoader(str(file_path), encoding="utf-8").load()
        if suffix == ".pdf":
            return PyPDFLoader(str(file_path)).load()
        if suffix == ".docx":
            return Docx2txtLoader(str(file_path)).load()
        raise ValueError("仅支持 txt/md/pdf/docx 文档")
    
    def _build_chunk_id(self, source: str, page: int, level: int, idx: int) -> str:
        """构建分块唯一标识：{source}::p{page}::l{level}::{idx}"""
        return f"{source}::p{page}::l{level}::{idx}"
    
    MIN_CHUNK_LENGTH = 30

    def _is_valid_chunk(self, text: str) -> bool:
        """
        校验分块是否有效。

        无效分块条件：
          - 纯空白或长度 < 30
          - 仅包含标题行（无实际内容）
          - 去除标题行后内容长度 < 30
        """
        if not text or len(text.strip()) < self.MIN_CHUNK_LENGTH:
            return False
        
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
        if not lines:
            return False
        
        non_header_lines = [line for line in lines if not line.startswith('#')]
        
        if not non_header_lines:
            return False
        
        non_header_text = ' '.join(non_header_lines)
        if len(non_header_text) < self.MIN_CHUNK_LENGTH:
            return False
        
        return True
    
    def _filter_invalid_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """过滤掉无效分块（内容过短或仅含标题）"""
        return [chunk for chunk in chunks if self._is_valid_chunk(chunk.get("text", ""))]
    
    def _split_by_markdown_structure(
        self,
        text: str,
        base_doc: Dict[str, Any],
        page_global_chunk_idx: int,
        doc_id: str,
        source: str,
        page: int,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        基于 Markdown 结构的分块策略。

        流程：
          1. 先按标题结构分割为多个 section（保留标题层级元数据）
          2. 合并过小的 section
          3. 每个 section 内部再进行三层嵌套分块 (L1→L2→L3)
          4. 保留标题路径信息 (header_path) 作为元数据
        """
        all_chunks: List[Dict] = []
        parent_chunks: List[Dict] = []
        
        sections = self._md_splitter.split_text(text)
        sections = self._md_splitter.merge_small_sections(sections, min_size=100)
        
        l1_counter = 0
        l2_counter = 0
        l3_counter = 0
        
        for section in sections:
            section_text = section.get("text", "").strip()
            section_metadata = section.get("metadata", {})
            
            if not section_text:
                continue
            
            header_path = self._build_header_path(section_metadata)
            
            l1_docs = self._splitter_l1.create_documents([section_text], [base_doc])
            
            for l1_doc in l1_docs:
                l1_text = (l1_doc.page_content or "").strip()
                if not l1_text:
                    continue
                
                l1_id = self._build_chunk_id(source, page, 1, l1_counter)
                l1_counter += 1
                
                l1_chunk = {
                    **base_doc,
                    "source": source,
                    "text": l1_text,
                    "chunk_id": l1_id,
                    "parent_chunk_id": "",
                    "root_chunk_id": l1_id,
                    "chunk_level": 1,
                    "chunk_idx": page_global_chunk_idx,
                    "doc_id": doc_id,
                    "header_path": header_path,
                    **section_metadata,
                }
                parent_chunks.append(l1_chunk)
                page_global_chunk_idx += 1
                
                l2_docs = self._splitter_l2.create_documents([l1_text], [base_doc])
                for l2_doc in l2_docs:
                    l2_text = (l2_doc.page_content or "").strip()
                    if not l2_text:
                        continue
                    
                    l2_id = self._build_chunk_id(source, page, 2, l2_counter)
                    l2_counter += 1
                    
                    l2_chunk = {
                        **base_doc,
                        "source": source,
                        "text": l2_text,
                        "chunk_id": l2_id,
                        "parent_chunk_id": l1_id,
                        "root_chunk_id": l1_id,
                        "chunk_level": 2,
                        "chunk_idx": page_global_chunk_idx,
                        "doc_id": doc_id,
                        "header_path": header_path,
                        **section_metadata,
                    }
                    parent_chunks.append(l2_chunk)
                    page_global_chunk_idx += 1
                    
                    l3_chunks = self._structure_splitter.split_text(l2_text)
                    for l3_text in l3_chunks:
                        l3_text = l3_text.strip()
                        if not l3_text:
                            continue
                        
                        l3_id = self._build_chunk_id(source, page, 3, l3_counter)
                        l3_counter += 1
                        
                        l3_chunk = {
                            **base_doc,
                            "source": source,
                            "text": l3_text,
                            "chunk_id": l3_id,
                            "parent_chunk_id": l2_id,
                            "root_chunk_id": l1_id,
                            "chunk_level": 3,
                            "chunk_idx": page_global_chunk_idx,
                            "doc_id": doc_id,
                            "header_path": header_path,
                            **section_metadata,
                        }
                        all_chunks.append(l3_chunk)
                        page_global_chunk_idx += 1
        
        return all_chunks, parent_chunks
    
    def _build_header_path(self, metadata: Dict[str, str]) -> str:
        """构建标题路径，如 '第一章 > 第一节 > 第一条'"""
        parts = []
        for i in range(1, 5):
            key = f"header_{i}"
            if key in metadata and metadata[key]:
                parts.append(metadata[key])
        return " > ".join(parts) if parts else ""
    
    def split_to_three_levels(
        self,
        text: str,
        base_doc: Dict[str, Any],
        page_global_chunk_idx: int,
        doc_id: str,
        source: str,
        page: int,
        is_markdown: bool = False,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        三层嵌套分块：L1 (大块) → L2 (中块) → L3 (小块)。

        对于 Markdown 文档且启用结构化分块时，优先使用 _split_by_markdown_structure。
        否则使用递归字符分割器进行三层嵌套分块。

        每个分块包含父子关系字段：
          - parent_chunk_id: 直接父块的 chunk_id
          - root_chunk_id:   L1 根块的 chunk_id
          - chunk_level:     层级 (1/2/3)

        Args:
            text: 待分块的文本
            base_doc: 基础元数据字典
            page_global_chunk_idx: 全局分块索引起始值
            doc_id: 文档 ID
            source: 文件名
            page: 页码
            is_markdown: 是否为 Markdown 文档

        Returns:
            (all_chunks, all_parent_chunks) —— L3 叶块列表和 L1/L2 父块列表
        """
        if not text or not text.strip():
            return [], []
        
        if is_markdown and self.use_markdown_structure:
            structure_features = self._detect_text_structure(text)
            if structure_features["has_markdown_headers"]:
                return self._split_by_markdown_structure(
                    text=text,
                    base_doc=base_doc,
                    page_global_chunk_idx=page_global_chunk_idx,
                    doc_id=doc_id,
                    source=source,
                    page=page,
                )
        
        all_chunks: List[Dict] = []
        parent_chunks: List[Dict] = []
        
        l1_docs = self._splitter_l1.create_documents([text], [base_doc])
        l1_counter = 0
        l2_counter = 0
        l3_counter = 0

        for l1_doc in l1_docs:
            l1_text = (l1_doc.page_content or "").strip()
            if not l1_text:
                continue
            
            l1_id = self._build_chunk_id(source, page, 1, l1_counter)
            l1_counter += 1

            l1_chunk = {
                **base_doc,
                "source": source,
                "text": l1_text,
                "chunk_id": l1_id,
                "parent_chunk_id": "",
                "root_chunk_id": l1_id,
                "chunk_level": 1,
                "chunk_idx": page_global_chunk_idx,
                "doc_id": doc_id,
            }
            parent_chunks.append(l1_chunk)
            page_global_chunk_idx += 1

            l2_docs = self._splitter_l2.create_documents([l1_text], [base_doc])
            for l2_doc in l2_docs:
                l2_text = (l2_doc.page_content or "").strip()
                if not l2_text:
                    continue
                
                l2_id = self._build_chunk_id(source, page, 2, l2_counter)
                l2_counter += 1

                l2_chunk = {
                    **base_doc,
                    "source": source,
                    "text": l2_text,
                    "chunk_id": l2_id,
                    "parent_chunk_id": l1_id,
                    "root_chunk_id": l1_id,
                    "chunk_level": 2,
                    "chunk_idx": page_global_chunk_idx,
                    "doc_id": doc_id,
                }
                parent_chunks.append(l2_chunk)
                page_global_chunk_idx += 1

                l3_docs = self._splitter_l3.create_documents([l2_text], [base_doc])
                for l3_doc in l3_docs:
                    l3_text = (l3_doc.page_content or "").strip()
                    if not l3_text:
                        continue
                    
                    l3_id = self._build_chunk_id(source, page, 3, l3_counter)
                    l3_counter += 1

                    l3_chunk = {
                        **base_doc,
                        "source": source,
                        "text": l3_text,
                        "chunk_id": l3_id,
                        "parent_chunk_id": l2_id,
                        "root_chunk_id": l1_id,
                        "chunk_level": 3,
                        "chunk_idx": page_global_chunk_idx,
                        "doc_id": doc_id,
                    }
                    all_chunks.append(l3_chunk)
                    page_global_chunk_idx += 1

        return all_chunks, parent_chunks
    
    def process_document(
        self,
        file_path: Path,
        source: str,
        doc_id: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        处理完整文档，返回所有分块。

        按页遍历文档，对每页内容执行三层分块，汇总所有叶块和父块。

        Args:
            file_path: 文件路径
            source: 文件名
            doc_id: 文档 ID

        Returns:
            (all_chunks, all_parent_chunks) 所有 L3 叶块和 L1/L2 父块
        """
        docs = self.load_document(file_path)
        
        all_chunks: List[Dict] = []
        all_parent_chunks: List[Dict] = []
        page_global_chunk_idx = 0
        
        is_markdown = self._is_markdown_file(file_path)

        for doc in docs:
            base_doc = {
                "filename": source,
                "file_path": str(file_path),
                "file_type": file_path.suffix.lower().lstrip("."),
                "page_number": doc.metadata.get("page", 0),
            }
            page = int(doc.metadata.get("page", 0) or 0)
            text = (doc.page_content or "").strip()
            
            page_chunks, page_parent_chunks = self.split_to_three_levels(
                text=text,
                base_doc=base_doc,
                page_global_chunk_idx=page_global_chunk_idx,
                doc_id=doc_id,
                source=source,
                page=page,
                is_markdown=is_markdown,
            )
            all_chunks.extend(page_chunks)
            all_parent_chunks.extend(page_parent_chunks)
            page_global_chunk_idx += len(page_chunks) + len(page_parent_chunks)

        all_chunks = self._filter_invalid_chunks(all_chunks)
        
        return all_chunks, all_parent_chunks
