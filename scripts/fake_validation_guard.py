"""验收进程默认禁用真实模型，网络只允许本机 HTTP 测试服务。"""

from contextlib import contextmanager
import ipaddress
import socket
from unittest.mock import patch


def loopback_address(address):
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@contextmanager
def fake_validation_guard():
    blocked = []
    original_create = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def forbid_client(*args, **kwargs):
        blocked.append("real_client_or_urlopen")
        raise RuntimeError("fake_validation_real_client_forbidden")

    def create_connection(address, *args, **kwargs):
        if not loopback_address(address):
            blocked.append("external_create_connection")
            raise RuntimeError("fake_validation_external_network_forbidden")
        return original_create(address, *args, **kwargs)

    def connect(stream, address):
        if not loopback_address(address):
            blocked.append("external_connect")
            raise RuntimeError("fake_validation_external_network_forbidden")
        return original_connect(stream, address)

    def connect_ex(stream, address):
        if not loopback_address(address):
            blocked.append("external_connect_ex")
            raise RuntimeError("fake_validation_external_network_forbidden")
        return original_connect_ex(stream, address)

    with patch("creative_os.agent_runtime.OpenAICompatibleClient.from_env", side_effect=forbid_client), \
         patch("urllib.request.urlopen", side_effect=forbid_client), \
         patch("socket.create_connection", side_effect=create_connection), \
         patch.object(socket.socket, "connect", connect), patch.object(socket.socket, "connect_ex", connect_ex):
        yield blocked
