"""skill 自更新系统测试（updater + 工具权限）

覆盖：创建/热加载、非法名称、更新备份与回滚、内置只读与用户副本、
脚本路径遍历、审计、备份轮换、schema 层权限过滤。

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_skill_updater.py
"""
import json
import sys
import tempfile
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
from hoshino.modules.aichat.aichat.skills import skill_manager, updater  # noqa: E402
from hoshino.modules.aichat.aichat.skills.discovery import BUILTIN_SKILL_PATH  # noqa: E402
from hoshino.modules.aichat.aichat.tools import permission  # noqa: E402
from hoshino.modules.aichat.aichat.tools.access import get_available_tools  # noqa: E402

conf = Config.get_instance('aichat')


class TestSkillUpdater(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.old_paths = conf.skill_user_paths
        conf.skill_user_paths = [str(Path(self._tmp.name) / "skills")]
        updater.reload_skills()

    def tearDown(self):
        conf.skill_user_paths = self.old_paths
        updater.reload_skills()

    def _body(self, name: str) -> str:
        skill = skill_manager.get_skill(name)
        return skill.content if skill else ""

    def test_create_and_reload_visible(self):
        ok, msg = updater.create_skill("testcalc", "测试计算", "做四则运算", user_id=1)
        self.assertTrue(ok, msg)
        skill = skill_manager.get_skill("testcalc")
        self.assertIsNotNone(skill)
        self.assertIn("四则运算", skill.content)
        self.assertEqual(skill.metadata.description, "测试计算")

    def test_invalid_name_rejected(self):
        for bad in ["../evil", "A B", "中文", "a/b", "", "x" * 51]:
            ok, _ = updater.create_skill(bad, "d", "c")
            self.assertFalse(ok, f"应拒绝非法名称: {bad}")

    def test_update_backup_and_rollback(self):
        updater.create_skill("testroll", "d", "v1", user_id=1)
        ok, msg = updater.update_skill("testroll", content="v2", user_id=1)
        self.assertTrue(ok, msg)
        self.assertEqual(self._body("testroll"), "v2")

        ok, msg = updater.rollback_skill("testroll", user_id=1)
        self.assertTrue(ok, msg)
        self.assertEqual(self._body("testroll"), "v1")

    def test_backup_rotation_keeps_five(self):
        updater.create_skill("testrot", "d", "v0", user_id=1)
        for i in range(1, 7):
            ok, _ = updater.update_skill("testrot", content=f"v{i}", user_id=1)
            self.assertTrue(ok)
        backups = updater._list_backups("testrot")
        self.assertEqual(len(backups), updater.BACKUP_KEEP)

    def test_builtin_readonly_and_user_copy(self):
        builtin_md = BUILTIN_SKILL_PATH / "setu" / "SKILL.md"
        before = builtin_md.read_text(encoding="utf-8")

        # 删除内置被拒
        ok, msg = updater.delete_skill("setu", user_id=1)
        self.assertFalse(ok)
        self.assertIn("只读", msg)

        # 更新内置 → 用户副本，内置文件不动
        ok, msg = updater.update_skill("setu", description="用户定制版", user_id=1)
        self.assertTrue(ok, msg)
        self.assertEqual(builtin_md.read_text(encoding="utf-8"), before)
        skill = skill_manager.get_skill("setu")
        self.assertEqual(skill.metadata.description, "用户定制版")
        self.assertIn(str(Path(self._tmp.name)), str(skill.directory))

    def test_delete_user_skill(self):
        updater.create_skill("testdel", "d", "c", user_id=1)
        ok, msg = updater.delete_skill("testdel", user_id=1)
        self.assertTrue(ok, msg)
        self.assertIsNone(skill_manager.get_skill("testdel"))

    def test_script_path_traversal_rejected(self):
        ok, _ = updater.create_skill("testsec", "d", "c", scripts={"../evil.py": "x"}, user_id=1)
        self.assertFalse(ok)

    def test_script_written_and_validated(self):
        ok, msg = updater.create_skill(
            "testscr", "d", "c",
            scripts={"scripts/run.py": "print('hi')"},
            user_id=1,
        )
        self.assertTrue(ok, msg)
        script_path = Path(self._tmp.name) / "skills" / "testscr" / "scripts" / "run.py"
        self.assertTrue(script_path.exists())

    def test_audit_log_written(self):
        updater.create_skill("testaudit", "d", "c", user_id=123, group_id=456)
        log_path = Path(self._tmp.name) / "skills" / updater.CHANGES_LOG_NAME
        self.assertTrue(log_path.exists())
        records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(r["action"] == "create" and r["skill"] == "testaudit" for r in records))
        self.assertTrue(any(r["user_id"] == 123 and r["group_id"] == 456 for r in records))


class TestSkillAdminPermission(unittest.IsolatedAsyncioTestCase):
    async def test_schema_filter(self):
        with patch.object(permission, "_get_superusers", return_value={10001}):
            normal = Session("skp_n_1", 99999)
            su = Session("skp_s_1", 10001)
            names_normal = {t["function"]["name"] for t in await get_available_tools(normal)}
            names_su = {t["function"]["name"] for t in await get_available_tools(su)}
        for tool_name in ["create_skill", "update_skill", "delete_skill", "rollback_skill", "reload_skills"]:
            self.assertNotIn(tool_name, names_normal)
            self.assertIn(tool_name, names_su)


if __name__ == "__main__":
    unittest.main()
