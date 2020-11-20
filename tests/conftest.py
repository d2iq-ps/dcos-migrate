import logging
import os
from pathlib import Path
from typing import Any
from typing import Generator

import pytest
from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_ee
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Node, Output
from passlib.hash import sha512_crypt


# Configures logging level to DEBUG
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture(scope='session')
def workspace_dir() -> Path:
    """
    Provides a temporary workspace.
    """
    tmp_dir_path = Path(os.environ['DCOS_E2E_TMP_DIR_PATH'])
    assert tmp_dir_path.exists() and tmp_dir_path.is_dir()

    return tmp_dir_path


@pytest.fixture(scope='session')
def docker_backend(workspace_dir: Path) -> Docker:
    """
    Creates a common Docker backend configuration that works within the pytest
    environment directory.
    """
    return Docker(workspace_dir=workspace_dir)


@pytest.fixture(scope='session')
def artifact_path() -> Path:
    """
    Return the path to an enterprise artifact to test against.
    """
    generate_config_path = Path(os.environ['DCOS_E2E_GENCONF_PATH'])
    return generate_config_path


@pytest.fixture(scope='session')
def license_key_contents() -> str:
    """
    Return the contents of a license file which is valid for the latest version
    of DC/OS.
    """
    return os.environ['DCOS_LICENSE']


@pytest.fixture(scope='session')
def log_dir() -> Path:
    """
    Return the path to a directory which logs should be stored in.
    """
    return Path(os.environ['DCOS_E2E_LOG_DIR'])


@pytest.fixture(scope='session')
def superuser_username() -> str:
    return 'admin'


@pytest.fixture(scope='session')
def superuser_password() -> str:
    return 'password'


@pytest.fixture
def master_node(
    artifact_path: Path,
    docker_backend: Docker,
    license_key_contents: str,
    request: SubRequest,
    log_dir: Path,
    superuser_username: str,
    superuser_password: str,
) -> Generator[Node, None, None]:
    config = {
        'superuser_username': superuser_username,
        'superuser_password_hash': sha512_crypt.hash(superuser_password),
        'security': 'strict',
        'fault_domain_enabled': 'false',
        'license_key_contents': license_key_contents,
    }

    with Cluster(cluster_backend=docker_backend, agents=0, public_agents=0) as cluster:
        cluster.install_dcos_from_path(
            dcos_installer=artifact_path,
            dcos_config={
                **cluster.base_config,
                **config,
            },
            output=Output.LOG_AND_CAPTURE,
            ip_detect_path=docker_backend.ip_detect_path,
        )

        wait_for_dcos_ee(
            cluster=cluster,
            superuser_username=superuser_username,
            superuser_password=superuser_password,
            request=request,
            log_dir=log_dir,
        )

        master = next(iter(cluster.masters))

        yield master
