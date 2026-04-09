from langchain_core.tools import tool
import datetime


@tool
def get_current_time() -> str:
    """
    return:
        当前时间
    """
    now = datetime.datetime.now()
    
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_names[now.weekday()]
    
    period = "上午" if now.hour < 12 else "下午"
    
    return (f"现在是 {now.strftime('%Y年%m月%d日')} {weekday} "
            f"{period} {now.strftime('%H:%M:%S')}")
