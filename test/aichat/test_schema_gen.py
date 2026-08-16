"""工具 Schema 自动生成测试

覆盖：类型映射、required 推导、Literal/Enum、嵌套 Pydantic 模型内联、
Annotated/docstring 描述、注入参数排除、PEP 604 联合类型、
注册器自动生成、executor Pydantic 模型校验路径。

用法:
  cd /root/bot/shebot_nb2
  .venv/bin/python test/aichat/test_schema_gen.py
"""
import json
import sys
import unittest
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
load_dotenv(str(_PROJECT_ROOT / ".env.prod"))

import nonebot  # noqa: E402
nonebot.init()

sys.path.insert(0, str(_PROJECT_ROOT))

from pydantic import BaseModel, Field  # noqa: E402

from hoshino.modules.aichat.aichat.chat_executor import ChatExecutor  # noqa: E402
from hoshino.modules.aichat.aichat.session import Session  # noqa: E402
from hoshino.modules.aichat.aichat.tools.registry import (  # noqa: E402
    _annotation_to_schema,
    _build_schema_from_signature,
    get_injectable_params,
    tool_registry,
)


class TestAnnotationToSchema(unittest.TestCase):
    def test_primitives(self):
        self.assertEqual(_annotation_to_schema(str), {"type": "string"})
        self.assertEqual(_annotation_to_schema(int), {"type": "integer"})
        self.assertEqual(_annotation_to_schema(float), {"type": "number"})
        self.assertEqual(_annotation_to_schema(bool), {"type": "boolean"})

    def test_list_and_dict(self):
        self.assertEqual(
            _annotation_to_schema(List[int]),
            {"type": "array", "items": {"type": "integer"}},
        )
        self.assertEqual(
            _annotation_to_schema(Dict[str, str]),
            {"type": "object", "additionalProperties": {"type": "string"}},
        )

    def test_literal_enum(self):
        self.assertEqual(
            _annotation_to_schema(Literal["a", "b"]),
            {"enum": ["a", "b"]},
        )

    def test_any_freeform(self):
        self.assertEqual(_annotation_to_schema(Any), {})
        self.assertEqual(_annotation_to_schema(None), {})


class Address(BaseModel):
    city: str = Field(description="城市")


class User(BaseModel):
    name: str
    age: int = Field(ge=0, le=150, description="年龄")
    address: Address


class TestPydanticModelSchema(unittest.TestCase):
    def test_nested_model_inlined(self):
        schema = _annotation_to_schema(User)
        self.assertEqual(schema["type"], "object")
        self.assertNotIn("$defs", schema)
        self.assertNotIn("$ref", json.dumps(schema, ensure_ascii=False))
        self.assertEqual(schema["properties"]["address"]["properties"]["city"]["description"], "城市")
        self.assertEqual(schema["properties"]["age"]["minimum"], 0)


class TestBuildSchemaFromSignature(unittest.TestCase):
    def test_required_and_defaults(self):
        async def f(a: str, b: int = 1, c: Optional[str] = None, d: "Session" = None):
            pass

        schema = _build_schema_from_signature(f)
        self.assertEqual(schema["required"], ["a"])
        self.assertEqual(schema["properties"]["b"], {"type": "integer"})
        # 注入参数被排除
        self.assertNotIn("d", schema["properties"])

    def test_pep604_optional(self):
        async def f(a: "str | None"):
            pass

        schema = _build_schema_from_signature(f)
        self.assertEqual(schema["required"], [])
        self.assertEqual(schema["properties"]["a"], {"type": "string"})

    def test_annotated_description(self):
        async def f(a: Annotated[str, Field(description="名称")]):
            pass

        schema = _build_schema_from_signature(f)
        self.assertEqual(schema["properties"]["a"]["description"], "名称")

    def test_docstring_param_docs(self):
        async def f(a: str):
            """
            测试工具

            :param a: 从文档来的描述
            """
            pass

        schema = _build_schema_from_signature(f)
        self.assertEqual(schema["properties"]["a"]["description"], "从文档来的描述")

    def test_annotated_wins_over_docstring(self):
        async def f(a: Annotated[str, Field(description="注解描述")]):
            """
            :param a: 文档描述
            """
            pass

        schema = _build_schema_from_signature(f)
        self.assertEqual(schema["properties"]["a"]["description"], "注解描述")


class TestInjectableParams(unittest.TestCase):
    def test_pep604_injectable(self):
        async def f(session: "Session | None"):
            pass

        self.assertEqual(get_injectable_params(f), {"session": "Session"})

    def test_cache_same_result(self):
        async def f(session: Optional["Session"]):
            pass

        self.assertEqual(get_injectable_params(f), get_injectable_params(f))


class TestRegisterAutoSchema(unittest.TestCase):
    def test_auto_schema_from_registry(self):
        async def __test_auto(name: str, count: int = 1):
            """自动生成的工具"""
            pass

        tool_registry.register(description=None)(__test_auto)
        info = tool_registry.get_tool_info("__test_auto")
        self.assertEqual(info.parameters["required"], ["name"])
        self.assertEqual(info.description, "自动生成的工具")
        self.assertIsNone(info.input_model)


class TestExecutorPydanticModel(unittest.IsolatedAsyncioTestCase):
    async def test_valid_and_invalid_arguments(self):
        class TestInput(BaseModel):
            q: str = Field(description="查询词")
            n: int = Field(default=1, ge=1, le=5)

        @tool_registry.register
        async def __test_model_tool(params: TestInput):
            from hoshino.modules.aichat.aichat.tools.registry import ok
            return ok(f"{params.q}:{params.n}")

        session = Session("schema_exec_1", 1)
        executor = ChatExecutor(session)

        # 合法参数：模型构造成功，函数收到模型实例
        result = await executor._execute_tool_call(
            {"id": "c1", "function": {"name": "__test_model_tool", "arguments": '{"q": "hi", "n": 3}'}},
            context={"session": session},
        )
        parsed = json.loads(result["content"])
        self.assertTrue(parsed["success"])
        self.assertIn("hi:3", parsed["content"])

        # 非法参数：pydantic 校验拦截，不进入函数
        result = await executor._execute_tool_call(
            {"id": "c2", "function": {"name": "__test_model_tool", "arguments": '{"q": "hi", "n": 99}'}},
            context={"session": session},
        )
        parsed = json.loads(result["content"])
        self.assertFalse(parsed["success"])
        self.assertIn("校验失败", parsed["error"])


if __name__ == "__main__":
    unittest.main()
