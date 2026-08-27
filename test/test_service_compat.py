"""NoneBot 插件 ↔ Service 兼容桥测试

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/test_service_compat.py
"""
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

from nonebot.adapters.onebot.v11 import (  # noqa: E402
    Adapter,
    Bot as OneBot,
    GroupMessageEvent,
    Message,
    PrivateMessageEvent,
)

nonebot.get_driver().register_adapter(Adapter)

sys.path.insert(0, str(_PROJECT_ROOT))

from hoshino.compat import (  # noqa: E402
    bind_matcher,
    bind_plugin_matchers,
    load_nb_plugin,
    service_name_for,
)
from hoshino.service import Service, _loaded_matchers, _loaded_services  # noqa: E402


def _make_bot() -> OneBot:
    driver = nonebot.get_driver()
    return OneBot(adapter=Adapter(driver), self_id=1)


def _group_event(gid: int, uid: int = 1) -> GroupMessageEvent:
    return GroupMessageEvent(
        group_id=gid, user_id=uid, message=Message("hi"), raw_message="hi",
        self_id=1, time=0, post_type="message", message_id=1,
        message_type="group", sub_type="normal", font=0,
        sender={"user_id": uid, "nickname": "x", "role": "member"},
    )


def _private_event(uid: int = 1) -> PrivateMessageEvent:
    return PrivateMessageEvent(
        user_id=uid, message=Message("hi"), raw_message="hi",
        self_id=1, time=0, post_type="message", message_id=2,
        message_type="private", sub_type="friend", font=0,
        sender={"user_id": uid, "nickname": "x"},
    )


class TestServiceNameFor(unittest.TestCase):
    def test_prefix_stripped(self):
        self.assertEqual(service_name_for("nonebot_plugin_wordle"), "wordle")
        self.assertEqual(service_name_for("nonebot_parser"), "parser")

    def test_plain_name_kept(self):
        self.assertEqual(service_name_for("my_plugin"), "my_plugin")

    def test_prefix_only_falls_back(self):
        self.assertEqual(service_name_for("nonebot_plugin_"), "nonebot_plugin_")


class TestBindPluginMatchers(unittest.TestCase):
    """load_nb_plugin 登记后无参绑定（新增插件只改一处）"""

    @classmethod
    def setUpClass(cls):
        from hoshino.compat import load_nb_plugin

        # wordle 用 load_nb_plugin 加载并登记；handle 用裸 load_plugin（未登记）
        load_nb_plugin("nonebot_plugin_wordle")
        nonebot.load_plugin("nonebot_plugin_handle")
        # 无参绑定：只绑定登记过的插件
        cls.count = bind_plugin_matchers()

    def test_b_plugin_matchers_bound(self):
        self.assertGreater(self.count, 0, "应至少绑定 wordle 的 matcher")
        self.assertIn("wordle", _loaded_services, "缺少 Service: wordle")

    def test_a_non_registered_plugin_untouched(self):
        # 未登记插件（handle）不应被创建 Service / 绑定
        self.assertNotIn("handle", _loaded_services, "未登记插件不应被接管")

    def test_c_bound_matchers_registered(self):
        # 已绑定的 matcher 应进入 _loaded_matchers（日志 / 管理可见）
        self.assertTrue(
            any(mw.sv.name == "wordle" for mw in _loaded_matchers.values())
        )
        # handle 的 matcher 不应被绑定
        self.assertFalse(
            any(mw.sv.name == "handle" for mw in _loaded_matchers.values())
        )

    def test_d_idempotent(self):
        # 幂等：再次无参绑定不重复注册
        self.assertEqual(bind_plugin_matchers(), 0)

    def test_z_bind_remaining_with_explicit_list(self):
        # 显式列表可覆盖登记列表：补绑未登记的 handle
        more = bind_plugin_matchers(["nonebot_plugin_wordle", "nonebot_plugin_handle"])
        self.assertGreater(more, 0, "handle 的 matcher 应被补绑")
        self.assertIn("handle", _loaded_services)
        # 此时全部已绑定，再次调用不再新增
        self.assertEqual(bind_plugin_matchers(["nonebot_plugin_wordle", "nonebot_plugin_handle"]), 0)

    def test_y_dynamic_matcher_bound_by_rebind(self):
        # 回归：插件在 on_startup 阶段动态注册 matcher（如 parser 的链接解析），
        # 启动时已绑定过，on_startup 再调一次 bind_plugin_matchers 应补绑新 matcher
        from nonebot import on_message

        dynamic = on_message()
        dynamic.plugin_name = "nonebot_plugin_wordle"  # 模拟动态 matcher 的插件归属

        self.assertNotIn(dynamic, _loaded_matchers)
        self.assertEqual(bind_plugin_matchers(), 1)
        self.assertIn(dynamic, _loaded_matchers)
        # 再次调用不再重复
        self.assertEqual(bind_plugin_matchers(), 0)


class TestBindMatcherRule(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 隔离 service 数据目录：set_enable/set_disable 会写盘，避免污染真实数据
        import tempfile

        import hoshino.service as svc_mod

        self._tmp = tempfile.TemporaryDirectory()
        self._old_service_dir = svc_mod._service_dir
        svc_mod._service_dir = self._tmp.name

    def tearDown(self):
        import hoshino.service as svc_mod

        svc_mod._service_dir = self._old_service_dir
        self._tmp.cleanup()

    async def test_service_rule_applied(self):
        # 直接创建 matcher + 显式绑定自定义 Service，验证群开关生效
        from nonebot import on_message

        m = on_message()
        sv = Service("compat_demo_svc", visible=False)
        bind_matcher(m, sv)
        bot = _make_bot()

        # 默认 enable_on_default=True：群事件放行，私聊放行
        self.assertTrue(await m.rule(bot, _group_event(10001), {}))

        # 群被 disable 后：群事件拦截，私聊仍放行
        sv.set_disable(10001)
        self.assertFalse(await m.rule(bot, _group_event(10001), {}))
        self.assertTrue(await m.rule(bot, _private_event(), {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
