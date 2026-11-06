"""保护必须在真实出口前拒绝，不能依赖每项测试约定注入 Fake。"""

import socket
import pytest
from creative_os.llm_writer import OpenAICompatibleClient, ModelMessage
from scripts.fake_validation_guard import fake_validation_guard


def test_guard_blocks_real_client_and_network_before_any_connection():
    with fake_validation_guard() as blocked:
        with pytest.raises(RuntimeError, match="real_client_forbidden"):
            OpenAICompatibleClient.from_env()
        client = OpenAICompatibleClient("https://example.invalid", "fake", "fake")
        with pytest.raises(RuntimeError, match="real_client_forbidden"):
            client.complete([ModelMessage("user", "隔离探针")], temperature=0.1, max_tokens=1)
        with pytest.raises(RuntimeError, match="external_network_forbidden"):
            socket.create_connection(("example.invalid", 443))
        with socket.socket() as stream:
            with pytest.raises(RuntimeError, match="external_network_forbidden"):
                stream.connect(("203.0.113.1", 443))
            with pytest.raises(RuntimeError, match="external_network_forbidden"):
                stream.connect_ex(("203.0.113.1", 443))
        assert blocked == ["real_client_or_urlopen", "real_client_or_urlopen", "external_create_connection", "external_connect", "external_connect_ex"]
