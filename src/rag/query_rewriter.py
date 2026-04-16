import os
import re
from typing import List
_STOPWORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就",
    "不", "人", "都", "一", "个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "什么", "怎么",
    "如何", "哪些", "哪个", "吗", "呢", "吧", "呀",
    "啊", "哦", "嗯", "关于", "对于", "根据", "按照",
    "中", "之", "以", "及", "其", "与", "或", "等",
    "被", "把", "对", "从", "向", "为", "由",
    "请问", "麻烦", "帮我", "帮忙", "我想知道", "告诉我", "请你",
    "可以", "能否", "能不能", "有没有", "一下", "一下子", "这个", "那个",
}
_PUNCT_RE = re.compile(r"[，。！？；：、,.!?;:()（）\[\]{}\"'“”‘’`]+")
_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9_./:-]+")
_FILLER_RE = re.compile(
    r"(请问|麻烦|帮我|帮忙|我想知道|告诉我|请你|可以|能否|能不能|有没有|一下|一下子|这个|那个)"
)
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
RAG_QUERY_VARIANT_LIMIT = max(1, min(_env_int("RAG_QUERY_VARIANT_LIMIT", 4), 6))
def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
def normalize_query_text(query: str) -> str:
    text = str(query or "").strip()
    text = _SPACE_RE.sub(" ", text)
    return text
def simplify_query_text(query: str) -> str:
    text = normalize_query_text(query)
    text = _PUNCT_RE.sub(" ", text)
    text = _FILLER_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip(" ?？")
    return text
def extract_query_keywords(query: str, limit: int = 8) -> List[str]:
    tokens = _TOKEN_RE.findall(normalize_query_text(query).lower())
    result: List[str] = []
    seen = set()
    for token in tokens:
        token = token.strip()
        if not token or token in _STOPWORDS:
            continue
        if len(token) == 1 and re.fullmatch(r"[\u4e00-\u9fff]", token):
            continue
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
        if len(result) >= limit:
            break
    return result
def build_query_variants(query: str, max_variants: int = RAG_QUERY_VARIANT_LIMIT) -> List[str]:
    base = normalize_query_text(query)
    if not base:
        return []
    simplified = simplify_query_text(base)
    keywords = extract_query_keywords(base)
    keyword_query = " ".join(keywords[:6]) if keywords else ""
    variants: List[str] = [base]
    if simplified and simplified != base:
        variants.append(simplified)
    if keyword_query and keyword_query not in {base, simplified}:
        variants.append(keyword_query)
    intent_seed = simplified or base
    if re.search(r"(是什么|含义|定义|概念|原理)", base):
        variants.append(f"{intent_seed} 定义 概念")
    elif re.search(r"(怎么|如何|怎样|步骤|流程|实现)", base):
        variants.append(f"{intent_seed} 方法 步骤 实现")
    elif re.search(r"(区别|差异|对比|不同)", base):
        variants.append(f"{intent_seed} 区别 对比")
    elif re.search(r"(配置|参数|环境变量)", base):
        variants.append(f"{intent_seed} 配置 参数 环境变量")
    return _dedupe_keep_order(variants)[:max_variants]
def build_variant_weights(count: int) -> List[float]:
    if count <= 0:
        return []
    weights = [1.0]
    next_weight = 0.82
    for _ in range(1, count):
        weights.append(next_weight)
        next_weight = max(0.5, next_weight - 0.12)
    return weights[:count]