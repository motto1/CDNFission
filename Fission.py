import os
import re
import random
import ipaddress
import subprocess
import concurrent.futures
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from lxml import etree
from fake_useragent import UserAgent
import requests

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 文件配置和行数限制更新
IPS_FILE = "Fission_ip.txt"
DOMAINS_FILE = "Fission_domain.txt"
DNS_RESULT_FILE = "dns_result.txt"

MAX_LINES_IPS = 1500   # IP文件行数限制
MAX_LINES_DOMAINS = 500   # 域名文件行数限制

# 并发数配置
MAX_WORKERS_REQUEST = 20   # 并发请求数量
MAX_WORKERS_DNS = 50       # 并发DNS查询数量

# 生成随机User-Agent
ua = UserAgent()

# 网站配置
SITES_CONFIG = {
    "site_ip138": {
        "url": "https://site.ip138.com/",
        "xpath": '//ul[@id="list"]/li/a'
    },
    "dnsdblookup": {
        "url": "https://dnsdblookup.com/",
        "xpath": '//ul[@id="list"]/li/a'
    },
    "ipchaxun": {
        "url": "https://ipchaxun.com/",
        "xpath": '//div[@id="J_domain"]/p/a'
    }
}

def setup_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def get_headers():
    return {
        'User-Agent': ua.random,
        'Accept': '*/*',
        'Connection': 'keep-alive',
    }

def fetch_domains_for_ip(ip_address, session, attempts=0, used_sites=None):
    logging.info(f"Fetching domains for {ip_address}...")
    if used_sites is None:
        used_sites = []
    if attempts >= 3:  
        return []

    available_sites = {key: value for key, value in SITES_CONFIG.items() if key not in used_sites}
    if not available_sites:
        return []

    site_key = random.choice(list(available_sites.keys()))
    site_info = available_sites[site_key]
    used_sites.append(site_key)

    try:
        url = f"{site_info['url']}{ip_address}/"
        headers = get_headers()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text

        parser = etree.HTMLParser()
        tree = etree.fromstring(html_content, parser)
        a_elements = tree.xpath(site_info['xpath'])
        domains = [a.text for a in a_elements if a.text]

        if domains:
            logging.info(f"Succeeded to fetch domains for {ip_address} from {site_info['url']}")
            return domains
        else:
            raise Exception("No domains found")

    except Exception as e:
        logging.error(f"Error fetching domains for {ip_address} from {site_info['url']}: {e}")
        return fetch_domains_for_ip(ip_address, session, attempts + 1, used_sites)

def fetch_domains_concurrently(ip_addresses):
    session = setup_session()
    domains = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_REQUEST) as executor:
        future_to_ip = {executor.submit(fetch_domains_for_ip, ip, session): ip for ip in ip_addresses}
        for future in concurrent.futures.as_completed(future_to_ip):
            domains.extend(future.result())

    return list(set(domains))

def dns_lookup(domain):
    logging.info(f"Performing DNS lookup for {domain}...")
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    return domain, result.stdout

def perform_dns_lookups(domain_filename, result_filename, unique_ipv4_filename):
    try:
        with open(domain_filename, 'r') as file:
            domains = file.read().splitlines()

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_DNS) as executor:
            results = list(executor.map(dns_lookup, domains))

        with open(result_filename, 'w') as output_file:
            for domain, output in results:
                output_file.write(output)

        ipv4_addresses = set()
        for _, output in results:
            ipv4_addresses.update(re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', output))

        with open(unique_ipv4_filename, 'r') as file:
            exist_list = {ip.strip() for ip in file}

        filtered_ipv4_addresses = set()
        for ip in ipv4_addresses:
            try:
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_global:
                    filtered_ipv4_addresses.add(ip)
            except ValueError:
                continue
        
        filtered_ipv4_addresses.update(exist_list)

        with open(unique_ipv4_filename, 'w') as output_file:
            for address in filtered_ipv4_addresses:
                output_file.write(address + '\n')

    except Exception as e:
        logging.error(f"Error performing DNS lookups: {e}")

def limit_file_size(filename, new_lines, max_lines):
    with open(filename, 'r') as file:
        existing_lines = file.readlines()
    
    combined_lines = existing_lines + [line + "\n" for line in new_lines]
    if len(combined_lines) > max_lines:
        combined_lines = combined_lines[-max_lines:]
    
    with open(filename, 'w') as file:
        file.writelines(combined_lines)

def main():
    if not os.path.exists(IPS_FILE):
        with open(IPS_FILE, 'w') as file:
            file.write("")
    
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w') as file:
            file.write("")

    with open(IPS_FILE, 'r') as ips_txt:
        ip_list = [ip.strip() for ip in ips_txt]

    domain_list = fetch_domains_concurrently(ip_list)
    logging.info("域名列表为: %s", domain_list)
    
    with open(DOMAINS_FILE, "r") as file:
        exist_list = [domain.strip() for domain in file]

    domain_list = list(set(domain_list + exist_list))

    # 更新文件限制
    limit_file_size(DOMAINS_FILE, domain_list, MAX_LINES_DOMAINS)
    logging.info("IP -> 域名 已完成")

    perform_dns_lookups(DOMAINS_FILE, DNS_RESULT_FILE, IPS_FILE)
    logging.info("域名 -> IP 已完成")

    # 更新文件限制
    limit_file_size(IPS_FILE, ip_list, MAX_LINES_IPS)

if __name__ == '__main__':
    main()
