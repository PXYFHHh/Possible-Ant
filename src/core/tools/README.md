# 工具模块说明

## 文件结构

```
src/core/tools/
├── __init__.py              # 工具导出
├── get_time.py              # 获取当前时间工具
├── web_search.py            # 网络搜索工具
├── file_manager.py          # 文件管理工具集
├── calculator.py            # 计算器工具
├── plot_tool.py             # 绘图工具集
└── manictime_tracker.py     # ManicTime追踪工具集
```

## 工具列表

### 1. get_time.py - 时间工具
**工具名称**: `get_current_time`

**功能**: 获取当前系统时间

**返回格式**: 
```
现在是 2026年4月10日 星期五 上午 00:44:25
```

**使用示例**:
```python
from src.core.tools import get_current_time

# 直接调用
result = get_current_time.invoke({})

# 在Agent中使用
agent.React_Agent_Stream("现在几点了？")
```

---

### 2. web_search.py - 网络搜索工具
**工具名称**: `get_search_results`

**功能**: 使用DuckDuckGo搜索引擎进行网络搜索，自动过滤不适当内容

**参数**:
- `query` (str): 搜索关键词
- `max_results` (int, 可选): 最大返回结果数（默认5）

**过滤功能**:
- ✅ 过滤不适当关键词（成人内容、色情等）
- ✅ 过滤低质量域名
- ✅ 过滤内容过短的摘要（少于20字符）
- ✅ 清理文本中的多余空格和换行符

**返回格式**:
```
1. 标题: [新闻标题]
   链接: [URL]
   摘要: [内容摘要]
```

**使用示例**:
```python
from src.core.tools import get_search_results

# 直接调用（默认返回5个结果）
result = get_search_results.invoke({"query": "今日新闻"})

# 指定返回结果数量
result = get_search_results.invoke({"query": "Python教程", "max_results": 10})

# 在Agent中使用
agent.React_Agent_Stream("搜索一下今天的新闻")
```

**过滤示例**:
```python
# 不适当的内容会被自动过滤
# 例如包含"大尺度"、"色情"等关键词的结果会被过滤
# 低质量域名的链接也会被过滤
```

---

### 3. file_manager.py - 文件管理工具集

#### 3.1 create_file - 创建文件
**功能**: 在files文件夹中创建新文件

**参数**:
- `filename` (str): 文件名
- `content` (str): 文件内容

**使用示例**:
```python
create_file.invoke({"filename": "test.txt", "content": "你好"})
```

#### 3.2 overwrite_file - 覆盖文件
**功能**: 覆盖已存在文件的内容

**参数**:
- `filename` (str): 文件名
- `content` (str): 新内容

**使用示例**:
```python
overwrite_file.invoke({"filename": "test.txt", "content": "新内容"})
```

#### 3.3 read_file - 读取文件
**功能**: 读取文件内容

**参数**:
- `filename` (str): 文件名

**使用示例**:
```python
read_file.invoke({"filename": "test.txt"})
```

#### 3.4 delete_file - 删除文件
**功能**: 删除指定文件

**参数**:
- `filename` (str): 文件名

**使用示例**:
```python
delete_file.invoke({"filename": "test.txt"})
```

#### 3.5 delete_multiple_files - 批量删除文件
**功能**: 批量删除多个文件，支持排除特定文件

**参数**:
- `filenames` (str): 要删除的文件名列表，用逗号分隔
- `exclude` (str, 可选): 要保留的文件名列表，用逗号分隔

**使用场景**:
- 删除多个指定文件
- 删除所有文件但保留某些重要文件
- 清理文件夹，只保留特定文件

**使用示例**:
```python
# 删除指定文件
delete_multiple_files.invoke({
    "filenames": "file1.txt,file2.txt,file3.png"
})

# 删除所有文件，但保留README.md
delete_multiple_files.invoke({
    "filenames": "",
    "exclude": "README.md"
})

# 删除多个文件，但保留某些重要文件
delete_multiple_files.invoke({
    "filenames": "data1.txt,data2.txt,data3.txt",
    "exclude": "README.md,config.json"
})
```

**优势**:
- ✅ 一次调用删除多个文件，节省token
- ✅ 支持批量操作，提高效率
- ✅ 自动统计删除结果和释放空间
- ✅ 支持排除特定文件

#### 3.6 list_files - 列出文件
**功能**: 列出files文件夹中的所有文件

**使用示例**:
```python
list_files.invoke({})
```

---

### 4. calculator.py - 计算器工具

#### 4.1 calculate - 数学表达式计算
**功能**: 安全地计算数学表达式

**参数**:
- `expression` (str): 数学表达式

**支持的操作**:
- 基本运算: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- 数学函数: `sqrt`, `sin`, `cos`, `tan`, `log`, `exp`, `floor`, `ceil`, `abs`, `round`, `min`, `max`
- 数学常量: `pi`, `e`

**使用示例**:
```python
# 基本运算
calculate.invoke({"expression": "2 + 3 * 4"})

# 幂运算
calculate.invoke({"expression": "2 ** 10"})

# 数学函数
calculate.invoke({"expression": "sqrt(16)"})

# 使用常量
calculate.invoke({"expression": "pi * 2"})

# 复杂表达式
calculate.invoke({"expression": "sqrt(16) + sin(pi/2)"})
```

#### 4.2 calculate_percentage - 百分比计算
**功能**: 计算数值的百分比

**参数**:
- `value` (float): 基础数值
- `percentage` (float): 百分比

**使用示例**:
```python
calculate_percentage.invoke({"value": 100, "percentage": 20})
```

#### 4.3 calculate_average - 平均值计算
**功能**: 计算数字列表的平均值

**参数**:
- `numbers` (str): 数字列表，用逗号分隔

**使用示例**:
```python
calculate_average.invoke({"numbers": "1, 2, 3, 4, 5"})
```

---

### 5. plot_tool.py - 绘图工具集

#### 5.1 plot_line_chart - 折线图
**功能**: 绘制折线图

**参数**:
- `filename` (str): 保存的文件名（不含扩展名）
- `x_data` (str): X轴数据
- `y_data` (str): Y轴数据
- `title` (str): 图表标题
- `x_label` (str): X轴标签
- `y_label` (str): Y轴标签
- `line_color` (str): 线条颜色
- `line_width` (int): 线条宽度
- `marker` (str): 数据点标记
- `grid` (bool): 是否显示网格

**使用示例**:
```python
plot_line_chart.invoke({
    "filename": "sales_trend",
    "x_data": "1,2,3,4,5,6",
    "y_data": "100,150,120,180,200,250",
    "title": "销售趋势",
    "x_label": "月份",
    "y_label": "销售额"
})
```

#### 5.2 plot_bar_chart - 柱状图
**功能**: 绘制柱状图（支持水平和垂直）

**参数**:
- `filename` (str): 保存的文件名
- `categories` (str): 类别名称
- `values` (str): 数值数据
- `title` (str): 图表标题
- `x_label` (str): X轴标签
- `y_label` (str): Y轴标签
- `color` (str): 柱子颜色
- `show_values` (bool): 是否显示数值
- `horizontal` (bool): 是否水平显示

**使用示例**:
```python
plot_bar_chart.invoke({
    "filename": "product_sales",
    "categories": "产品A,产品B,产品C",
    "values": "120,150,100",
    "title": "产品销售对比"
})
```

#### 5.3 plot_pie_chart - 饼图
**功能**: 绘制饼图

**参数**:
- `filename` (str): 保存的文件名
- `labels` (str): 标签名称
- `values` (str): 数值数据
- `title` (str): 图表标题
- `colors` (str): 自定义颜色（可选）
- `explode` (str): 突出显示（可选）
- `show_percentage` (bool): 是否显示百分比
- `start_angle` (int): 起始角度

**使用示例**:
```python
plot_pie_chart.invoke({
    "filename": "market_share",
    "labels": "产品A,产品B,产品C",
    "values": "40,35,25",
    "title": "市场份额"
})
```

#### 5.4 plot_scatter_chart - 散点图
**功能**: 绘制散点图（支持回归线）

**参数**:
- `filename` (str): 保存的文件名
- `x_data` (str): X轴数据
- `y_data` (str): Y轴数据
- `title` (str): 图表标题
- `x_label` (str): X轴标签
- `y_label` (str): Y轴标签
- `color` (str): 点的颜色
- `size` (int): 点的大小
- `show_regression` (bool): 是否显示回归线

**使用示例**:
```python
plot_scatter_chart.invoke({
    "filename": "correlation",
    "x_data": "1,2,3,4,5,6,7,8,9,10",
    "y_data": "2,4,5,4,5,7,8,9,10,11",
    "title": "相关性分析",
    "show_regression": True
})
```

#### 5.5 plot_histogram - 直方图
**功能**: 绘制直方图（支持核密度估计）

**参数**:
- `filename` (str): 保存的文件名
- `data` (str): 数据
- `title` (str): 图表标题
- `x_label` (str): X轴标签
- `y_label` (str): Y轴标签
- `bins` (int): 柱子数量
- `color` (str): 柱子颜色
- `show_edge` (bool): 是否显示边框
- `show_kde` (bool): 是否显示核密度估计曲线

**使用示例**:
```python
plot_histogram.invoke({
    "filename": "age_distribution",
    "data": "25,30,35,40,45,50,55,60,65,70,75,80",
    "title": "年龄分布",
    "bins": 5
})
```

#### 5.6 plot_multi_line_chart - 多线折线图
**功能**: 绘制多条折线图

**参数**:
- `filename` (str): 保存的文件名
- `x_data` (str): X轴数据
- `y_data_list` (str): Y轴数据列表（用|分隔多条线）
- `labels` (str): 各条线的标签
- `title` (str): 图表标题
- `x_label` (str): X轴标签
- `y_label` (str): Y轴标签
- `colors` (str): 自定义颜色（可选）

**使用示例**:
```python
plot_multi_line_chart.invoke({
    "filename": "sales_comparison",
    "x_data": "1,2,3,4,5,6",
    "y_data_list": "100,150,120,180,200,250|80,120,100,150,180,220",
    "labels": "产品A,产品B",
    "title": "销售对比"
})
```

## 命名规则

- **get_time.py**: 获取时间，简洁明了
- **web_search.py**: 网络搜索，明确功能
- **file_manager.py**: 文件管理器，体现管理多个文件操作
- **calculator.py**: 计算器，直观明了
- **plot_tool.py**: 绘图工具，支持多种图表类型
- **manictime_tracker.py**: ManicTime追踪工具，访问时间追踪数据

## 安全特性

1. **文件操作限制**: 只允许在 `files` 文件夹内操作
2. **文件名验证**: 禁止路径遍历和特殊字符
3. **错误处理**: 所有工具都有完善的异常处理
4. **友好提示**: 提供清晰的操作反馈

---

### 6. manictime_tracker.py - ManicTime追踪工具集

ManicTime是一个时间追踪软件，记录您的电脑使用情况。这个工具集可以访问ManicTime数据库，分析您的活动记录。

#### 6.1 get_manictime_schema - 获取数据库结构
**功能**: 获取ManicTime数据库的表结构信息

**使用示例**:
```python
get_manictime_schema.invoke({})
```

#### 6.2 get_today_activities - 获取今天的活动记录
**功能**: 获取今天的所有活动记录和时间统计

**返回格式**:
```
今天（2026-04-10）的活动记录
============================================================

1. main.py - agent - Trae CN
   分组：Trae CN
   开始：2026-04-10 04:53:19
   结束：2026-04-10 04:54:03
   时长：0:00:44

2. manictime_tracker.py - agent - Trae CN
   分组：Trae CN
   开始：2026-04-10 04:52:35
   结束：2026-04-10 04:53:19
   时长：0:00:44

...

============================================================
📊 总计活动数：50
⏱️  总时长：0.38 小时
```

**使用示例**:
```python
get_today_activities.invoke({})

# 在Agent中使用
agent.React_Agent_Stream("我今天都干了什么？")
```

#### 6.3 get_activities_by_date_range - 获取指定日期范围的活动记录
**功能**: 获取指定日期范围内的活动记录和统计

**参数**:
- `start_date` (str): 开始日期（格式：YYYY-MM-DD）
- `end_date` (str): 结束日期（格式：YYYY-MM-DD）

**使用示例**:
```python
# 获取过去一周的活动
get_activities_by_date_range.invoke({
    "start_date": "2026-04-01",
    "end_date": "2026-04-10"
})

# 在Agent中使用
agent.React_Agent_Stream("查看我4月1号到4月10号的活动记录")
```

#### 6.4 get_application_usage - 获取应用程序使用统计
**功能**: 获取应用程序使用时间统计

**参数**:
- `start_date` (str, 可选): 开始日期（格式：YYYY-MM-DD）
- `end_date` (str, 可选): 结束日期（格式：YYYY-MM-DD）

**返回格式**:
```
应用程序使用统计（2026-04-10 到 2026-04-10）
============================================================

1. Trae CN
   使用次数：90
   总时长：1:43:14 (1.72 小时)

2. Doubao
   使用次数：53
   总时长：0:36:04 (0.60 小时)

...

============================================================
📊 总计统计
   应用数量：20
   总使用时长：3.29 小时
```

**使用示例**:
```python
# 获取今天的应用使用统计
get_application_usage.invoke({})

# 获取指定日期范围的统计
get_application_usage.invoke({
    "start_date": "2026-04-01",
    "end_date": "2026-04-10"
})

# 在Agent中使用
agent.React_Agent_Stream("我今天使用了哪些应用程序？")
```

#### 6.5 get_productivity_summary - 获取生产力摘要报告
**功能**: 获取生产力摘要报告，包括最常使用的应用、活动时间分布等

**参数**:
- `start_date` (str, 可选): 开始日期（格式：YYYY-MM-DD）
- `end_date` (str, 可选): 结束日期（格式：YYYY-MM-DD）

**返回格式**:
```
生产力摘要报告（2026-04-10 到 2026-04-10）
============================================================

🏆 最常使用的应用（Top 10）
------------------------------------------------------------
1. Trae CN
   1.72 小时 (32.3%)
2. Doubao
   0.60 小时 (11.3%)
...

⏰ 活跃时间分布
------------------------------------------------------------
02:00 - 03:00  1.50 小时
01:00 - 02:00  1.24 小时
...

============================================================
📊 总体统计
------------------------------------------------------------
总使用时长：5.30 小时
应用数量：33
平均每小时切换应用：48.9 次
```

**使用示例**:
```python
# 获取今天的生产力摘要
get_productivity_summary.invoke({})

# 获取指定日期范围的生产力摘要
get_productivity_summary.invoke({
    "start_date": "2026-04-01",
    "end_date": "2026-04-10"
})

# 在Agent中使用
agent.React_Agent_Stream("给我一个今天的工作效率报告")
agent.React_Agent_Stream("分析一下我过去一周的工作效率")
```

## 数据库位置

ManicTime数据库文件位于：
```
C:\Users\H\AppData\Local\Finkit\ManicTime\ManicTimeReports.db
```

## 注意事项

1. **隐私保护**: ManicTime记录了您的所有电脑活动，请谨慎分享这些数据
2. **数据准确性**: 数据来源于ManicTime软件，准确性取决于软件的监控
3. **性能考虑**: 查询大量数据可能需要一些时间，请耐心等待
4. **日期格式**: 所有日期参数必须使用 YYYY-MM-DD 格式

## 使用场景

- 📊 **时间管理**: 了解自己的时间分配情况
- 📈 **效率分析**: 分析工作效率和改进空间
- 🎯 **目标追踪**: 追踪特定应用或活动的使用时间
- 📅 **历史回顾**: 回顾过去的工作和学习情况
- 💡 **习惯养成**: 了解自己的使用习惯，优化时间分配

## 扩展指南

添加新工具的步骤：

1. 在 `src/core/tools/` 目录下创建新的工具文件
2. 使用 `@tool` 装饰器定义工具函数
3. 在 `__init__.py` 中导入并导出工具
4. 在 `agent.py` 中添加到工具列表

示例：
```python
# src/core/tools/new_tool.py
from langchain_core.tools import tool

@tool
def my_new_tool(param: str) -> str:
    """
    工具描述
    
    params:
        param: 参数说明
    
    return:
        返回值说明
    """
    # 实现逻辑
    return "结果"
```

```python
# src/core/tools/__init__.py
from .new_tool import my_new_tool

__all__ = [..., "my_new_tool"]
```
