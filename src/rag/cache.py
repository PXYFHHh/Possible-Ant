import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class LruCache:
    """
    轻量级LRU缓存（替代Redis）
    
    特性：
    - 线程安全
    - TTL过期支持
    - LRU淘汰策略
    - 命中率统计
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_order: List[str] = []
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
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
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_order.remove(key)
                return True
            return False
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
    
    def stats(self) -> Dict[str, Any]:
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
