#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Release Monitor for GitHub Actions
"""

import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GitHubReleaseMonitor:
    def __init__(self):
        """从环境变量初始化配置"""
        self.repo_url = os.environ.get('GITHUB_REPO_URL', 'https://github.com/Silent1566/webhtv')
        self.telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        self.github_token = os.environ.get('GITHUB_TOKEN') # Actions 自动注入
        
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.error("缺少必要的环境变量: TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
            sys.exit(1)

        # 提取 owner 和 repo
        parts = self.repo_url.rstrip('/').split('github.com/')[-1].split('/')
        self.owner, self.repo = parts[0], parts[1]
        self.api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
        
        # 状态文件路径 (用于 GitHub Actions Cache)
        self.state_file = Path('last_release.json')
        logger.info(f"初始化监控器: {self.repo_url}")

    def get_latest_release(self):
        """获取最新的 release 信息"""
        try:
            headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'GitHub-Actions'}
            if self.github_token:
                headers['Authorization'] = f"token {self.github_token}"
            
            response = requests.get(self.api_url, headers=headers, timeout=30)
            response.raise_for_status()
            releases = response.json()
            return releases[0] if releases else None
        except Exception as e:
            logger.error(f"获取 release 失败: {e}")
            return None

    def get_last_tag(self):
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text()).get('last_tag')
            except: pass
        return None

    def save_last_tag(self, tag):
        self.state_file.write_text(json.dumps({'last_tag': tag, 'time': datetime.now().isoformat()}))

    def download_asset(self, url, filename):
        try:
            filepath = Path(filename)
            if filepath.exists(): return filepath
            
            headers = {'Accept': 'application/octet-stream'}
            if self.github_token: headers['Authorization'] = f"token {self.github_token}"
            
            logger.info(f"下载中: {filename}")
            r = requests.get(url, headers=headers, stream=True, timeout=300)
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(8192): f.write(chunk)
            return filepath
        except Exception as e:
            logger.error(f"下载失败 {filename}: {e}")
            return None

    def send_tg_message(self, text):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            r = requests.post(url, json={
                'chat_id': self.telegram_chat_id, 'text': text, 'parse_mode': 'HTML'
            }, timeout=30)
            r.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"发送 TG 消息失败: {e}")
            return False

    def send_tg_document(self, filepath, caption):
        try:
            if filepath.stat().st_size > 50 * 1024 * 1024:
                logger.warning(f"文件超过 50MB，跳过发送: {filepath.name}")
                return False
            
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendDocument"
            with open(filepath, 'rb') as f:
                r = requests.post(url, files={'document': f}, data={
                    'chat_id': self.telegram_chat_id, 'caption': caption
                }, timeout=300)
            r.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"发送文件失败 {filepath.name}: {e}")
            return False

    def format_message(self, release):
        pub_time = datetime.fromisoformat(release['published_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
        body = release.get('body', '无更新说明')[:3000]
        assets = "\n".join([f"  • {a['name']}" for a in release.get('assets', [])]) or "  无附件"
        
        return f"""🎉 <b>发现新版本!</b>

📦 <b>版本:</b> {release.get('name', release['tag_name'])}
🏷️ <b>Tag:</b> {release['tag_name']}
🕐 <b>发布时间:</b> {pub_time}

📝 <b>更新明细:</b>
{body}

📎 <b>包含文件:</b>
{assets}

🔗 <a href="{release['html_url']}">查看 Release 页面</a>"""

    def run(self):
        latest = self.get_latest_release()
        if not latest: return
        
        latest_tag = latest['tag_name']
        last_tag = self.get_last_tag()
        is_cache_miss = last_tag is None
        
        # 如果是首次运行或 Cache 丢失，检查发布时间防止重复发送旧版本
        if is_cache_miss:
            pub_time = datetime.fromisoformat(latest['published_at'].replace('Z', '+00:00'))
            days_diff = (datetime.now(timezone.utc) - pub_time).days
            if days_diff > 3:
                logger.info(f"Cache 丢失，但最新版本已发布 {days_diff} 天，跳过发送，仅记录状态。")
                self.save_last_tag(latest_tag)
                return
        
        if latest_tag == last_tag:
            logger.info(f"已是最新版本: {latest_tag}")
            return
            
        logger.info(f"发现新版本: {last_tag} -> {latest_tag}")
        
        # 1. 发送文本通知
        if not self.send_tg_message(self.format_message(latest)):
            return
            
        # 2. 下载并发送文件
        for asset in latest.get('assets', []):
            filepath = self.download_asset(asset['browser_download_url'], asset['name'])
            if filepath:
                self.send_tg_document(filepath, f"📦 {latest['tag_name']} - {asset['name']}")
                # 发送后删除本地文件，保持 Actions 环境整洁
                filepath.unlink() 
                
        # 3. 更新状态
        self.save_last_tag(latest_tag)
        logger.info("处理完成！")

if __name__ == '__main__':
    monitor = GitHubReleaseMonitor()
    monitor.run()
