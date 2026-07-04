#!/bin/bash
set -euo pipefail

# 动漫日报自动生成发送脚本
# 流程:
# 1. 收集数据生成 JSON
# 2. 生成 HTML
# 3. 发送 HTML 邮件到配置邮箱
# 4. 发送 TXT 分段消息到 Telegram 频道

cd /root/anime_daily_report

today=$(date +%Y-%m-%d)
mkdir -p files/"$today"

# Step 1: 生成数据 JSON
echo "📊 生成动漫日报数据..."
python3 scripts/anime_data_collector.py "$today"

# Step 2: 生成 HTML 报告
echo "🎨 生成 HTML 报告..."
if [[ ! -f "templates/anime_daily.html.j2" ]]; then
    echo "❌ 缺少模板文件: templates/anime_daily.html.j2"
    exit 1
fi
python3 generate_anime_report.py "$today"

html_file="files/$today/动漫日报_$today.html"

if [[ ! -f "$html_file" ]]; then
    echo "❌ HTML 文件生成失败: $html_file"
    exit 1
fi

echo "✅ HTML 报告已生成: $html_file"

# Step 3: 发送邮件
echo "📧 发送邮件..."
python3 send_report_email.py "$html_file" "日本动漫番剧日报 $today" --html

# Step 4: 发送 Telegram 分段消息
echo "📺 发送 Telegram..."
python3 send_tg_report.py "$html_file"

echo "🎉 动漫日报发送完成！"
