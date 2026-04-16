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
    """基于 Markdown 结构的智能切片器"""
    
    def __init__(
        self,
        headers_to_split_on: List[Tuple[str, str]] = None,
        strip_headers: bool = False,
    ):
        self.headers_to_split_on = headers_to_split_on or MARKDOWN_HEADER_SPLIT_CONFIG
        self.strip_headers = strip_headers
        self._header_pattern = self._build_header_pattern()
    
    def _build_header_pattern(self) -> re.Pattern:
        header_patterns = []
        for marker, _ in self.headers_to_split_on:
            escaped = re.escape(marker)
            header_patterns.append(f"(^{escaped}\\s+.+$)")
        return re.compile("|".join(header_patterns), re.MULTILINE)
    
    def split_text(self, text: str) -> List[Dict[str, Any]]:
        """
        按 Markdown 标题结构分割文本
        
        返回: [{"text": "...", "metadata": {"header_1": "...", "header_2": "..."}}, ...]
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
        """合并过小的分块"""
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
    """结构感知的文本切片器，保护代码块、表格等结构"""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        preserve_structures: List[str] = None,
    ):
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
        提取需要保护的结构，用占位符替换
        
        返回: (处理后的文本, {占位符索引: 原始结构})
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
        """恢复被保护的结构"""
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
        """分割文本，保护特定结构"""
        modified_text, protected = self._extract_structures(text)
        chunks = self._base_splitter.split_text(modified_text)
        return self._restore_structures(chunks, protected)


class Chunker:
    """文档分块服务，支持 Markdown 结构化切片"""
    
    def __init__(
        self,
        use_markdown_structure: bool = False,
        preserve_code_blocks: bool = True,
        preserve_tables: bool = True,
    ):
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
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
    
    def _is_markdown_file(self, file_path: Path) -> bool:
        """判断是否为 Markdown 文件"""
        return file_path.suffix.lower() in {".md", ".markdown"}
    
    def _detect_text_structure(self, text: str) -> Dict[str, Any]:
        """检测文本的结构特征"""
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
        """加载文档"""
        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            return TextLoader(str(file_path), encoding="utf-8").load()
        if suffix == ".pdf":
            return PyPDFLoader(str(file_path)).load()
        if suffix == ".docx":
            return Docx2txtLoader(str(file_path)).load()
        raise ValueError("仅支持 txt/md/pdf/docx 文档")
    
    def _build_chunk_id(self, source: str, page: int, level: int, idx: int) -> str:
        return f"{source}::p{page}::l{level}::{idx}"
    
    MIN_CHUNK_LENGTH = 30
    
    def _is_valid_chunk(self, text: str) -> bool:
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
        基于 Markdown 结构的分块策略
        
        流程：
        1. 先按标题结构分割为多个 section
        2. 每个 section 内部再进行三层嵌套分块
        3. 保留标题层级信息作为元数据
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
        三层嵌套分块：
        L1 (大块) -> L2 (中块) -> L3 (小块)
        
        对于 Markdown 文档，优先使用结构化切片
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
        处理文档，返回所有分块
        
        Returns:
            (all_chunks, all_parent_chunks)
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
