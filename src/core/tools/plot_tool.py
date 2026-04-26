from langchain_core.tools import tool
from pathlib import Path
from typing import List, Optional

FILES_DIR = Path(__file__).parent.parent.parent.parent / "files"
FILES_DIR.mkdir(exist_ok=True)

_mpl_initialized = False


def _init_mpl():
    """懒初始化 matplotlib + numpy，首次绘图时才 import，避免启动时加载重库"""
    global _mpl_initialized, plt, np
    if _mpl_initialized:
        return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    _mpl_initialized = True


def _save_plot(filename, draw_fn, *, title="", x_label="X轴", y_label="Y轴", grid=True, grid_axis='both', figsize=(10, 6), success_msg=None):
    """
    通用绘图包装器：初始化 → 创建画布 → 执行绘图回调 → 保存/关闭。
    """
    try:
        _init_mpl()
        fig, ax = plt.subplots(figsize=figsize)
        draw_fn(ax)
        if title:
            ax.set_title(title, fontsize=16, fontweight='bold')
        if x_label:
            ax.set_xlabel(x_label, fontsize=12)
        if y_label:
            ax.set_ylabel(y_label, fontsize=12)
        if grid:
            ax.grid(True, alpha=0.3, axis=grid_axis)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        file_path = FILES_DIR / f"{filename}.png"
        plt.savefig(file_path, dpi=300, bbox_inches='tight')
        plt.close()
        return success_msg or f"成功创建图表：{filename}.png\n文件路径：{file_path}"
    except Exception as e:
        return f"绘图失败：{str(e)}"


def _parse_data(data_str: str) -> List:
    """
    解析数据字符串为列表
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
    """
    try:
        x = _parse_data(x_data)
        y = _parse_data(y_data)
    except Exception as e:
        return f"数据解析失败：{str(e)}"
    if len(x) != len(y):
        return f"错误：X轴数据({len(x)}个)和Y轴数据({len(y)}个)长度不一致"

    def draw(ax):
        if marker.lower() == 'none':
            ax.plot(x, y, color=line_color, linewidth=line_width)
        else:
            ax.plot(x, y, color=line_color, linewidth=line_width, marker=marker)

    return _save_plot(filename, draw, title=title, x_label=x_label, y_label=y_label, grid=grid,
                      success_msg=f"成功创建折线图：{filename}.png\n数据点数：{len(x)}")


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
    """
    try:
        cats = [c.strip() for c in categories.split(',')]
        vals = _parse_data(values)
    except Exception as e:
        return f"数据解析失败：{str(e)}"
    if len(cats) != len(vals):
        return f"错误：类别数({len(cats)}个)和数值数({len(vals)}个)不一致"

    def draw(ax):
        x_pos = np.arange(len(cats))
        if horizontal:
            bars = ax.barh(x_pos, vals, color=color)
            ax.set_yticks(x_pos)
            ax.set_yticklabels(cats)
            if show_values:
                for i, (bar, val) in enumerate(zip(bars, vals)):
                    ax.text(val, i, f' {val}', va='center', fontsize=10)
        else:
            bars = ax.bar(x_pos, vals, color=color)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(cats)
            if show_values:
                for bar, val in zip(bars, vals):
                    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                           f'{val}', ha='center', va='bottom', fontsize=10)

    return _save_plot(filename, draw, title=title,
                      x_label=(y_label if horizontal else x_label),
                      y_label=(x_label if horizontal else y_label),
                      success_msg=f"成功创建柱状图：{filename}.png\n类别数：{len(cats)}")


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
    """
    try:
        label_list = [l.strip() for l in labels.split(',')]
        value_list = _parse_data(values)
    except Exception as e:
        return f"数据解析失败：{str(e)}"
    if len(label_list) != len(value_list):
        return f"错误：标签数({len(label_list)}个)和数值数({len(value_list)}个)不一致"
    color_list = [c.strip() for c in colors.split(',')] if colors else None
    explode_list = [float(e.strip()) for e in explode.split(',')] if explode else None

    def draw(ax):
        wedges, texts, autotexts = ax.pie(
            value_list, labels=label_list, colors=color_list,
            explode=explode_list, autopct='%1.1f%%' if show_percentage else '',
            startangle=start_angle, textprops={'fontsize': 11})
        if show_percentage:
            for at in autotexts:
                at.set_color('white')
                at.set_fontweight('bold')

    return _save_plot(filename, draw, title=title, x_label="", y_label="", grid=False, figsize=(10, 8),
                      success_msg=f"成功创建饼图：{filename}.png\n类别数：{len(label_list)}")


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
    """
    try:
        x = _parse_data(x_data)
        y = _parse_data(y_data)
    except Exception as e:
        return f"数据解析失败：{str(e)}"
    if len(x) != len(y):
        return f"错误：X轴数据({len(x)}个)和Y轴数据({len(y)}个)长度不一致"

    def draw(ax):
        ax.scatter(x, y, c=color, s=size, alpha=0.6, edgecolors='black', linewidth=0.5)
        if show_regression:
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            ax.plot(np.linspace(min(x), max(x), 100), p(np.linspace(min(x), max(x), 100)),
                   "r--", alpha=0.8, linewidth=2, label='趋势线')
            ax.legend()

    return _save_plot(filename, draw, title=title, x_label=x_label, y_label=y_label,
                      success_msg=f"成功创建散点图：{filename}.png\n数据点数：{len(x)}")


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
    """
    try:
        data_list = _parse_data(data)
    except Exception as e:
        return f"数据解析失败：{str(e)}"

    def draw(ax):
        ax.hist(data_list, bins=bins, color=color,
                edgecolor='black' if show_edge else None, alpha=0.7)
        if show_kde:
            from scipy import stats
            kde = stats.gaussian_kde(data_list)
            x_range = np.linspace(min(data_list), max(data_list), 100)
            ax2 = ax.twinx()
            ax2.plot(x_range, kde(x_range), 'r-', linewidth=2, label='核密度估计')
            ax2.set_ylabel('密度', fontsize=12)
            ax2.legend(loc='upper right')

    return _save_plot(filename, draw, title=title, x_label=x_label, y_label=y_label, grid_axis='y',
                      success_msg=f"成功创建直方图：{filename}.png\n数据点数：{len(data_list)}\n分组数：{bins}")


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
    """
    try:
        x = _parse_data(x_data)
        y_lists = [_parse_data(ys.strip()) for ys in y_data_list.split('|')]
        label_list = [l.strip() for l in labels.split(',')]
    except Exception as e:
        return f"数据解析失败：{str(e)}"
    if len(y_lists) != len(label_list):
        return f"错误：数据系列数({len(y_lists)}个)和标签数({len(label_list)}个)不一致"
    for i, y in enumerate(y_lists):
        if len(x) != len(y):
            return f"错误：第{i+1}条线的X轴数据({len(x)}个)和Y轴数据({len(y)}个)长度不一致"
    color_list = [c.strip() for c in colors.split(',')] if colors else None

    def draw(ax):
        for i, y in enumerate(y_lists):
            c = color_list[i] if color_list and i < len(color_list) else None
            ax.plot(x, y, marker='o', label=label_list[i], color=c, linewidth=2)
        ax.legend()

    return _save_plot(filename, draw, title=title, x_label=x_label, y_label=y_label,
                      success_msg=f"成功创建多线折线图：{filename}.png\n线条数：{len(y_lists)}")
