from langchain_core.tools import tool
from ddgs import DDGS
import re


INAPPROPRIATE_KEYWORDS = [
    'porn', 'sex', 'adult', 'xxx', 'nude', '裸体', '色情', '成人',
    '大尺度', '露脸', '自慰', '高潮', '肉棒', '做爱', '性爱',
    'swag', 'onlyfans', '直播', '私密', '激情',
    '群p', '轮草', '口交', '淫乱', '群交', '炸裂',
    '精神小妹', '精神小伙', '纹身', '91吃瓜',
    '强奸', '乱伦', '偷拍', '迷奸', '轮奸',
    'av', '女优', '中出', '内射', '颜射',
    'sm', '调教', '奴役', '虐待',
    '乱交', '群淫', '淫荡', '骚货'
]

LOW_QUALITY_DOMAINS = [
    'bbj75.com', 'downxia.com', 'blsql.com', 'htropw.sbs'
]


def _is_appropriate(result: dict) -> bool:
    """
    判断搜索结果是否合适
    
    params:
        result: 搜索结果字典
    
    return:
        True表示合适，False表示不合适
    """
    title = result.get('title', '').lower()
    body = result.get('body', '').lower()
    href = result.get('href', '').lower()
    
    for keyword in INAPPROPRIATE_KEYWORDS:
        if keyword in title or keyword in body:
            return False
    
    for domain in LOW_QUALITY_DOMAINS:
        if domain in href:
            return False
    
    if len(body.strip()) < 20:
        return False
    
    return True


def _clean_text(text: str) -> str:
    """
    清理文本中的特殊字符和多余空格
    
    params:
        text: 原始文本
    
    return:
        清理后的文本
    """
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


@tool
def get_search_results(query: str, max_results: int = 5) -> str:
    """
    执行网络搜索并返回过滤后的高质量结果
    
    params:
        query: 搜索关键词
        max_results: 最大返回结果数（默认5）
    
    return:
        过滤后的搜索结果
    """
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max_results * 2)
        
        if not results:
            return f"未搜索到关于【{query}】的相关结果"
        
        filtered_results = []
        for r in results:
            if _is_appropriate(r):
                filtered_results.append(r)
                if len(filtered_results) >= max_results:
                    break
        
        if not filtered_results:
            return f"未找到关于【{query}】的合适搜索结果，请尝试其他关键词"
        
        formatted = []
        for i, r in enumerate(filtered_results, 1):
            title = _clean_text(r.get('title', '无标题'))
            href = r.get('href', '无链接')
            body = _clean_text(r.get('body', '无摘要'))
            
            formatted.append(
                f"{i}. 标题: {title}\n"
                f"   链接: {href}\n"
                f"   摘要: {body}"
            )
        
        return "\n\n".join(formatted)
    
    except Exception as e:
        return f"搜索失败：网络异常或服务不可用，错误信息：{str(e)[:100]}"