import pytest
from unittest.mock import MagicMock

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.multimodality.client import MultimodalityClient
from src.l2_interfaces.multimodality.skills.vision import VisionSkills


@pytest.fixture
def mock_os_client():
    client = MagicMock(spec=HostOSClient)
    return client


@pytest.fixture
def vision_client(mock_os_client):
    return MultimodalityClient(host_os_client=mock_os_client)


@pytest.fixture
def vision_skills(vision_client):
    return VisionSkills(client=vision_client)
