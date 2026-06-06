#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Release Monitor (GitHub Actions 版)
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path
import logging
import argparse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GitHubReleaseMonitor:
    def __init__(self):
        # 从环境变量读取配置
        self.repo_url = os.environ.get('TARGET_REPO_URL')
        self.telegram_bot_token = os.environ.get('TG_BOT_TOKEN')
        self.telegram_chat_id = os.environ.get('TG_CHAT_ID')
        self.github_token = os.environ.get('GITHUB_TOKEN') # GitHub Actions 自动提供
        
        if not all([self.repo_url, self.telegram_bot_token, self.telegram_chat_id]):
            raise ValueError("缺少必要的环境变量，请检查 GitHub Secrets 配置！")

        self.download_dir = Path('./downloads')
        self.state_file = Path('last_release.json')
        
        self.owner, self.repo = self.extract_owner_repo(self.repo_url)
        self.api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
        
        self.download_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"初始化监控器: {self.repo_url}")

    def extract_owner_repo(self, url):
        url = url.rstrip('/')
        parts = url.split('github.com/')[-1].split('/')
        return parts[0], parts[1]

    def get_latest_release(self):
        try:
            headers = {
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'GitHub-Actions-Release-Monitor'
            }
            if self.github_token:
                headers['Authorization'] = f"token {self.github_token}"
            
            response = requests.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            releases = response.json()
            return releases[0] if releases else None
        except Exception as e:
            logger.error(f"获取release信息失败: {e}")
            return None

    def get_last_release_tag(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f).get('last_tag')
            except: return None
        return None

    def save_last_release_tag(self, tag):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump({'last_tag': tag}, f)

    def download_asset(self, asset_url, filename):
        filepath = self.download_dir / filename
        if filepath.exists(): return filepath
        
        logger.info(f"开始下载: {filename}")
        headers = {'Accept': 'application/octet-stream'}
        if self.github_token: headers['Authorization'] = f"token {self.github_token}"
        
        try:
            with requests.get(asset_url, headers=headers, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return filepath
        except Exception as e:
            logger.error(f"下载失败 {filename}: {e}")
            return None

    def send_telegram_message(self, message, parse_mode='HTML'):
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        data = {'chat_id': self.telegram_chat_id, 'text': message, 'parse_mode': parse_mode}
        try:
            requests.post(url, json=data, timeout=30).raise_for_status()
        except Exception as e:
            logger.error(f"发送TG消息失败: {e}")

    def send_telegram_document(self, filepath, caption, download_url):
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendDocument"
        file_size_mb = filepath.stat().st_size / (1024 * 1024)
        
        # Telegram 限制 50MB，超过则发送下载链接
        if file_size_mb > 50:
            logger.warning(f"文件 {filepath.name} 大于 50MB，转为发送下载链接")
            fallback_msg = f"⚠️ <b>文件过大无法直接推送</b>\n📦 {filepath.name} ({file_size_mb:.2f} MB)\n🔗 <a href='{download_url}'>点击下载</a>"
            self.send_telegram_message(fallback_msg)
            return

        try:
            with open(filepath, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': self.telegram_chat_id, 'caption': caption}
                requests.post(url, files=files, data=data, timeout=300).raise_for_status()
        except Exception as e:
            logger.error(f"发送TG文件失败 {filepath.name}: {e}")

    def format_release_message(self, release):
        tag_name = release.get('tag_name', 'Unknown')
        name = release.get('name', tag_name)
        published_at = release.get('published_at', '')
        body = release.get('body', '无详细说明')
        
        pub_time_str = datetime.fromisoformat(published_at.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S') if published_at else 'Unknown'
        if len(body) > 2000: body = body[:2000] + "...\n(内容过长已截断)"
        
        assets = release.get('assets', [])
        assets_info = "\n".join([f"  • {a['name']}" for a in assets]) if assets else "  无附件"
        
        return f"""🎉 <b>新版本发布: {self.repo}</b>

📦 <b>版本:</b> {name}
🏷️ <b>Tag:</b> <code>{tag_name}</code>
🕐 <b>时间:</b> {pub_time_str}

📝 <b>更新明细:</b>
{body}

📎 <b>打包文件:</b>
{assets_info}

🔗 <a href="{release.get('html_url')}">查看 Release 页面</a>
"""

    def check_and_notify(self):
        logger.info("开始检查新版本...")
        latest_release = self.get_latest_release()
        if not latest_release: return
        
        latest_tag = latest_release.get('tag_name')
        last_tag = self.get_last_release_tag()
        
        if last_tag is None:
            logger.info(f"首次运行，记录当前版本: {latest_tag}")
            self.save_last_release_tag(latest_tag)
            return
        
        if latest_tag == last_tag:
            logger.info(f"当前已是最新版本: {latest_tag}")
            return
        
        logger.info(f"发现新版本: {last_tag} -> {latest_tag}")
        
        # 发送文字通知
        self.send_telegram_message(self.format_release_message(latest_release))
        
        # 下载并发送文件
        for asset in latest_release.get('assets', []):
            asset_url = asset.get('browser_download_url')
            filename = asset.get('name')
            if not asset_url or not filename: continue
            
            filepath = self.download_asset(asset_url, filename)
            if filepath and filepath.exists():
                caption = f"📦 {latest_release.get('name', latest_tag)}\n{filename}"
                self.send_telegram_document(filepath, caption, asset_url)
        
        self.save_last_release_tag(latest_tag)
        logger.info("处理完成")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    
    monitor = GitHubReleaseMonitor()
    monitor.check_and_notify()
