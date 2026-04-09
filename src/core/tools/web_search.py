from langchain_core.tools import tool
# 替换为新的官方库 ddgs
from ddgs import DDGS


@tool
def get_search_results(query: str) -> str:
    """
    params:
        query: 搜索关键词
    return:
        搜索结果
    """
    try:
        # 初始化搜索客户端
        ddgs = DDGS()
        # 执行搜索，捕获网络/连接异常
        results = ddgs.text(query, max_results=3)
        
        # 处理无搜索结果的情况
        if not results:
            return f"未搜索到关于【{query}】的相关结果"
        
        # 格式化结果
        formatted = []
        for r in results:
            formatted.append(
                f"标题: {r.get('title', '无标题')}\n"
                f"链接: {r.get('href', '无链接')}\n"
                f"摘要: {r.get('body', '无摘要')}"
            )
        
        return "\n\n".join(formatted)
    
    except Exception as e:
        # 核心：捕获所有异常（网络错误、连接失败等），返回友好提示，不崩溃
        return f"搜索失败：网络异常或服务不可用，错误信息：{str(e)[:100]}"