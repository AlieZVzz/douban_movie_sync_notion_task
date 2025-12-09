import time
# import yaml  <-- 已删除
import os
import re
import feedparser
import requests
from bs4 import BeautifulSoup
import NotionAPI
from PIL import Image
import logging
import json
import sys  # 引入 sys 用于退出程序

# 设置日志格式
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)

# 获取日志器
logger = logging.getLogger("MovieTracker")

# 全局配置字典 (将在 main 中初始化)
config = {}

def request_movie_opt_name(moviename):
    logger.debug(f"Requesting optimized name for movie: {moviename}")
    url = "https://api.deepseek.com/chat/completions"

    payload = json.dumps({
        "messages": [
            {
                "role": "user",
                "content": "请将以下的电影名称转换为一个tmdb数据库可以搜索到标准名称" + "\n" + moviename + "\n" +
                           "注意！！！！请直接告诉我名称，，不需要返回其他内容！！，不需要返回其他内容\n" +
                           "例如： 地球脉动 第三季 Planet Earth Season 3(2023)，可以搜索到的名称是 Planet Earth III" +
                           "直接返回 Planet Earth III 即可。不需要返回其他内容！",
            }
        ],
        "model": "deepseek-chat",
        "frequency_penalty": 0,
        "max_tokens": 2048,
        "presence_penalty": 0,
        "response_format": {
            "type": "text"
        },
        "stop": None,
        "stream": False,
        "stream_options": None,
        "temperature": 1,
        "top_p": 1,
        "tools": None,
        "tool_choice": "none",
        "logprobs": False,
        "top_logprobs": None
    })
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + config["deepseek_api"]
    }

    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            optimized_name = response.json().get("choices")[0].get("message").get("content")
            logger.info(f"Successfully optimized movie name: {moviename} -> {optimized_name}")
            logger.debug(f"Full API response: {response.text}")
            return optimized_name
        else:
            logger.error(f"Failed to optimize movie name. Status code: {response.status_code}, Response: {response.text}")
            return moviename
    except Exception as e:
        logger.error(f"Exception occurred while requesting optimized movie name: {str(e)}")
        return moviename


def search_movie(api_key, query):
    """搜索电影并返回第一个搜索结果的电影 ID"""
    logger.info(f"Searching for movie: {query}")
    url = f'https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query}'
    
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('results'):
            movie_id = data['results'][0]['id']
            logger.info(f"Found movie ID {movie_id} for query: {query}")
            return movie_id
        else:
            logger.warning(f"No results found for '{query}', attempting to optimize name...")
            new_name = request_movie_opt_name(query)
            logger.info(f"Retrying search with optimized name: {new_name}")
            url = f'https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={new_name}'
            response = requests.get(url)
            data = response.json()
            if data.get('results'):
                movie_id = data['results'][0]['id']
                logger.info(f"Found movie ID {movie_id} for optimized query: {new_name}")
                return movie_id
            else:
                logger.warning(f"Search failed for both original and optimized names. Original: {query}, Optimized: {new_name}")
                return None
    except Exception as e:
        logger.error(f"Exception occurred while searching for movie: {str(e)}")
        return None


def get_movie_poster(api_key, movie_id):
    """
    根据电影 ID 获取电影海报 URL
    """
    logger.debug(f"Getting poster for movie ID: {movie_id}")
    url = f'https://api.themoviedb.org/3/movie/{movie_id}?api_key={api_key}'
    
    try:
        response = requests.get(url)
        data = response.json()
        if 'poster_path' in data and data['poster_path']:
            poster_path = data['poster_path']
            poster_url = f'https://image.tmdb.org/t/p/w500{poster_path}'
            logger.info(f"Successfully retrieved poster URL for movie ID {movie_id}")
            return poster_url
        else:
            logger.warning(f"No poster available for movie ID: {movie_id}")
            return ""
    except Exception as e:
        logger.error(f"Exception occurred while getting movie poster: {str(e)}")
        return ""


def compress_image(input_path, max_size_kb=5000):
    """
    压缩图片
    """
    logger.debug(f"Compressing image: {input_path}")
    try:
        with Image.open(input_path) as img:
            width, height = img.size
            file_size = os.path.getsize(input_path) / 1024  # 转换为KB
            logger.debug(f"Original image size: {file_size:.2f} KB")
            
            if file_size > max_size_kb:
                compression_ratio = (max_size_kb / file_size) ** 0.5
                new_width = int(width * compression_ratio)
                new_height = int(height * compression_ratio)
                compressed_img = img.resize((new_width, new_height))
                compressed_img = compressed_img.convert("RGB")
                compressed_img.save(input_path)
                new_file_size = os.path.getsize(input_path) / 1024
                logger.info(f"Compressed image from {file_size:.2f} KB to {new_file_size:.2f} KB")
            else:
                img.save(input_path)
                logger.debug("Image size is within limit, no compression needed")
    except Exception as e:
        logger.error(f"Exception occurred while compressing image: {str(e)}")


def download_img(img_url):
    """
    download douban cover to local
    """
    logger.info(f"Downloading image from: {img_url}")
    try:
        # 确保目录存在
        if not os.path.exists("posters"):
            os.makedirs("posters")

        r = requests.get(img_url, headers={'Referer': 'https://movie.douban.com'}, stream=True)
        logger.debug(f"Image download status code: {r.status_code}")
        img_name = "posters/" + img_url.split("/")[-1]
        
        if r.status_code == 200:
            with open(img_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=2048):
                    if chunk:
                        f.write(chunk)
                        f.flush()
            logger.info(f"Successfully downloaded image to: {img_name}")
            return img_name
        else:
            logger.error(f"Failed to download image. Status code: {r.status_code}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred while downloading image: {str(e)}")
        return None


def upload_img(path):
    """
    upload img to smms
    """
    logger.info(f"Uploading image: {path}")
    try:
        compress_image(path)
        headers = {'Authorization': config["smms_token"]}
        with open(path, 'rb') as f:
            files = {'smfile': f}
            url = 'https://sm.ms/api/v2/upload'
            res = requests.post(url, files=files, headers=headers)
            res = res.json()

        if "data" in res.keys():
            uploaded_url = res['data']['url']
            logger.info(f"Successfully uploaded image. URL: {uploaded_url}")
            return uploaded_url
        else:
            logger.error(f"Failed to upload image. Response: {res}")
            return None
    except Exception as e:
        logger.error(f"Exception occurred while uploading image: {str(e)}")
        return None


def film_info1(item):
    """名称title 封面链接cover_url 观影时间watch_time 电影链接movive_url 评分score 评论 comment"""
    logger.debug("Extracting film info from RSS item")
    try:
        pattern1 = re.compile(r'(?<=src=").+(?=")', re.I)  # 匹配海报链接
        title = item["title"].split("看过")[1]
        cover_url = re.findall(pattern1, item["summary"])[0]
        cover_url = cover_url.replace("s_ratio_poster", "r")
        logger.debug(f"Extracted cover URL: {cover_url}")

        pub_time = item["published"]
        pattern2 = re.compile(r'(?<=. ).+\d{4}', re.S)  # 匹配时间
        month_standard = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                          'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
        time_match = re.findall(pattern2, pub_time)[0]
        time_parts = time_match.split(" ")
        day = time_parts[0]
        month = month_standard[time_parts[1]]
        year = time_parts[2]
        watch_time = str(year) + "-" + str(month) + "-" + str(day)
        logger.debug(f"Extracted watch time: {watch_time}")

        movie_url = item["link"]
        logger.debug(f"Extracted movie URL: {movie_url}")

        # 处理comment
        pattern = re.compile(r'(?<=<p>).+(?=</p>)', re.S)  # 匹配评论·
        allcomment = re.findall(pattern, item["summary"])[0]  # 需要进一步处理

        # 评分处理
        scoredict = {'很差': '⭐', '较差': '⭐⭐', '还行': '⭐⭐⭐', '推荐': '⭐⭐⭐⭐', '力荐': '⭐⭐⭐⭐⭐', }
        score_text = allcomment[-2:]
        if score_text in scoredict:
            score = scoredict[score_text]
        else:
            score = "⭐⭐⭐"

        comment = ''
        logger.debug("Successfully extracted film info")
        return cover_url, watch_time, movie_url, score, comment
    except Exception as e:
        logger.error(f"Error extracting film info from RSS item: {str(e)}")
        raise


def film_info2(movie_url, headers):
    # 检测网址是否是https，不是的话更改格式为https
    logger.info(f"Fetching detailed film info from: {movie_url}")
    try:
        if movie_url[:5] != 'https':
            url = movie_url[:4] + 's' + movie_url[4:]
        else:
            url = movie_url
            
        res = requests.get(url, headers=headers)
        bstitle = BeautifulSoup(res.text, 'html.parser')

        moive_content = bstitle.find_all('div', id='content')[0]

        # 电影名称与年份
        title_element = moive_content.find('h1')
        title_spans = title_element.find_all('span')
        title = title_spans[0].text + title_spans[1].text

        # 基本信息
        base_information = moive_content.find('div', class_='subject clearfix')
        info = base_information.find('div', id='info').text.split('\n')
        info = ','.join(info)

        pattern_type = re.compile(r'(?<=类型: )[\u4e00-\u9fa5 /]+', re.S)
        movie_type = re.findall(pattern_type, info)[0].replace(" ", "").split("/")
        pattern_director = re.compile(r'(?<=导演: )[\u4e00-\u9fa5 /]+', re.I)

        if len(re.findall(pattern_director, info)) > 0:
            director = re.findall(pattern_director, info)[0].replace(" ", "").split("/")
        else:
            director = ""

        logger.info(f"Successfully extracted film details - Title: {title}, Type: {str(movie_type)}, Director: {str(director)}")
        return title, movie_type, director
    except Exception as e:
        logger.error(f"Error fetching detailed film info from {movie_url}: {str(e)}")
        raise


def remove_year(text):
    # 正则表达式匹配括号及其中的数字
    logger.debug(f"Removing year from text: {text}")
    new_text = re.sub(r'\(\d+\)', '', text)
    cleaned_text = new_text.strip() 
    logger.debug(f"Text after removing year: {cleaned_text}")
    return cleaned_text


if __name__ == '__main__':
    try:
        logger.info("Loading configuration from Environment Variables...")
        
        # 1. 环境变量读取与映射
        # 格式: config["代码中用的名字"] = os.getenv("GitHub Secret 名字")
        config = {
            "rss_address": os.getenv("RSS_ADDRESS"),
            "databaseid": os.getenv("NOTION_DATABASE_ID"),
            "deepseek_api": os.getenv("DEEPSEEK_API"),
            "tmdb_api_key": os.getenv("TMDB_API_KEY"),
            "smms_token": os.getenv("SMMS_TOKEN"),
            "douban_cookie": os.getenv("DOUBAN_COOKIE") # 建议将 Cookie 也放入环境变量
        }

        # 2. 检查配置是否缺失 (重要！防止运行一半报错)
        missing_vars = [key for key, value in config.items() if value is None]
        if missing_vars:
            logger.critical(f"Missing environment variables: {', '.join(missing_vars)}")
            sys.exit(1) # 退出程序

        logger.info("Configuration loaded successfully.")

        # 使用环境变量中的 Cookie，如果没设置则使用默认（但强烈建议设置）
        cookie_val = config["douban_cookie"] if config["douban_cookie"] else 'll="108288"; bid=LxuBFcq903Y; ...' # 这里填你原本的备用

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Cookie': cookie_val, 
            'Content-type': 'text/html; charset=utf-8',
            'Upgrade-Insecure-Requests': '1',
        }

        # notion相关配置
        logger.info("Parsing RSS feed")
        rss_movietracker = feedparser.parse(config["rss_address"], request_headers=headers)
        logger.info(f"RSS parsing completed. Found {len(rss_movietracker.get('entries', []))} entries")
        
        logger.info("Querying Notion database for existing movies")
        notion_movies = NotionAPI.DataBase_item_query(config["databaseid"])
        watched_movie = [item['properties']['影片链接']['url'] for item in notion_movies]
        logger.info(f"Found {len(watched_movie)} existing movies in Notion database")
        
        processed_count = 0
        added_count = 0
        
        for idx, item in enumerate(rss_movietracker["entries"]):
            if "看过" not in item["title"]:
                continue
                
            logger.info(f"Processing item {idx+1}: {item['title']}")
            try:
                cover_url, watch_time, movie_url, score, comment = film_info1(item)

                rel = NotionAPI.select_items_form_Databaseitems(notion_movies, "影片链接", movie_url)
                if rel:
                    logger.debug(f"Movie already exists in database: {movie_url}")
                    continue
                    
                if movie_url not in watched_movie:
                    # 注意：film_info2 需要 headers 参数了
                    title, movie_type, director = film_info2(movie_url, headers)
                    movie_name = remove_year(title)  
                    movie_id = search_movie(config["tmdb_api_key"], movie_name)
                    
                    poster_url = ""
                    if movie_id:
                        poster_url = get_movie_poster(config["tmdb_api_key"], movie_id)
                        logger.info(f'Poster URL for "{movie_name}": {poster_url}')
                    else:
                        logger.warning(f'No results found for "{movie_name}"')
                        poster_url = " "

                    body = {
                        'properties': {
                            '名称': {
                                'title': [{'type': 'text', 'text': {'content': str(title)}}]
                            },
                            '观看时间': {'date': {'start': str(watch_time)}},
                            '评分': {'type': 'select', 'select': {'name': str(score)}},
                            '封面': {
                                'files': [{'type': 'external', 'name': '封面', 'external': {'url': str(poster_url)}}]
                            },
                            '有啥想说的不': {'type': 'rich_text',
                                             'rich_text': [
                                                 {'type': 'text', 'text': {'content': str(comment)},
                                                  'plain_text': str(comment)}]},
                            '影片链接': {'type': 'url', 'url': str(movie_url)},
                            '类型': {'type': 'multi_select', 'multi_select': [{'name': str(item)} for item in movie_type]},
                            '导演': {'type': 'multi_select', 'multi_select': [{'name': str(item)} for item in director]},

                        }
                    }
                    logger.debug(f"Adding movie to Notion database: {title}")
                    NotionAPI.DataBase_additem(config["databaseid"], body, title)
                    added_count += 1
                    # 避免请求过快被封 IP
                    time.sleep(3)
                    processed_count += 1
                else:
                    logger.debug(f"Movie already processed: {movie_url}")
            except Exception as e:
                logger.error(f"Error processing item {item['title']}: {str(e)}")
                continue
                
        logger.info(f"Processing completed. Added {added_count} new movies, processed {processed_count} items in total")
    except Exception as e:
        logger.critical(f"Critical error in main execution: {str(e)}")
        # 抛出异常，让 GitHub Actions 知道这次运行失败了（显示红色❌）
        raise