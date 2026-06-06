#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Release Monitor for GitHub Actions - 修复版本
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
        self.github_token = os.environ.get('GITHUB_TOKEN')
        
        # 验证必要的环境变量
        if not self.telegram_bot_token:
            logger.error("错误: 缺少 TELEGRAM_BOT_TOKEN 环境变量")
            sys.exit(1)
        if not self.telegram_chat_id:
            logger.error("错误: 缺少 TELEGRAM_CHAT_ID 环境变量")
            sys.exit(1)

        # 提取 owner 和 repo
        try:
            parts = self.repo_url.rstrip('/').split('github.com/')[-1].split('/')
            self.owner, self.repo = parts[0], parts[1]
            self.api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
        except Exception as e:
            logger.error(f"解析仓库URL失败: {e}")
            sys.exit(1)
        
        self.state_file = Path('last_release.json')
        logger.info(f"初始化监控器: {self.repo_url}")

    def get_latest_release(self):
        """获取最新的 release 信息"""
        try:
            headers = {
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'GitHub-Actions-Monitor'
            }
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
        """获取上次处理的 tag"""
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text(encoding='utf-8'))
                return data.get('last_tag')
        except Exception as e:
            logger.warning(f"读取状态文件失败: {e}")
        return None

    def save_last_tag(self, tag):
        """保存当前处理的 tag"""
        try:
            self.state_file.write_text(
                json.dumps({'last_tag': tag, 'time': datetime.now().isoformat()}),
                encoding='utf-8'
            )
            logger.info(f"已保存状态: {tag}")
        except Exception as e:
            logger.error(f"保存状态文件失败: {e}")

    def download_asset(self, url, filename):
        """下载资源文件"""
        try:
            filepath = Path(filename)
            if filepath.exists():
                logger.info(f"文件已存在，跳过下载: {filename}")
                return filepath
            
            headers = {'Accept': 'application/octet-stream'}
            if self.github_token:
                headers['Authorization'] = f"token {self.github_token}"
            
            logger.info(f"开始下载: {filename}")
            response = requests.get(url, headers=headers, stream=True, timeout=300)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"下载完成: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"下载失败 {filename}: {e}")
            return None

    def send_tg_message(self, text):
        """发送消息到 Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            response = requests.post(url, json={
                'chat_id': self.telegram_chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }, timeout=30)
            response.raise_for_status()
            logger.info("Telegram 消息发送成功")
            return True
        except Exception as e:
            logger.error(f"发送 TG 消息失败: {e}")
            return False

    def send_tg_document(self, filepath, caption):
        """发送文件到 Telegram"""
        try:
            file_size = filepath.stat().st_size
            if file_size > 50 * 1024 * 1024:
                logger.warning(f"文件超过 50MB，跳过发送: {filepath.name} ({file_size / 1024 / 1024:.2f}MB)")
                return False
            
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendDocument"
            with open(filepath, 'rb') as f:
                response = requests.post(url, files={'document': f}, data={
                    'chat_id': self.telegram_chat_id,
                    'caption': caption
                }, timeout=300)
            response.raise_for_status()
            logger.info(f"文件发送成功: {filepath.name}")
            return True
        except Exception as e:
            logger.error(f"发送文件失败 {filepath.name}: {e}")
            return False

    def format_message(self, release):
        """格式化通知消息"""
        try:
            pub_time = datetime.fromisoformat(
                release['published_at'].replace('Z', '+00:00')
            ).strftime('%Y-%m-%d %H:%M:%S')
        except:
            pub_time = release.get('published_at', '未知时间')
        
        body = release.get('body', '无更新说明')
        if len(body) > 3000:
            body = body[:3000] + "...\n\n(内容过长，已截断)"
        
        assets = release.get('assets', [])
        if assets:
            assets_text = "\n".join([f"  • {a['name']} ({a['size'] / 1024 / 1024:.2f} MB)" for a in assets])
        else:
            assets_text = "  无附件"
        
        return f"""🎉 <b>发现新版本!</b>

📦 <b>版本:</b> {release.get('name', release['tag_name'])}
🏷️ <b>Tag:</b> {release['tag_name']}
🕐 <b>发布时间:</b> {pub_time}

📝 <b>更新明细:</b>
{body}

📎 <b>包含文件:</b>
{assets_text}

🔗 <a href="{release['html_url']}">查看 Release 页面</a>"""

    def run(self):
        """主运行逻辑"""
        logger.info("开始检查新版本...")
        
        latest = self.get_latest_release()
        if not latest:
            logger.error("未能获取 release 信息")
            sys.exit(1)
        
        latest_tag = latest['tag_name']
        last_tag = self.get_last_tag()
        
        # 首次运行或缓存丢失的处理
        if last_tag is None:
            logger.info("首次运行或缓存丢失")
            # 检查发布时间，避免发送旧版本
            try:
                pub_time = datetime.fromisoformat(
                    latest['published_at'].replace('Z', '+00:00')
                )
                days_diff = (datetime.now(timezone.utc) - pub_time).days
                if days_diff > 7:  # 超过7天的版本不发送
                    logger.info(f"版本已发布 {days_diff} 天，仅记录状态，不发送通知")
                    self.save_last_tag(latest_tag)
                    return
            except:
                pass
        
        # 检查是否是新版本
        if latest_tag == last_tag:
            logger.info(f"已是最新版本: {latest_tag}")
            return
            
        logger.info(f"发现新版本: {last_tag} -> {latest_tag}")
        
        # 发送文本通知
        message = self.format_message(latest)
        if not self.send_tg_message(message):
            logger.error("发送消息失败，终止流程")
            sys.exit(1)
        
        # 下载并发送文件
        assets = latest.get('assets', [])
        for asset in assets:
            try:
                filepath = self.download_asset(
                    asset['browser_download_url'],
                    asset['name']
                )
                if filepath and filepath.exists():
                    caption = f"📦 {latest['tag_name']} - {asset['name']}"
                    self.send_tg_document(filepath, caption)
                    # 清理本地文件
                    try:
                        filepath.unlink()
                    except:
                        pass
            except Exception as e:
                logger.error(f"处理文件 {asset.get('name', 'unknown')} 失败: {e}")
                continue
                
        # 保存状态
        self.save_last_tag(latest_tag)
        logger.info("处理完成！")

if __name__ == '__main__':
    try:
        monitor = GitHubReleaseMonitor()
        monitor.run()
    except Exception as e:
        logger.error(f"程序执行失败: {e}", exc_info=True)
        sys.exit(1)
