from langchain_core.tools import tool
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import json


MANICTIME_DIR = Path(r"C:\Users\H\AppData\Local\Finkit\ManicTime")
MANICTIME_REPORTS_DB = MANICTIME_DIR / "ManicTimeReports.db"


def _get_db_connection(db_path: Path):
    """获取数据库连接"""
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在：{db_path}")
    return sqlite3.connect(str(db_path))


def _execute_query(db_path: Path, query: str, params: tuple = ()) -> list:
    """执行SQL查询"""
    conn = _get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results


def _get_table_schema(db_path: Path) -> str:
    """获取数据库表结构"""
    conn = _get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    schema_info = []
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        schema_info.append(f"\n表名：{table_name}")
        for col in columns:
            schema_info.append(f"  - {col[1]} ({col[2]})")
    
    conn.close()
    return "\n".join(schema_info)


@tool
def get_manictime_schema() -> str:
    """
    获取ManicTime数据库的表结构
    
    return:
        数据库表结构信息
    """
    try:
        result = "ManicTime 数据库结构\n"
        result += "=" * 60 + "\n"
        
        result += "\n【ManicTimeReports.db】\n"
        result += _get_table_schema(MANICTIME_REPORTS_DB)
        
        return result
    
    except Exception as e:
        return f"获取数据库结构失败：{str(e)}"


@tool
def get_today_activities() -> str:
    """
    获取今天的所有活动记录
    
    return:
        今天的活动记录和时间统计
    """
    try:
        today = datetime.now().date()
        
        query = """
        SELECT 
            a.Name,
            a.StartLocalTime,
            a.EndLocalTime,
            g.Name as GroupName
        FROM Ar_Activity a
        LEFT JOIN Ar_CommonGroup g ON a.CommonGroupId = g.CommonId
        WHERE date(a.StartLocalTime) = ?
        ORDER BY a.StartLocalTime DESC
        LIMIT 50
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (today,))
        
        if not results:
            return f"今天（{today}）还没有活动记录"
        
        activities = []
        total_duration = timedelta()
        
        for row in results:
            name, start_time, end_time, group_name = row
            
            try:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S") if end_time else start_dt
                duration = end_dt - start_dt
                total_duration += duration
                duration_str = str(duration).split('.')[0]
            except:
                duration_str = "未知"
            
            activities.append({
                "活动": name,
                "分组": group_name or "未分类",
                "开始时间": start_time,
                "结束时间": end_time,
                "持续时间": duration_str
            })
        
        total_hours = total_duration.total_seconds() / 3600
        
        result = f"今天（{today}）的活动记录\n"
        result += "=" * 60 + "\n\n"
        
        for i, activity in enumerate(activities, 1):
            result += f"{i}. {activity['活动']}\n"
            result += f"   分组：{activity['分组']}\n"
            result += f"   开始：{activity['开始时间']}\n"
            result += f"   结束：{activity['结束时间']}\n"
            result += f"   时长：{activity['持续时间']}\n\n"
        
        result += "=" * 60 + "\n"
        result += f"📊 总计活动数：{len(activities)}\n"
        result += f"⏱️  总时长：{total_hours:.2f} 小时\n"
        
        return result
    
    except Exception as e:
        return f"获取活动记录失败：{str(e)}"


@tool
def get_activities_by_date_range(
    start_date: str,
    end_date: str
) -> str:
    """
    获取指定日期范围内的活动记录
    
    params:
        start_date: 开始日期（格式：YYYY-MM-DD，如：2026-04-01）
        end_date: 结束日期（格式：YYYY-MM-DD，如：2026-04-10）
    
    return:
        指定日期范围内的活动记录和统计
    
    示例:
        get_activities_by_date_range("2026-04-01", "2026-04-10")
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        query = """
        SELECT 
            a.Name,
            a.StartLocalTime,
            a.EndLocalTime,
            g.Name as GroupName,
            date(a.StartLocalTime) as ActivityDate
        FROM Ar_Activity a
        LEFT JOIN Ar_CommonGroup g ON a.CommonGroupId = g.CommonId
        WHERE date(a.StartLocalTime) BETWEEN ? AND ?
        ORDER BY a.StartLocalTime DESC
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (start, end))
        
        if not results:
            return f"在 {start_date} 到 {end_date} 期间没有活动记录"
        
        daily_stats = {}
        activities_by_date = {}
        
        for row in results:
            name, start_time, end_time, group_name, activity_date = row
            
            if activity_date not in activities_by_date:
                activities_by_date[activity_date] = []
                daily_stats[activity_date] = {"count": 0, "total_duration": timedelta()}
            
            try:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S") if end_time else start_dt
                duration = end_dt - start_dt
                daily_stats[activity_date]["total_duration"] += duration
                duration_str = str(duration).split('.')[0]
            except:
                duration_str = "未知"
            
            activities_by_date[activity_date].append({
                "活动": name,
                "分组": group_name or "未分类",
                "开始时间": start_time,
                "结束时间": end_time,
                "持续时间": duration_str
            })
            daily_stats[activity_date]["count"] += 1
        
        result = f"活动记录（{start_date} 到 {end_date}）\n"
        result += "=" * 60 + "\n\n"
        
        for date in sorted(activities_by_date.keys(), reverse=True):
            activities = activities_by_date[date]
            stats = daily_stats[date]
            total_hours = stats["total_duration"].total_seconds() / 3600
            
            result += f"📅 {date}\n"
            result += f"   活动数：{stats['count']}\n"
            result += f"   总时长：{total_hours:.2f} 小时\n"
            result += f"   主要活动：\n"
            
            for i, activity in enumerate(activities[:5], 1):
                result += f"      {i}. {activity['活动']} ({activity['持续时间']})\n"
            
            if len(activities) > 5:
                result += f"      ... 还有 {len(activities) - 5} 个活动\n"
            
            result += "\n"
        
        total_activities = sum(s["count"] for s in daily_stats.values())
        total_duration = sum((s["total_duration"] for s in daily_stats.values()), timedelta())
        total_hours = total_duration.total_seconds() / 3600
        
        result += "=" * 60 + "\n"
        result += f"📊 总计统计\n"
        result += f"   日期数：{len(activities_by_date)}\n"
        result += f"   总活动数：{total_activities}\n"
        result += f"   总时长：{total_hours:.2f} 小时\n"
        result += f"   日均时长：{total_hours / len(activities_by_date):.2f} 小时\n"
        
        return result
    
    except Exception as e:
        return f"获取活动记录失败：{str(e)}"


@tool
def get_application_usage(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    获取应用程序使用统计
    
    params:
        start_date: 开始日期（可选，格式：YYYY-MM-DD）
        end_date: 结束日期（可选，格式：YYYY-MM-DD）
    
    return:
        应用程序使用时间统计
    
    示例:
        # 获取今天的应用使用统计
        get_application_usage()
        
        # 获取指定日期范围的统计
        get_application_usage("2026-04-01", "2026-04-10")
    """
    try:
        if start_date is None or end_date is None:
            today = datetime.now().date()
            start_date = str(today)
            end_date = str(today)
        
        query = """
        SELECT 
            g.Name as AppName,
            COUNT(*) as UsageCount,
            SUM(
                CAST((julianday(a.EndLocalTime) - julianday(a.StartLocalTime)) * 86400 AS INTEGER)
            ) as TotalSeconds
        FROM Ar_Activity a
        LEFT JOIN Ar_CommonGroup g ON a.CommonGroupId = g.CommonId
        WHERE date(a.StartLocalTime) BETWEEN ? AND ?
        AND g.Name IS NOT NULL
        GROUP BY g.Name
        ORDER BY TotalSeconds DESC
        LIMIT 20
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (start_date, end_date))
        
        if not results:
            return f"在 {start_date} 到 {end_date} 期间没有应用使用记录"
        
        result = f"应用程序使用统计（{start_date} 到 {end_date}）\n"
        result += "=" * 60 + "\n\n"
        
        total_duration = 0
        
        for i, row in enumerate(results, 1):
            app_name, usage_count, total_seconds = row
            
            if total_seconds:
                total_duration += total_seconds
                duration_str = str(timedelta(seconds=int(total_seconds)))
                hours = total_seconds / 3600
            else:
                duration_str = "未知"
                hours = 0
            
            result += f"{i}. {app_name}\n"
            result += f"   使用次数：{usage_count}\n"
            result += f"   总时长：{duration_str} ({hours:.2f} 小时)\n\n"
        
        total_hours = total_duration / 3600
        
        result += "=" * 60 + "\n"
        result += f"📊 总计统计\n"
        result += f"   应用数量：{len(results)}\n"
        result += f"   总使用时长：{total_hours:.2f} 小时\n"
        
        return result
    
    except Exception as e:
        return f"获取应用使用统计失败：{str(e)}"


@tool
def get_productivity_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    获取生产力摘要报告
    
    params:
        start_date: 开始日期（可选，格式：YYYY-MM-DD）
        end_date: 结束日期（可选，格式：YYYY-MM-DD）
    
    return:
        生产力摘要报告，包括最常使用的应用、活动时间分布等
    
    示例:
        # 获取今天的生产力摘要
        get_productivity_summary()
        
        # 获取指定日期范围的生产力摘要
        get_productivity_summary("2026-04-01", "2026-04-10")
    """
    try:
        if start_date is None or end_date is None:
            today = datetime.now().date()
            start_date = str(today)
            end_date = str(today)
        
        query = """
        SELECT 
            g.Name as AppName,
            a.StartLocalTime,
            CAST((julianday(a.EndLocalTime) - julianday(a.StartLocalTime)) * 86400 AS INTEGER) as DurationSeconds
        FROM Ar_Activity a
        LEFT JOIN Ar_CommonGroup g ON a.CommonGroupId = g.CommonId
        WHERE date(a.StartLocalTime) BETWEEN ? AND ?
        ORDER BY a.StartLocalTime
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (start_date, end_date))
        
        if not results:
            return f"在 {start_date} 到 {end_date} 期间没有活动记录"
        
        app_usage = {}
        hourly_distribution = {i: 0 for i in range(24)}
        total_duration = 0
        
        for row in results:
            app_name, start_time, duration_seconds = row
            
            if duration_seconds:
                total_duration += duration_seconds
                
                if app_name:
                    if app_name not in app_usage:
                        app_usage[app_name] = 0
                    app_usage[app_name] += duration_seconds
                
                try:
                    start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                    hour = start_dt.hour
                    hourly_distribution[hour] += duration_seconds
                except:
                    pass
        
        sorted_apps = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)
        
        result = f"生产力摘要报告（{start_date} 到 {end_date}）\n"
        result += "=" * 60 + "\n\n"
        
        result += "🏆 最常使用的应用（Top 10）\n"
        result += "-" * 60 + "\n"
        for i, (app, duration) in enumerate(sorted_apps[:10], 1):
            hours = duration / 3600
            percentage = (duration / total_duration * 100) if total_duration > 0 else 0
            result += f"{i}. {app}\n"
            result += f"   {hours:.2f} 小时 ({percentage:.1f}%)\n"
        
        result += "\n⏰ 活跃时间分布\n"
        result += "-" * 60 + "\n"
        
        peak_hours = sorted(hourly_distribution.items(), key=lambda x: x[1], reverse=True)[:5]
        
        for hour, duration in peak_hours:
            if duration > 0:
                hours = duration / 3600
                result += f"{hour:02d}:00 - {hour+1:02d}:00  {hours:.2f} 小时\n"
        
        total_hours = total_duration / 3600
        
        result += "\n" + "=" * 60 + "\n"
        result += "📊 总体统计\n"
        result += "-" * 60 + "\n"
        result += f"总使用时长：{total_hours:.2f} 小时\n"
        result += f"应用数量：{len(app_usage)}\n"
        result += f"平均每小时切换应用：{len(results) / max(total_hours, 1):.1f} 次\n"
        
        return result
    
    except Exception as e:
        return f"获取生产力摘要失败：{str(e)}"


@tool
def get_screen_time_today() -> str:
    """
    获取今天的屏幕活跃时间（实际使用电脑的时间）
    
    return:
        今天的屏幕活跃时间和离开时间统计
    
    说明:
        - Active: 屏幕活跃（您正在使用电脑）
        - Away: 电脑开启但您不在使用（离开、锁屏等）
    
    示例:
        get_screen_time_today()
    """
    try:
        today = datetime.now().date()
        
        query = """
        SELECT 
            a.Name,
            COUNT(*) as Count,
            SUM(CAST((julianday(a.EndLocalTime) - julianday(a.StartLocalTime)) * 86400 AS INTEGER)) as TotalSeconds,
            a.StartLocalTime,
            a.EndLocalTime
        FROM Ar_Activity a
        WHERE a.Name IN ('Active', 'Away')
          AND date(a.StartLocalTime) = ?
        GROUP BY a.Name, a.ActivityId
        ORDER BY a.StartLocalTime
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (today,))
        
        if not results:
            return f"今天（{today}）还没有屏幕使用记录"
        
        active_sessions = []
        away_sessions = []
        total_active_seconds = 0
        total_away_seconds = 0
        
        for row in results:
            name, count, total_seconds, start_time, end_time = row
            
            if name == 'Active':
                total_active_seconds += total_seconds if total_seconds else 0
                active_sessions.append({
                    "开始": start_time,
                    "结束": end_time,
                    "时长": str(timedelta(seconds=int(total_seconds))) if total_seconds else "未知"
                })
            elif name == 'Away':
                total_away_seconds += total_seconds if total_seconds else 0
                away_sessions.append({
                    "开始": start_time,
                    "结束": end_time,
                    "时长": str(timedelta(seconds=int(total_seconds))) if total_seconds else "未知"
                })
        
        total_screen_seconds = total_active_seconds + total_away_seconds
        active_percentage = (total_active_seconds / total_screen_seconds * 100) if total_screen_seconds > 0 else 0
        
        result = f"📱 今天（{today}）的屏幕使用报告\n"
        result += "=" * 60 + "\n\n"
        
        result += "⏰ 时间统计\n"
        result += "-" * 60 + "\n"
        result += f"🟢 屏幕活跃时间（Active）：{timedelta(seconds=int(total_active_seconds))} ({total_active_seconds/3600:.2f} 小时)\n"
        result += f"🔴 离开时间（Away）：{timedelta(seconds=int(total_away_seconds))} ({total_away_seconds/3600:.2f} 小时)\n"
        result += f"📊 总计开机时间：{timedelta(seconds=int(total_screen_seconds))} ({total_screen_seconds/3600:.2f} 小时)\n"
        result += f"✅ 活跃时间占比：{active_percentage:.1f}%\n"
        
        result += "\n\n🟢 活跃时段详情\n"
        result += "-" * 60 + "\n"
        for i, session in enumerate(active_sessions, 1):
            result += f"{i}. {session['开始']} - {session['结束']} ({session['时长']})\n"
        
        result += f"\n共 {len(active_sessions)} 个活跃时段\n"
        
        return result
    
    except Exception as e:
        return f"获取屏幕活跃时间失败：{str(e)}"


@tool
def get_screen_time_by_date(
    date: str
) -> str:
    """
    获取指定日期的屏幕活跃时间
    
    params:
        date: 日期（格式：YYYY-MM-DD，如：2026-04-09）
    
    return:
        指定日期的屏幕活跃时间和离开时间统计
    
    示例:
        get_screen_time_by_date("2026-04-09")
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        
        query = """
        SELECT 
            a.Name,
            COUNT(*) as Count,
            SUM(CAST((julianday(a.EndLocalTime) - julianday(a.StartLocalTime)) * 86400 AS INTEGER)) as TotalSeconds,
            a.StartLocalTime,
            a.EndLocalTime
        FROM Ar_Activity a
        WHERE a.Name IN ('Active', 'Away')
          AND date(a.StartLocalTime) = ?
        GROUP BY a.Name, a.ActivityId
        ORDER BY a.StartLocalTime
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (target_date,))
        
        if not results:
            return f"{date} 没有屏幕使用记录"
        
        active_sessions = []
        away_sessions = []
        total_active_seconds = 0
        total_away_seconds = 0
        
        for row in results:
            name, count, total_seconds, start_time, end_time = row
            
            if name == 'Active':
                total_active_seconds += total_seconds if total_seconds else 0
                active_sessions.append({
                    "开始": start_time,
                    "结束": end_time,
                    "时长": str(timedelta(seconds=int(total_seconds))) if total_seconds else "未知"
                })
            elif name == 'Away':
                total_away_seconds += total_seconds if total_seconds else 0
                away_sessions.append({
                    "开始": start_time,
                    "结束": end_time,
                    "时长": str(timedelta(seconds=int(total_seconds))) if total_seconds else "未知"
                })
        
        total_screen_seconds = total_active_seconds + total_away_seconds
        active_percentage = (total_active_seconds / total_screen_seconds * 100) if total_screen_seconds > 0 else 0
        
        result = f"📱 {date} 的屏幕使用报告\n"
        result += "=" * 60 + "\n\n"
        
        result += "⏰ 时间统计\n"
        result += "-" * 60 + "\n"
        result += f"🟢 屏幕活跃时间（Active）：{timedelta(seconds=int(total_active_seconds))} ({total_active_seconds/3600:.2f} 小时)\n"
        result += f"🔴 离开时间（Away）：{timedelta(seconds=int(total_away_seconds))} ({total_away_seconds/3600:.2f} 小时)\n"
        result += f"📊 总计开机时间：{timedelta(seconds=int(total_screen_seconds))} ({total_screen_seconds/3600:.2f} 小时)\n"
        result += f"✅ 活跃时间占比：{active_percentage:.1f}%\n"
        
        result += "\n\n🟢 活跃时段详情\n"
        result += "-" * 60 + "\n"
        for i, session in enumerate(active_sessions, 1):
            result += f"{i}. {session['开始']} - {session['结束']} ({session['时长']})\n"
        
        result += f"\n共 {len(active_sessions)} 个活跃时段，{len(away_sessions)} 个离开时段\n"
        
        return result
    
    except Exception as e:
        return f"获取屏幕活跃时间失败：{str(e)}"


@tool
def get_productivity_with_screen_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    获取包含屏幕活跃时间的生产力摘要报告
    
    params:
        start_date: 开始日期（可选，格式：YYYY-MM-DD）
        end_date: 结束日期（可选，格式：YYYY-MM-DD）
    
    return:
        包含屏幕活跃时间的详细生产力报告
    
    示例:
        # 获取今天的带屏幕时间的生产力摘要
        get_productivity_with_screen_time()
        
        # 获取指定日期范围的报告
        get_productivity_with_screen_time("2026-04-01", "2026-04-10")
    """
    try:
        if start_date is None or end_date is None:
            today = datetime.now().date()
            start_date = str(today)
            end_date = str(today)
        
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        query = """
        SELECT 
            a.Name,
            date(a.StartLocalTime) as ActivityDate,
            SUM(CAST((julianday(a.EndLocalTime) - julianday(a.StartLocalTime)) * 86400 AS INTEGER)) as TotalSeconds
        FROM Ar_Activity a
        WHERE a.Name IN ('Active', 'Away')
          AND date(a.StartLocalTime) BETWEEN ? AND ?
        GROUP BY a.Name, date(a.StartLocalTime)
        ORDER BY ActivityDate DESC, a.Name
        """
        
        results = _execute_query(MANICTIME_REPORTS_DB, query, (start, end))
        
        if not results:
            return f"在 {start_date} 到 {end_date} 期间没有屏幕使用记录"
        
        daily_stats = {}
        
        for row in results:
            name, activity_date, total_seconds = row
            
            if activity_date not in daily_stats:
                daily_stats[activity_date] = {"active": 0, "away": 0}
            
            if name == 'Active':
                daily_stats[activity_date]["active"] += total_seconds if total_seconds else 0
            elif name == 'Away':
                daily_stats[activity_date]["away"] += total_seconds if total_seconds else 0
        
        result = f"📊 屏幕活跃时间报告（{start_date} 到 {end_date}）\n"
        result += "=" * 60 + "\n\n"
        
        total_active_all = 0
        total_away_all = 0
        
        for date in sorted(daily_stats.keys(), reverse=True):
            stats = daily_stats[date]
            active_sec = stats["active"]
            away_sec = stats["away"]
            total_sec = active_sec + away_sec
            active_pct = (active_sec / total_sec * 100) if total_sec > 0 else 0
            
            total_active_all += active_sec
            total_away_all += away_sec
            
            result += f"📅 {date}\n"
            result += f"   🟢 活跃：{timedelta(seconds=int(active_sec))} ({active_sec/3600:.2f}h)\n"
            result += f"   🔴 离开：{timedelta(seconds=int(away_sec))} ({away_sec/3600:.2f}h)\n"
            result += f"   📊 占比：{active_pct:.1f}%\n\n"
        
        total_all = total_active_all + total_away_all
        avg_active_pct = (total_active_all / total_all * 100) if total_all > 0 else 0
        days_count = len(daily_stats)
        
        result += "=" * 60 + "\n"
        result += "📈 汇总统计\n"
        result += "-" * 60 + "\n"
        result += f"总活跃时间：{timedelta(seconds=int(total_active_all))} ({total_active_all/3600:.2f} 小时)\n"
        result += f"总离开时间：{timedelta(seconds=int(total_away_all))} ({total_away_all/3600:.2f} 小时)\n"
        result += f"日均活跃：{timedelta(seconds=int(total_active_all/days_count))} ({total_active_all/3600/days_count:.2f} 小时)\n"
        result += f"平均活跃占比：{avg_active_pct:.1f}%\n"
        
        return result
    
    except Exception as e:
        return f"获取生产力报告失败：{str(e)}"
