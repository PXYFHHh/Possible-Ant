import os
import requests
from langchain_core.tools import tool
from datetime import datetime, timedelta


@tool
def get_deepseek_balance() -> str:
    """
    查询 DeepSeek API 账户余额信息。
    
    返回账户的总余额、赠金余额和充值余额等信息。
    
    return:
        余额信息的格式化字符串
    """
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    if not api_key:
        return "错误：未找到 DEEPSEEK_API_KEY 环境变量"

    if base_url != "https://api.deepseek.com/v1":
        return "暂不支持deepseek外的模型"
    
    url = "https://api.deepseek.com/user/balance"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if not data.get("is_available", False):
                return "账户当前无可用余额"
            
            result_lines = ["📊 DeepSeek 账户余额信息：\n"]
            
            for info in data.get("balance_infos", []):
                currency = info.get("currency", "CNY")
                total = info.get("total_balance", "0")
                granted = info.get("granted_balance", "0")
                topped_up = info.get("topped_up_balance", "0")
                
                result_lines.append(f"货币类型: {currency}")
                result_lines.append(f"总可用余额: {total}")
                result_lines.append(f"赠金余额: {granted}")
                result_lines.append(f"充值余额: {topped_up}")
            
            return "\n".join(result_lines)
        
        else:
            return f"查询失败: HTTP {response.status_code} - {response.text}"
    
    except requests.exceptions.Timeout:
        return "查询超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        return f"网络请求错误: {str(e)}"
    except Exception as e:
        return f"查询出错: {str(e)}"


@tool
def get_deepseek_usage(start_date: str = None, end_date: str = None) -> str:
    """
    查询 DeepSeek API 在指定时间范围内的使用量。
    
    args:
        start_date: 起始日期，格式 YYYY-MM-DD，默认为7天前
        end_date: 结束日期，格式 YYYY-MM-DD，默认为今天
    
    return:
        使用量信息的格式化字符串
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return "错误：未找到 LLM_API_KEY 环境变量"
    
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    url = "https://api.deepseek.com/v1/usage"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    params = {
        "start_date": start_date,
        "end_date": end_date
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            result_lines = [f"📈 DeepSeek API 使用量 ({start_date} 至 {end_date})：\n"]
            
            usage_infos = data.get("daily_usage_infos", [])
            
            if not usage_infos:
                return f"在 {start_date} 至 {end_date} 期间没有使用记录"
            
            total_prompt = 0
            total_completion = 0
            total_cached = 0
            
            for info in usage_infos:
                date = info.get("date", "未知")
                prompt = info.get("prompt_tokens", 0)
                completion = info.get("completion_tokens", 0)
                cached = info.get("cached_tokens", 0)
                
                total_prompt += prompt
                total_completion += completion
                total_cached += cached
                
                result_lines.append(
                    f"📅 {date}: 输入 {prompt:,} | 输出 {completion:,} | 缓存 {cached:,}"
                )
            
            result_lines.append(f"\n📊 汇总:")
            result_lines.append(f"总输入 tokens: {total_prompt:,}")
            result_lines.append(f"总输出 tokens: {total_completion:,}")
            result_lines.append(f"总缓存 tokens: {total_cached:,}")
            
            return "\n".join(result_lines)
        
        else:
            return f"查询失败: HTTP {response.status_code} - {response.text}"
    
    except requests.exceptions.Timeout:
        return "查询超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        return f"网络请求错误: {str(e)}"
    except Exception as e:
        return f"查询出错: {str(e)}"
