#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Release Monitor for GitHub Actions
监控 GitHub 仓库新版本发布，下载文件并发送到 Telegram
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class GitHubReleaseMonitor:
    def __init__(self):
        """从环境变量初始化配置"""
        self.repo_url = os.environ.get('GITHUB_REPO_URL', 'https://github.com/Silent1566/webhtv')
        self.telegram_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        self.github_token = os.environ.get('GITHUB_TOKEN', '')
        
        # 验证必要的环境变量
        missing_vars = []
        if not self.telegram_bot_token:
            missing_vars.append('TELEGRAM_BOT_TOKEN')
        if not self.telegram_chat_id:
            missing_vars.append('TELEGRAM_CHAT_ID')
        
        if missing_vars:
            error_msg = f"缺少必要的环境变量: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 解析仓库信息
        try:
            parts = self.repo_url.rstrip('/').split('github.com/')[-1].split('/')
            self.owner, self.repo = parts[0], parts[1]
            self.api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
        except Exception as e:
            logger.error(f"解析仓库URL失败: {e}")
            raise ValueError(f"无效的仓库URL: {self.repo_url}") from e
        
        self.state_file = Path('last_release.json')
        logger.info(f"监控器初始化完成: {self.owner}/{self.repo}")

    def get_latest_release(self):
        """获取最新的 release 信息"""
        try:
            headers = {
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'GitHub-Release-Monitor'
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
            data = {
                'last_tag': tag,
                'updated_at': datetime.now().isoformat(),
                'repo': f"{self.owner}/{self.repo}"
            }
            self.state_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
            logger.info(f"状态已保存: {tag}")
            return True
        except Exception as e:
            logger.error(f"保存状态文件失败: {e}")
            return False

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
            
            size_mb = filepath.stat().st_size / 1024 / 1024
            logger.info(f"下载完成: {filename} ({size_mb:.2f} MB)")
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
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
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
        tag = release.get('tag_name', 'unknown')
        name = release.get('name', tag)
        
        # 解析时间
        try:
            pub_time = datetime.fromisoformat(
                release['published_at'].replace('Z', '+00:00')
            ).strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception as e:
            logger.warning(f"时间解析失败: {e}")
            pub_time = release.get('published_at', '未知时间')
        
        # 处理更新说明 - 修复 None 问题
        body = release.get('body')
        if not body:  # 处理 None 或空字符串
            body = '无更新说明'
        else:
            body = str(body).strip()
        
        if len(body) > 3500:
            body = body[:3500] + "\n\n...(内容过长)"
        
        # 文件列表
        assets = release.get('assets', [])
        if assets:
            try:
                files_list = "\n".join([
                    f"  📄 {a['name']} ({a['size']/1024/1024:.1f}MB)"
                    for a in assets
                ])
            except Exception as e:
                logger.warning(f"文件列表格式化失败: {e}")
                files_list = f"  {len(assets)} 个文件"
        else:
            files_list = "  无附件"
        
        # 获取 HTML URL
        html_url = release.get('html_url', f'{self.repo_url}/releases/tag/{tag}')
        
        msg = f"""🎉 <b>新版本发布</b>

📦 <b>{name}</b>
🏷️ 版本: <code>{tag}</code>
⏰ 时间: {pub_time}

📝 <b>更新内容</b>
{body}

📎 <b>下载文件</b> ({len(assets)}个)
{files_list}

🔗 <a href="{html_url}">GitHub Release</a>"""
        
        return msg

    def run(self):
        """主运行逻辑"""
        logger.info("=" * 50)
        logger.info("开始检查新版本...")
        
        # 获取最新版本
        latest = self.get_latest_release()
        if not latest:
            logger.error("无法获取版本信息")
            sys.exit(1)
        
        current_tag = latest['tag_name']
        last_tag = self.get_last_tag()
        
        logger.info(f"当前最新版本: {current_tag}")
        logger.info(f"上次记录版本: {last_tag}")
        
        # 首次运行检查
        if last_tag is None:
            logger.info("首次运行，检查版本发布时间...")
            try:
                pub_date = datetime.fromisoformat(
                    latest['published_at'].replace('Z', '+00:00')
                )
                days_old = (datetime.now(timezone.utc) - pub_date).days
                
                if days_old > 7:
                    logger.info(f"版本已发布{days_old}天，仅记录不通知")
                    self.save_last_tag(current_tag)
                    return
                else:
                    logger.info(f"版本发布{days_old}天，发送通知")
            except Exception as e:
                logger.warning(f"时间检查失败: {e}")
        
        # 检查是否需要更新
        if current_tag == last_tag:
            logger.info("✅ 已是最新版本")
            return
        
        logger.info(f"🎉 发现新版本: {last_tag} → {current_tag}")
        
        # 发送通知
        message = self.format_message(latest)
        if not self.send_tg_message(message):
            logger.error("发送通知失败，终止流程")
            sys.exit(1)
        
        # 下载并发送文件
        assets = latest.get('assets', [])
        logger.info(f"准备处理 {len(assets)} 个文件")
        
        success_count = 0
        for asset in assets:
            try:
                url = asset.get('browser_download_url')
                name = asset.get('name')
                
                if not url or not name:
                    logger.warning(f"跳过无效资产: {asset}")
                    continue
                
                # 下载
                filepath = self.download_asset(url, name)
                if not filepath:
                    continue
                
                # 发送
                caption = f"📦 {latest.get('name', current_tag)}\n{name}"
                if self.send_tg_document(filepath, caption):
                    success_count += 1
                
                # 清理本地文件
                try:
                    filepath.unlink()
                except Exception as e:
                    logger.warning(f"清理文件失败: {e}")
                    
            except Exception as e:
                logger.error(f"处理文件失败: {e}")
                continue
        
        # 保存状态
        self.save_last_tag(current_tag)
        
        logger.info("=" * 50)
        logger.info(f"✅ 完成！成功发送 {success_count}/{len(assets)} 个文件")


def main():
    """主函数"""
    try:
        monitor = GitHubReleaseMonitor()
        monitor.run()
    except Exception as e:
        logger.error(f"程序错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
