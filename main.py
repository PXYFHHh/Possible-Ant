from src.core.agent import Model, Agent
from src.core.tools import (
    get_current_time,
    get_search_results,
    create_file,
    read_file,
    list_files,
    delete_file,
    delete_multiple_files,
    calculate,
    calculate_percentage,
    calculate_average,
    plot_line_chart,
    plot_bar_chart,
    plot_pie_chart,
    plot_scatter_chart,
    plot_histogram,
    plot_multi_line_chart,
    get_manictime_schema,
    get_today_activities,
    get_activities_by_date_range,
    get_application_usage,
    get_productivity_summary,
    get_screen_time_today,
    get_screen_time_by_date,
    get_productivity_with_screen_time,
    rag_ingest_document,
    rag_query,
    rag_list_documents,
    rag_delete_document,
)

if __name__ == "__main__":
    model = Model()
    agent = Agent(model, [
        get_current_time,
        get_search_results,
        create_file,
        read_file,
        list_files,
        delete_file,
        delete_multiple_files,
        calculate,
        calculate_percentage,
        calculate_average,
        plot_line_chart,
        plot_bar_chart,
        plot_pie_chart,
        plot_scatter_chart,
        plot_histogram,
        plot_multi_line_chart,
        get_manictime_schema,
        get_today_activities,
        get_activities_by_date_range,
        get_application_usage,
        get_productivity_summary,
        get_screen_time_today,
        get_screen_time_by_date,
        get_productivity_with_screen_time,
        rag_ingest_document,
        rag_query,
        rag_list_documents,
        rag_delete_document,
    ])
    
    print("=" * 70)
    print("🎉 智能助手已启动！")
    print("=" * 70)
    print("\n可用功能：")
    print("  ⏰  时间查询")
    print("  🔍  网络搜索")
    print("  📁  文件操作")
    print("  🧮  数学计算")
    print("  📊  图表绘制（折线图、柱状图、饼图、散点图、直方图）")
    print("  📈  ManicTime追踪（活动记录、应用使用统计、生产力分析、屏幕活跃时间）\n")
    print("  📚  RAG知识库（文档入库、混合检索、重排召回）\n")
    print("  输入 'exit' 或 'quit' 退出程序")
    print("=" * 70)
    
    while True:
        try:
            user_input = input("\n请输入您的问题：").strip()
            
            if user_input.lower() in ['exit', 'quit', '退出']:
                print("\n👋 感谢使用，再见！")
                break
            
            if not user_input:
                continue
            
            response = agent.React_Agent_Stream(user_input)
            
        except KeyboardInterrupt:
            print("\n\n👋 感谢使用，再见！")
            break
        except Exception as e:
            print(f"\n❌ 发生错误：{str(e)}")
