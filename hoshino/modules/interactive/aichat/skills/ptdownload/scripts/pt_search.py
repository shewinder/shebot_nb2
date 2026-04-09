#!/usr/bin/env python3
"""
PT 站资源搜索脚本
用法: python pt_search.py <关键词> [--save]
"""
from pathlib import Path
import sys
import json
import re
import argparse
from urllib.parse import quote
from typing import List, Dict, Any, Optional

# 添加 skill 目录到路径以便导入 config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import get_stations, get_qb_config, PTStation


try:
    import aiohttp
    import asyncio
    from bs4 import BeautifulSoup
except ImportError as e:
    print(json.dumps({
        "success": False,
        "error": f"缺少依赖: {e}. 请安装: uv pip install aiohttp beautifulsoup4"
    }, ensure_ascii=False))
    sys.exit(1)


class PTSearcher:
    """PT 站搜索器"""
    
    def __init__(self, station_config: PTStation):
        self.config = station_config
    
    async def search(self, keyword: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """搜索资源"""
        
        if not self.config.search_url:
            return []
        
        try:
            search_url = self.config.search_url.format(keyword=quote(keyword))
            method = self.config.search_method.lower()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            headers.update(self.config.headers)
            
            if method == "post":
                data = {k: v.format(keyword=keyword) for k, v in self.config.search_params.items()}
                async with session.post(search_url, headers=headers, data=data) as resp:
                    html = await resp.text()
            else:
                async with session.get(search_url, headers=headers) as resp:
                    html = await resp.text()
            
            results = self._parse_results(html)
            for r in results:
                r["station"] = self.config.name
            return results
            
        except Exception as e:
            return [{"error": f"{self.config.name}: {str(e)}"}]
    
    def _parse_results(self, html: str) -> List[Dict[str, Any]]:
        """解析搜索结果"""
        
        results = []
        soup = BeautifulSoup(html, 'html.parser')
        
        selector = self.config.result_selector
        rows = soup.select(selector)
        
        mapping = self.config.field_mapping
        
        for row in rows:
            try:
                result = {}
                
                # 提取标题
                title_sel = mapping.get('title', 'a[href*="details"]')
                title_elem = row.select_one(title_sel)
                if title_elem:
                    result['title'] = title_elem.get_text(strip=True)
                    if not mapping.get('link'):
                        link = title_elem.get('href')
                        if link:
                            result['link'] = self._make_absolute_url(link)
                
                # 提取下载链接
                download_sel = mapping.get('download')
                if download_sel:
                    download_elem = row.select_one(download_sel)
                    if download_elem:
                        href = download_elem.get('href')
                        if href:
                            result['download'] = self._make_absolute_url(href)
                
                # 提取大小
                size_sel = mapping.get('size')
                if size_sel:
                    size_elem = row.select_one(size_sel)
                    if size_elem:
                        result['size'] = size_elem.get_text(strip=True)
                
                # 提取做种数
                seeders_sel = mapping.get('seeders')
                if seeders_sel:
                    seeders_elem = row.select_one(seeders_sel)
                    if seeders_elem:
                        result['seeders'] = seeders_elem.get_text(strip=True)
                
                if result.get('title'):
                    results.append(result)
                    
            except Exception:
                continue
        
        return results
    
    def _make_absolute_url(self, url: str) -> str:
        """转换为绝对 URL"""
        from urllib.parse import urljoin
        base = self.config.search_url.split('?')[0]
        return urljoin(base, url)


def parse_size(size_str: str) -> float:
    """解析大小为 GB 数值"""
    size_str = size_str.upper().replace(',', '')
    match = re.search(r'([\d.]+)\s*(T|G|M|K)?', size_str)
    if not match:
        return 0
    
    num = float(match.group(1))
    unit = match.group(2) if match.group(2) else 'B'
    
    multipliers = {'T': 1024, 'G': 1, 'M': 1/1024, 'K': 1/1024/1024, 'B': 0}
    return num * multipliers.get(unit, 0)


def parse_seeders(seeders_str: str) -> int:
    """解析做种数为整数"""
    nums = re.findall(r'\d+', str(seeders_str))
    return int(nums[0]) if nums else 0


def score_result(result: Dict[str, Any]) -> float:
    """给搜索结果打分，越高越推荐"""
    score = 0
    
    # 做种数权重高
    seeders = parse_seeders(result.get('seeders', '0'))
    score += min(seeders, 100) * 2  # 最高 200 分
    
    # 大小适中加分（电影 8-20GB 最佳）
    size_gb = parse_size(result.get('size', '0'))
    if 8 <= size_gb <= 20:
        score += 50
    elif 5 <= size_gb < 8 or 20 < size_gb <= 30:
        score += 30
    
    # 1080p/2160p 加分
    title = result.get('title', '').lower()
    if '2160p' in title or '4k' in title or 'uhd' in title:
        score += 30
    elif '1080p' in title:
        score += 20
    
    # WEB-DL 减分（通常质量较差）
    if 'web-dl' in title or 'webdl' in title:
        score -= 10
    
    return score


async def search_all(keyword: str) -> Dict[str, Any]:
    """搜索所有启用的 PT 站"""
    
    stations = get_stations()
    if not stations:
        return {
            "success": False,
            "error": "未配置 PT 站。请在 config.json 中添加站点配置。"
        }
    
    all_results = []
    errors = []
    
    async with aiohttp.ClientSession() as session:
        for station_config in stations:
            searcher = PTSearcher(station_config)
            try:
                results = await searcher.search(keyword, session)
                if results and 'error' in results[0]:
                    errors.append(results[0]['error'])
                else:
                    all_results.extend(results)
            except Exception as e:
                errors.append(f"{station_config.name}: {str(e)}")
    
    if not all_results and errors:
        return {
            "success": False,
            "error": f"搜索失败: {'; '.join(errors)}"
        }
    
    # 按推荐度排序
    all_results.sort(key=score_result, reverse=True)
    
    return {
        "success": True,
        "keyword": keyword,
        "count": len(all_results),
        "results": all_results[:15],  # 最多返回 15 个
        "errors": errors if errors else None
    }


def format_results(data: Dict[str, Any]) -> str:
    """格式化结果为可读文本（包含下载链接）"""
    
    if not data.get('success'):
        return f"❌ 搜索失败: {data.get('error')}"
    
    results = data.get('results', [])
    if not results:
        return f"🔍 未找到「{data.get('keyword')}」相关资源"
    
    lines = [f"🔍 搜索到 {data.get('count')} 个资源：\n"]
    
    for i, r in enumerate(results, 1):
        title = r.get('title', '未知')[:50]
        size = r.get('size', '未知')
        seeders = r.get('seeders', '-')
        station = r.get('station', '未知')
        download = r.get('download', '')
        
        # 推荐标记
        score = score_result(r)
        mark = "⭐" if score > 150 else ""
        
        lines.append(f"{i}. {title} {mark}")
        lines.append(f"   大小: {size} | 做种: {seeders} | 来源: {station}")
        
        # 始终显示下载链接（AI 可以看到，用于选择下载）
        if download:
            lines.append(f"   下载链接: {download}")
        
        lines.append("")
    
    if data.get('errors'):
        lines.append(f"\n⚠️ 部分站点搜索失败: {'; '.join(data['errors'])}")
    
    lines.append('\n💡 回复"下载第N个"选择下载')
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='PT 站资源搜索')
    parser.add_argument('keyword', help='搜索关键词')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--save', action='store_true', help='保存结果到文件')
    
    args = parser.parse_args()
    
    result = asyncio.run(search_all(args.keyword))
    
    if args.json or args.save:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_results(result))
    
    sys.exit(0 if result.get('success') else 1)


if __name__ == "__main__":
    main()
