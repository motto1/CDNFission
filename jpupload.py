import os
import requests
import csv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 从环境变量中读取 Cloudflare 和 GitHub API 参数
api_token = os.getenv('CF_API_TOKEN')
zone_id = os.getenv('CF_ZONE_ID')
subdomain = "jp.2116666.xyz"  # 您的二级域名

# Cloudflare API 端点
api_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
headers = {
    "Authorization": f"Bearer {api_token}",
    "Content-Type": "application/json"
}

# GitHub 仓库的根目录 API URL
github_repo_api_url = 'https://api.github.com/repos/motto1/CDNFission/contents/'

# 要下载的文件名
file_name = 'jp.csv'

# GitHub Personal Access Token (PAT)
github_token = os.getenv('GH_TOKEN')

# 定义会话，并设置重试策略
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 522, 524], raise_on_status=False)
adapter = HTTPAdapter(max_retries=retries)
session.mount('https://', adapter)

# 通用的请求函数，带重试机制
def make_request(method, url, **kwargs):
    try:
        response = session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.SSLError as e:
        print(f"SSL错误：{e}")
    except requests.exceptions.RequestException as e:
        print(f"请求错误：{e}")
        print(f"请求URL: {url}")
        if 'json' in kwargs:
            print(f"请求数据: {kwargs['json']}")
        return None

# 获取所有指定二级域名下的 DNS 记录
def get_dns_records():
    response = make_request("GET", api_url, headers=headers, params={"name": subdomain})
    if response:
        return response.json().get('result', [])
    else:
        return []

# 删除指定 DNS 记录
def delete_dns_record(record_id):
    delete_url = f"{api_url}/{record_id}"
    response = make_request("DELETE", delete_url, headers=headers)
    if response:
        print(f"已成功删除 DNS 记录：{record_id}")

# 下载文件并保存为 CSV
def download_and_save_csv(url, save_path):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3.raw"  # 指定接受原始内容
    }
    response = make_request("GET", url, headers=headers)
    if response:
        content = response.text
        with open(save_path, 'w', newline='', encoding='utf-8') as csvfile:
            csvfile.write(content)
        print(f"数据已保存到 {save_path}")
    else:
        print(f"无法下载文件: {url}")

# 从 CSV 文件中读取 IP 地址并添加 DNS 记录
def add_dns_records_from_csv(save_path, limit=3):
    with open(save_path, 'r', newline='', encoding='utf-8') as csvfile:
        csv_reader = csv.reader(csvfile)
        count = 0
        for row in csv_reader:
            if count >= limit:
                break
            if row:
                ip_address = row[0]
                add_dns_record(ip_address)
                count += 1

# 添加 DNS 记录
def add_dns_record(ip_address):
    data = {
        "type": "A",
        "name": subdomain,
        "content": ip_address,
        "ttl": 1,
        "proxied": False
    }
    response = make_request("POST", api_url, headers=headers, json=data)
    if response:
        print(f"IP 地址 {ip_address} 已成功解析到 Cloudflare 域名下")

# 主逻辑
def main():
    try:
        # 获取并删除所有 DNS 记录
        records = get_dns_records()
        for record in records:
            delete_dns_record(record['id'])
        
        # 下载并保存新的CSV文件
        file_url = os.path.join(github_repo_api_url, file_name)
        download_and_save_csv(file_url, file_name)
        
        # 从 CSV 文件中添加前三个 DNS 记录
        add_dns_records_from_csv(file_name, limit=4)
        
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()
