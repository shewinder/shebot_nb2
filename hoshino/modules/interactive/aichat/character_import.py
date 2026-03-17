"""
角色卡导入模块
支持从 PNG 图片中导入角色卡（TavernAI / SillyTavern 格式）
PNG 图片中包含 base64 编码的 JSON 元数据
"""
import json
import base64
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from io import BytesIO
from loguru import logger

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class CharacterCard:
    """角色卡数据类"""
    def __init__(self, data: Dict[str, Any]):
        self.raw_data = data
        self.name = data.get('name', '')
        self.description = data.get('description', '')
        self.personality = data.get('personality', '')
        self.scenario = data.get('scenario', '')
        self.first_mes = data.get('first_mes', '')
        self.mes_example = data.get('mes_example', '')
        self.creator = data.get('creator', '')
        self.tags = data.get('tags', [])
        self.version = data.get('character_version', '')
    
    def to_persona_text(self) -> str:
        """
        将角色卡转换为 AI 人格文本
        
        整合各种字段成连贯的人格描述
        """
        parts = []
        
        # 基本信息
        if self.name:
            parts.append(f"你的名字是{self.name}。")
        
        # 描述（最详细的字段，通常包含角色设定）
        if self.description:
            # 清理描述中的某些格式标记
            desc = self._clean_text(self.description)
            parts.append(desc)
        
        # 性格特点
        if self.personality:
            parts.append(f"你的性格特点：{self.personality}")
        
        # 场景设定
        if self.scenario:
            parts.append(f"当前场景：{self.scenario}")
        
        # 示例对话作为参考
        if self.mes_example:
            # 截取部分示例对话作为参考
            example = self._clean_text(self.mes_example)
            if len(example) > 500:
                example = example[:500] + "..."
            parts.append(f"参考对话风格：\n{example}")
        
        return "\n\n".join(parts)
    
    def _clean_text(self, text: str) -> str:
        """清理文本中的某些格式标记"""
        if not text:
            return ""
        # 移除 {{user}} 和 {{char}} 等占位符，替换为通用描述
        text = text.replace('{{user}}', '用户')
        text = text.replace('{{char}}', self.name or '助手')
        # 移除多余的空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    
    def get_info_text(self) -> str:
        """获取角色卡信息文本"""
        lines = [f"角色名称：{self.name}"]
        
        if self.creator:
            lines.append(f"作者：{self.creator}")
        
        if self.version:
            lines.append(f"版本：{self.version}")
        
        if self.tags and isinstance(self.tags, list):
            lines.append(f"标签：{', '.join(str(t) for t in self.tags[:10])}")
        
        if self.personality:
            lines.append(f"性格：{self.personality[:50]}{'...' if len(self.personality) > 50 else ''}")
        
        if self.scenario:
            lines.append(f"场景：{self.scenario[:50]}{'...' if len(self.scenario) > 50 else ''}")
        
        return '\n'.join(lines)


def parse_character_png(image_data: bytes) -> Tuple[bool, Optional[CharacterCard], str]:
    """
    从 PNG 图片字节数据中解析角色卡
    
    PNG 图片的元数据中会包含名为 "chara" 的字段，其值为 base64 编码的 JSON 数据
    
    Args:
        image_data: PNG 图片字节数据
        
    Returns:
        (是否成功, 角色卡对象, 消息)
    """
    if not PIL_AVAILABLE:
        return False, None, "未安装 Pillow 库，无法解析 PNG 图片"
    
    try:
        img = Image.open(BytesIO(image_data))
        
        # 获取图片中的文本元数据
        text_chunks = img.text
        
        if "chara" not in text_chunks:
            return False, None, "PNG 图片中未找到角色卡元数据（chara 字段），这可能不是有效的角色卡图片"
        
        # 解码 base64
        chara_b64 = text_chunks["chara"]
        try:
            json_str = base64.b64decode(chara_b64).decode("utf-8")
        except Exception as e:
            return False, None, f"解码角色卡数据失败：{e}"
        
        # 解析 JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return False, None, f"角色卡 JSON 解析错误：{e}"
        
        if not isinstance(data, dict):
            return False, None, "角色卡数据格式错误"
        
        # 检查必要字段
        if 'name' not in data:
            return False, None, "角色卡数据中未找到 'name' 字段"
        
        char = CharacterCard(data)
        return True, char, f"成功解析角色卡：{char.name}"
        
    except Image.UnidentifiedImageError:
        return False, None, "无法识别图片格式，请确保是有效的 PNG 文件"
    except Exception as e:
        logger.exception(f"解析角色卡 PNG 失败: {e}")
        return False, None, f"解析失败：{e}"


def parse_character_png_file(file_path: Path) -> Tuple[bool, Optional[CharacterCard], str]:
    """
    从 PNG 文件路径解析角色卡
    
    Args:
        file_path: PNG 文件路径
        
    Returns:
        (是否成功, 角色卡对象, 消息)
    """
    try:
        with open(file_path, 'rb') as f:
            image_data = f.read()
        return parse_character_png(image_data)
    except FileNotFoundError:
        return False, None, f"文件不存在：{file_path}"
    except Exception as e:
        logger.exception(f"读取 PNG 文件失败: {e}")
        return False, None, f"读取文件失败：{e}"
