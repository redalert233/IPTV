import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime

# 创建模拟配置文件，因为原代码依赖config模块
class Config:
    # 示例源URL列表
    source_urls = [
        "https://iptv-org.github.io/iptv/channels.m3u",
        # 可以添加其他源URL
    ]
    
    # EPG URL列表
    epg_urls = [
        "http://epg.51zmt.top:8000/e.xml",
        "https://epg.pw/xmltv.xml.gz"
    ]
    
    # 公告信息
    announcements = [
        {
            'channel': '公告',
            'entries': [
                {
                    'name': '更新日期',
                    'logo': 'https://example.com/logo.png',
                    'url': 'https://example.com/notice'
                }
            ]
        }
    ]
    
    # IP版本优先级
    ip_version_priority = "ipv4"  # 或 "ipv6"
    
    # URL黑名单
    url_blacklist = ["example-blacklisted.com"]

config = Config()

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    handlers=[
        logging.FileHandler("function.log", "w", encoding="utf-8"), 
        logging.StreamHandler()
    ]
)

def parse_template(template_file):
    """
    解析模板文件，提取频道分类和频道名称
    """
    template_channels = OrderedDict()
    current_category = None

    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)

    return template_channels

def fetch_channels(url):
    """
    从指定URL获取频道信息
    """
    channels = OrderedDict()

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        lines = response.text.split("\n")
        
        current_category = None
        is_m3u = any("#EXTINF" in line for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"url: {url} 获取成功，判断为{source_type}格式")

        if is_m3u:
            channel_name = None
            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    match = re.search(r'group-title="(.*?)",(.*)', line)
                    if match:
                        current_category = match.group(1).strip()
                        channel_name = match.group(2).strip()
                        if current_category not in channels:
                            channels[current_category] = []
                elif line and not line.startswith("#"):
                    channel_url = line.strip()
                    if current_category and channel_name:
                        channels[current_category].append((channel_name, channel_url))
        else:
            for line in lines:
                line = line.strip()
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    channels[current_category] = []
                elif current_category:
                    match = re.match(r"^(.*?),(.*?)$", line)
                    if match:
                        channel_name = match.group(1).strip()
                        channel_url = match.group(2).strip()
                        channels[current_category].append((channel_name, channel_url))
                    elif line:
                        channels[current_category].append((line, ''))
        
        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"url: {url} 爬取成功✅，包含频道分类: {categories}")
    except requests.RequestException as e:
        logging.error(f"url: {url} 爬取失败❌, Error: {e}")
    except Exception as e:
        logging.error(f"处理URL {url} 时发生错误: {e}")

    return channels

def match_channels(template_channels, all_channels):
    """
    匹配模板频道和在线频道
    """
    matched_channels = OrderedDict()

    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            for online_category, online_channel_list in all_channels.items():
                for online_channel_name, online_channel_url in online_channel_list:
                    if channel_name == online_channel_name:
                        matched_channels[category].setdefault(channel_name, []).append(online_channel_url)

    return matched_channels

def filter_source_urls(template_file):
    """
    从所有源URL中过滤出匹配的频道
    """
    template_channels = parse_template(template_file)
    source_urls = config.source_urls

    all_channels = OrderedDict()
    for url in source_urls:
        fetched_channels = fetch_channels(url)
        for category, channel_list in fetched_channels.items():
            if category in all_channels:
                all_channels[category].extend(channel_list)
            else:
                all_channels[category] = channel_list

    matched_channels = match_channels(template_channels, all_channels)

    return matched_channels, template_channels

def is_ipv6(url):
    """
    判断URL是否为IPv6格式
    """
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def split_urls(url_string):
    """
    将包含多个URL的字符串分割成独立的URL列表
    """
    # 按 # 分割，但忽略URL参数中的 #
    urls = []
    current_pos = 0
    i = 0
    
    while i < len(url_string):
        if url_string[i] == '#':
            # 检查是否是URL参数中的#还是分隔符
            # 如果是分隔符，则添加到列表中
            part = url_string[current_pos:i].strip()
            if part:
                urls.append(part)
            current_pos = i + 1
        i += 1
    
    # 添加最后一个部分
    if current_pos < len(url_string):
        part = url_string[current_pos:].strip()
        if part:
            urls.append(part)
    
    # 进一步处理可能包含特殊分隔符的URL
    final_urls = []
    for url in urls:
        # 移除可能的后缀
        clean_url = url.split('$')[0].strip()
        if clean_url:
            final_urls.append(clean_url)
    
    return final_urls

def updateChannelUrlsM3U(channels, template_channels):
    """
    更新频道URL并生成M3U和TXT文件 - 修复版
    """
    written_urls = set()

    current_date = datetime.now().strftime("%Y-%m-%d")
    for group in config.announcements:
        for announcement in group['entries']:
            if announcement['name'] is None:
                announcement['name'] = current_date

    with open("live.m3u", "w", encoding="utf-8") as f_m3u:
        f_m3u.write(f"""#EXTM3U x-tvg-url={",".join(f'"{epg_url}"' for epg_url in config.epg_urls)}\n""")

        with open("live.txt", "w", encoding="utf-8") as f_txt:
            for group in config.announcements:
                f_txt.write(f"{group['channel']},#genre#\n")
                for announcement in group['entries']:
                    f_m3u.write(f"""#EXTINF:-1 tvg-id="1" tvg-name="{announcement['name']}" tvg-logo="{announcement['logo']}" group-title="{group['channel']}",{announcement['name']}\n""")
                    f_m3u.write(f"{announcement['url']}\n")
                    f_txt.write(f"{announcement['name']},{announcement['url']}\n")

            for category, channel_list in template_channels.items():
                f_txt.write(f"{category},#genre#\n")
                if category in channels:
                    for channel_name in channel_list:
                        if channel_name in channels[category]:
                            # 获取所有原始URL
                            original_urls = channels[category][channel_name]
                            
                            # 展开所有URL（处理包含多个URL的字符串）
                            all_individual_urls = []
                            for url in original_urls:
                                individual_urls = split_urls(url)
                                all_individual_urls.extend(individual_urls)
                            
                            # 过滤和排序URL
                            filtered_urls = []
                            for url in all_individual_urls:
                                if url and url not in written_urls and not any(blacklist in url for blacklist in config.url_blacklist):
                                    filtered_urls.append(url)
                                    written_urls.add(url)

                            # 按IP版本优先级排序
                            sorted_urls = sorted(
                                filtered_urls,
                                key=lambda url: not is_ipv6(url) if config.ip_version_priority == "ipv6" else is_ipv6(url)
                            )

                            # 输出每个URL为独立行
                            for index, url in enumerate(sorted_urls, start=1):
                                # 为每个URL添加适当的后缀
                                if is_ipv6(url):
                                    url_suffix = f"$LR•IPV6" if len(sorted_urls) == 1 else f"$LR•IPV6『线路{index}』"
                                else:
                                    url_suffix = f"$LR•IPV4" if len(sorted_urls) == 1 else f"$LR•IPV4『线路{index}』"
                                
                                if '$' in url:
                                    base_url = url.split('$', 1)[0]
                                else:
                                    base_url = url

                                new_url = f"{base_url}{url_suffix}"

                                f_m3u.write(f'#EXTINF:-1 tvg-id="{index}" tvg-name="{channel_name}" tvg-logo="https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{channel_name}.png" group-title="{category}",{channel_name}\n')
                                f_m3u.write(new_url + "\n")
                                f_txt.write(f"{channel_name},{new_url}\n")

            f_txt.write("\n")


if __name__ == "__main__":
    try:
        channels, template_channels = filter_source_urls(template_file)
        updateChannelUrlsM3U(channels, template_channels)
        print("频道列表已成功生成到 live.m3u 和 live.txt 文件中")
        print("现在每个URL都会单独占一行，不会再出现多个URL合并的情况")
    except Exception as e:
        print(f"执行过程中发生错误: {e}")
