from pathlib import Path
from typing import Any, Dict, List, Tuple

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


class Chunker:
    """文档分块服务"""
    
    def __init__(self):
        self._splitter_l1 = self._build_splitter(LEVEL_1_CHUNK_SIZE, LEVEL_1_CHUNK_OVERLAP)
        self._splitter_l2 = self._build_splitter(LEVEL_2_CHUNK_SIZE, LEVEL_2_CHUNK_OVERLAP)
        self._splitter_l3 = self._build_splitter(LEVEL_3_CHUNK_SIZE, LEVEL_3_CHUNK_OVERLAP)
    
    def _build_splitter(self, chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )
    
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
    
    def split_to_three_levels(
        self,
        text: str,
        base_doc: Dict[str, Any],
        page_global_chunk_idx: int,
        doc_id: str,
        source: str,
        page: int,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        三层嵌套分块：
        L1 (大块) -> L2 (中块) -> L3 (小块)
        
        返回: (all_chunks用于向量索引, parent_chunks用于存储)
        """
        if not text or not text.strip():
            return [], []

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
            )
            all_chunks.extend(page_chunks)
            all_parent_chunks.extend(page_parent_chunks)
            page_global_chunk_idx += len(page_chunks) + len(page_parent_chunks)

        return all_chunks, all_parent_chunks
