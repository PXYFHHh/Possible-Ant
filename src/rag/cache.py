"""
LRU 缓存模块 —— 用于缓存 Auto-merging 的父块数据

替代 Redis 的轻量级进程内缓存，避免父块重复查询数据库。
使用场景：Retriever 在 auto_merge_documents 时需要频繁读取 L1/L2 父块文本，
通过缓存避免对 SQLite 的重复查询。

特性：
  - 线程安全（RLock 保护）
  - TTL 过期支持（默认 1 小时）
  - LRU 淘汰策略（容量满时淘汰最久未访问的条目）
  - 命中率统计
"""

import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class LruCache:
    """
    轻量级 LRU 缓存。
    
    数据结构：
      - _cache: {key: (value, expire_at_timestamp)}
      - _access_order: 按访问时间排序的 key 列表（尾部为最近访问）
    
    线程安全：所有操作通过 RLock 保护。
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Args:
            max_size: 缓存最大条目数
            ttl_seconds: 默认过期时间（秒）
        """
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_order: List[str] = []
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值。
        
        命中时将 key 移到访问队列尾部（标记为最近访问）。
        过期或不存在时返回 None。
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expire_at = self._cache[key]
            if time.time() > expire_at:
                del self._cache[key]
                self._access_order.remove(key)
                self._misses += 1
                return None
            
            self._access_order.remove(key)
            self._access_order.append(key)
            self._hits += 1
            return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存值。
        
        容量满时淘汰访问队列头部的条目（最久未访问）。
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 自定义过期时间（秒），None 则使用默认 TTL
        """
        with self._lock:
            expire_at = time.time() + (ttl or self._ttl_seconds)
            
            if key in self._cache:
                self._access_order.remove(key)
            elif len(self._cache) >= self._max_size:
                oldest = self._access_order.pop(0)
                del self._cache[oldest]
            
            self._cache[key] = (value, expire_at)
            self._access_order.append(key)
    
    def delete(self, key: str) -> bool:
        """删除指定缓存条目，返回是否成功删除"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_order.remove(key)
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
    
    def stats(self) -> Dict[str, Any]:
        """
        返回缓存统计信息。
        
        包含：当前大小、最大容量、命中数、未命中数、命中率、TTL。
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "ttl_seconds": self._ttl_seconds,
            }
