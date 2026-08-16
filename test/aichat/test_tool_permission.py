"""工具权限双层接线测试

覆盖：权限级别获取（默认/配置覆盖）、check_permission（user_id/session）、
schema 层过滤（SUPERUSER 工具对普通用户隐藏、超管可见）。

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_tool_permission.py
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.modules.aichat.aichat.config import Config  # noqa: E402
from hoshino.modules.aichat.aichat.session import Session  # noqa: E402
from hoshino.modules.aichat.aichat.tools import permission  # noqa: E402
from hoshino.modules.aichat.aichat.tools.access import get_available_tools  # noqa: E402

conf = Config.get_instance('aichat')


class TestPermission(unittest.TestCase):
    def test_default_user(self):
        self.assertEqual(permission.get_tool_permission("web_search"), "USER")
        self.assertEqual(permission.get_tool_permission("不存在的工具"), "USER")

    def test_config_override(self):
        old = conf.tool_permissions
        conf.tool_permissions = {"web_search": "SUPERUSER"}
        try:
            self.assertEqual(permission.get_tool_permission("web_search"), "SUPERUSER")
        finally:
            conf.tool_permissions = old

    def test_check_permission_by_user_id(self):
        with patch.object(permission, "_get_superusers", return_value={10001}):
            ok, _ = permission.check_permission("SUPERUSER", user_id=10001)
            denied, reason = permission.check_permission("SUPERUSER", user_id=99999)
            self.assertTrue(ok)
            self.assertFalse(denied)
            self.assertIn("超级用户", reason)

    def test_check_permission_by_session(self):
        with patch.object(permission, "_get_superusers", return_value={10001}):
            su_session = Session("perm_test_su", 10001)
            normal_session = Session("perm_test_normal", 99999)
            ok, _ = permission.check_permission("SUPERUSER", session=su_session)
            denied, _ = permission.check_permission("SUPERUSER", session=normal_session)
            self.assertTrue(ok)
            self.assertFalse(denied)

    def test_user_level_always_pass(self):
        ok, reason = permission.check_permission("USER", user_id=None)
        self.assertTrue(ok)
        self.assertEqual(reason, "user")


class TestSchemaFilter(unittest.IsolatedAsyncioTestCase):
    async def test_superuser_tool_hidden_from_normal_user(self):
        old = conf.tool_permissions
        conf.tool_permissions = {"web_search": "SUPERUSER"}
        try:
            with patch.object(permission, "_get_superusers", return_value={10001}):
                normal = Session("perm_n_1", 99999)
                su = Session("perm_s_1", 10001)
                names_normal = {t["function"]["name"] for t in await get_available_tools(normal)}
                names_su = {t["function"]["name"] for t in await get_available_tools(su)}
        finally:
            conf.tool_permissions = old
        self.assertNotIn("web_search", names_normal)
        self.assertIn("web_search", names_su)

    async def test_schema_cache(self):
        old = conf.tool_permissions
        conf.tool_permissions = {}
        try:
            s = Session("perm_cache_1", 99999)
            first = await get_available_tools(s)
            second = await get_available_tools(s)
        finally:
            conf.tool_permissions = old
        self.assertIs(first, second)  # 激活集合未变 → 命中缓存，返回同一对象


if __name__ == "__main__":
    unittest.main()
