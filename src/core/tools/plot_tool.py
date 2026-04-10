from langchain_core.tools import tool
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import os
from pathlib import Path
from typing import List, Dict, Optional, Literal
import json

matplotlib.use('Agg')
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

FILES_DIR = Path(__file__).parent.parent.parent.parent / "files"
FILES_DIR.mkdir(exist_ok=True)


def _parse_data(data_str: str) -> List:
    """
    解析数据字符串为列表
    
    params:
        data_str: 数据字符串，支持格式：
            - "1,2,3,4,5"
            - "[1,2,3,4,5]"
            - "1 2 3 4 5"
    
    return:
        数据列表
    """
    data_str = data_str.strip()
    
    if data_str.startswith('[') and data_str.endswith(']'):
        data_str = data_str[1:-1]
    
    if ',' in data_str:
        return [float(x.strip()) for x in data_str.split(',') if x.strip()]
    else:
        return [float(x.strip()) for x in data_str.split() if x.strip()]


@tool
def plot_line_chart(
    filename: str,
    x_data: str,
    y_data: str,
    title: str = "折线图",
    x_label: str = "X轴",
    y_label: str = "Y轴",
    line_color: str = "blue",
    line_width: int = 2,
    marker: str = "o",
    grid: bool = True
) -> str:
    """
    绘制折线图
    
    params:
        filename: 保存的文件名（不含扩展名）
        x_data: X轴数据，格式："1,2,3,4,5" 或 "[1,2,3,4,5]"
        y_data: Y轴数据，格式同上
        title: 图表标题
        x_label: X轴标签
        y_label: Y轴标签
        line_color: 线条颜色（blue/red/green/orange/purple等）
        line_width: 线条宽度
        marker: 数据点标记（o/s/^/D/v等，或none表示无标记）
        grid: 是否显示网格
    
    return:
        保存结果信息
    
    示例:
        plot_line_chart(
            filename="sales_trend",
            x_data="1,2,3,4,5,6",
            y_data="100,150,120,180,200,250",
            title="销售趋势",
            x_label="月份",
            y_label="销售额"
        )
    """
    try:
        x = _parse_data(x_data)
        y = _parse_data(y_data)
        
        if len(x) != len(y):
            return f"错误：X轴数据({len(x)}个)和Y轴数据({len(y)}个)长度不一致"
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if marker.lower() == 'none':
            ax.plot(x, y, color=line_color, linewidth=line_width)
        else:
            ax.plot(x, y, color=line_color, linewidth=line_width, marker=marker)
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        
        if grid:
            ax.grid(True, alpha=0.3)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"成功创建折线图：{filename}.png\n文件路径：{file_path}\n数据点数：{len(x)}"
    
    except Exception as e:
        return f"绘图失败：{str(e)}"


@tool
def plot_bar_chart(
    filename: str,
    categories: str,
    values: str,
    title: str = "柱状图",
    x_label: str = "类别",
    y_label: str = "数值",
    color: str = "steelblue",
    show_values: bool = True,
    horizontal: bool = False
) -> str:
    """
    绘制柱状图
    
    params:
        filename: 保存的文件名（不含扩展名）
        categories: 类别名称，格式："类别1,类别2,类别3"
        values: 数值数据，格式："10,20,30"
        title: 图表标题
        x_label: X轴标签
        y_label: Y轴标签
        color: 柱子颜色
        show_values: 是否在柱子上显示数值
        horizontal: 是否绘制水平柱状图
    
    return:
        保存结果信息
    
    示例:
        plot_bar_chart(
            filename="product_sales",
            categories="产品A,产品B,产品C,产品D",
            values="120,150,100,180",
            title="产品销售对比",
            x_label="产品",
            y_label="销售额"
        )
    """
    try:
        cats = [c.strip() for c in categories.split(',')]
        vals = _parse_data(values)
        
        if len(cats) != len(vals):
            return f"错误：类别数({len(cats)}个)和数值数({len(vals)}个)不一致"
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        x_pos = np.arange(len(cats))
        
        if horizontal:
            bars = ax.barh(x_pos, vals, color=color)
            ax.set_yticks(x_pos)
            ax.set_yticklabels(cats)
            ax.set_xlabel(y_label, fontsize=12)
            ax.set_ylabel(x_label, fontsize=12)
            
            if show_values:
                for i, (bar, val) in enumerate(zip(bars, vals)):
                    ax.text(val, i, f' {val}', va='center', fontsize=10)
        else:
            bars = ax.bar(x_pos, vals, color=color)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(cats)
            ax.set_xlabel(x_label, fontsize=12)
            ax.set_ylabel(y_label, fontsize=12)
            
            if show_values:
                for bar, val in zip(bars, vals):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{val}', ha='center', va='bottom', fontsize=10)
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"成功创建柱状图：{filename}.png\n文件路径：{file_path}\n类别数：{len(cats)}"
    
    except Exception as e:
        return f"绘图失败：{str(e)}"


@tool
def plot_pie_chart(
    filename: str,
    labels: str,
    values: str,
    title: str = "饼图",
    colors: Optional[str] = None,
    explode: Optional[str] = None,
    show_percentage: bool = True,
    start_angle: int = 90
) -> str:
    """
    绘制饼图
    
    params:
        filename: 保存的文件名（不含扩展名）
        labels: 标签名称，格式："标签1,标签2,标签3"
        values: 数值数据，格式："30,40,30"
        title: 图表标题
        colors: 自定义颜色，格式："red,blue,green"（可选）
        explode: 突出显示，格式："0.1,0,0"（可选）
        show_percentage: 是否显示百分比
        start_angle: 起始角度
    
    return:
        保存结果信息
    
    示例:
        plot_pie_chart(
            filename="market_share",
            labels="产品A,产品B,产品C",
            values="40,35,25",
            title="市场份额",
            colors="red,blue,green"
        )
    """
    try:
        label_list = [l.strip() for l in labels.split(',')]
        value_list = _parse_data(values)
        
        if len(label_list) != len(value_list):
            return f"错误：标签数({len(label_list)}个)和数值数({len(value_list)}个)不一致"
        
        color_list = None
        if colors:
            color_list = [c.strip() for c in colors.split(',')]
        
        explode_list = None
        if explode:
            explode_list = [float(e.strip()) for e in explode.split(',')]
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        wedges, texts, autotexts = ax.pie(
            value_list,
            labels=label_list,
            colors=color_list,
            explode=explode_list,
            autopct='%1.1f%%' if show_percentage else '',
            startangle=start_angle,
            textprops={'fontsize': 11}
        )
        
        if show_percentage:
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        
        plt.tight_layout()
        
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"成功创建饼图：{filename}.png\n文件路径：{file_path}\n类别数：{len(label_list)}"
    
    except Exception as e:
        return f"绘图失败：{str(e)}"


@tool
def plot_scatter_chart(
    filename: str,
    x_data: str,
    y_data: str,
    title: str = "散点图",
    x_label: str = "X轴",
    y_label: str = "Y轴",
    color: str = "blue",
    size: int = 50,
    show_regression: bool = False
) -> str:
    """
    绘制散点图
    
    params:
        filename: 保存的文件名（不含扩展名）
        x_data: X轴数据，格式："1,2,3,4,5"
        y_data: Y轴数据，格式同上
        title: 图表标题
        x_label: X轴标签
        y_label: Y轴标签
        color: 点的颜色
        size: 点的大小
        show_regression: 是否显示回归线
    
    return:
        保存结果信息
    
    示例:
        plot_scatter_chart(
            filename="correlation",
            x_data="1,2,3,4,5,6,7,8,9,10",
            y_data="2,4,5,4,5,7,8,9,10,11",
            title="相关性分析",
            x_label="变量X",
            y_label="变量Y",
            show_regression=True
        )
    """
    try:
        x = _parse_data(x_data)
        y = _parse_data(y_data)
        
        if len(x) != len(y):
            return f"错误：X轴数据({len(x)}个)和Y轴数据({len(y)}个)长度不一致"
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.scatter(x, y, c=color, s=size, alpha=0.6, edgecolors='black', linewidth=0.5)
        
        if show_regression:
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            x_line = np.linspace(min(x), max(x), 100)
            ax.plot(x_line, p(x_line), "r--", alpha=0.8, linewidth=2, label=f'趋势线')
            ax.legend()
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        ax.grid(True, alpha=0.3)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"成功创建散点图：{filename}.png\n文件路径：{file_path}\n数据点数：{len(x)}"
    
    except Exception as e:
        return f"绘图失败：{str(e)}"


@tool
def plot_histogram(
    filename: str,
    data: str,
    title: str = "直方图",
    x_label: str = "数值",
    y_label: str = "频数",
    bins: int = 10,
    color: str = "steelblue",
    show_edge: bool = True,
    show_kde: bool = False
) -> str:
    """
    绘制直方图
    
    params:
        filename: 保存的文件名（不含扩展名）
        data: 数据，格式："1,2,3,4,5,6,7,8,9,10"
        title: 图表标题
        x_label: X轴标签
        y_label: Y轴标签
        bins: 柱子数量
        color: 柱子颜色
        show_edge: 是否显示边框
        show_kde: 是否显示核密度估计曲线
    
    return:
        保存结果信息
    
    示例:
        plot_histogram(
            filename="age_distribution",
            data="25,30,35,40,45,50,55,60,65,70,75,80",
            title="年龄分布",
            x_label="年龄",
            y_label="人数",
            bins=5
        )
    """
    try:
        data_list = _parse_data(data)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        n, bins_edges, patches = ax.hist(
            data_list,
            bins=bins,
            color=color,
            edgecolor='black' if show_edge else None,
            alpha=0.7
        )
        
        if show_kde:
            from scipy import stats
            kde = stats.gaussian_kde(data_list)
            x_range = np.linspace(min(data_list), max(data_list), 100)
            ax2 = ax.twinx()
            ax2.plot(x_range, kde(x_range), 'r-', linewidth=2, label='核密度估计')
            ax2.set_ylabel('密度', fontsize=12)
            ax2.legend(loc='upper right')
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"成功创建直方图：{filename}.png\n文件路径：{file_path}\n数据点数：{len(data_list)}\n分组数：{bins}"
    
    except Exception as e:
        return f"绘图失败：{str(e)}"


@tool
def plot_multi_line_chart(
    filename: str,
    x_data: str,
    y_data_list: str,
    labels: str,
    title: str = "多线折线图",
    x_label: str = "X轴",
    y_label: str = "Y轴",
    colors: Optional[str] = None
) -> str:
    """
    绘制多条折线图
    
    params:
        filename: 保存的文件名（不含扩展名）
        x_data: X轴数据，格式："1,2,3,4,5"
        y_data_list: Y轴数据列表，格式："10,20,30|15,25,35|20,30,40"（用|分隔多条线）
        labels: 各条线的标签，格式："系列1,系列2,系列3"
        title: 图表标题
        x_label: X轴标签
        y_label: Y轴标签
        colors: 自定义颜色，格式："red,blue,green"（可选）
    
    return:
        保存结果信息
    
    示例:
        plot_multi_line_chart(
            filename="sales_comparison",
            x_data="1,2,3,4,5,6",
            y_data_list="100,150,120,180,200,250|80,120,100,150,180,220",
            labels="产品A,产品B",
            title="销售对比",
            x_label="月份",
            y_label="销售额"
        )
    """
    try:
        x = _parse_data(x_data)
        
        y_lists = []
        for y_str in y_data_list.split('|'):
            y_lists.append(_parse_data(y_str.strip()))
        
        label_list = [l.strip() for l in labels.split(',')]
        
        if len(y_lists) != len(label_list):
            return f"错误：数据系列数({len(y_lists)}个)和标签数({len(label_list)}个)不一致"
        
        for i, y in enumerate(y_lists):
            if len(x) != len(y):
                return f"错误：第{i+1}条线的X轴数据({len(x)}个)和Y轴数据({len(y)}个)长度不一致"
        
        color_list = None
        if colors:
            color_list = [c.strip() for c in colors.split(',')]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        for i, y in enumerate(y_lists):
            color = color_list[i] if color_list and i < len(color_list) else None
            ax.plot(x, y, marker='o', label=label_list[i], color=color, linewidth=2)
        
        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        return f"成功创建多线折线图：{filename}.png\n文件路径：{file_path}\n线条数：{len(y_lists)}"
    
    except Exception as e:
        return f"绘图失败：{str(e)}"
