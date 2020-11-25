
import logging
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError, PIPE, Popen
from typing import List, Optional, Tuple

import cryptography.hazmat.backends
from _pytest.fixtures import SubRequest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dcos_e2e.cluster import Cluster
from dcos_e2e.exceptions import DCOSTimeoutError
from dcos_e2e.node import Node
from dcos_test_utils.enterprise import EnterpriseApiSession, EnterpriseUser


LOGGER = logging.getLogger(__name__)


def wait_for_dcos_ee(
    cluster: Cluster,
    superuser_username: str,
    superuser_password: str,
    request: SubRequest,
    log_dir: Path,
) -> None:
    """
    Helper for ``wait_for_dcos_ee`` that automatically dumps the journal of
    every cluster node if a ``DCOSTimeoutError`` is hit.
    """
    try:
        cluster.wait_for_dcos_ee(
            superuser_username=superuser_username,
            superuser_password=superuser_password,
        )
    except DCOSTimeoutError:
        # Dumping the logs on timeout only works if DC/OS has already started
        # the systemd units that the logs are retrieved from.
        # This does currently not pose a problem since the ``wait_for_dcos_ee``
        # timeout is set to one hour. We expect the systemd units to have
        # started by then.
        dump_cluster_journals(
            cluster=cluster,
            target_dir=log_dir / artifact_dir_format(request.node.name),
        )
        raise


def session_from_cluster(
    cluster: Cluster,
    username: str,
    password: str,
) -> EnterpriseApiSession:
    """
    Return a session connected to the given cluster.
    """
    auth_user = EnterpriseUser(uid=username, password=password)
    scheme = 'https://'
    master = next(iter(cluster.masters))
    dcos_url = scheme + str(master.public_ip_address)
    enterprise_session = EnterpriseApiSession(
        dcos_url=dcos_url,
        masters=[str(n.public_ip_address) for n in cluster.masters],
        slaves=[str(n.public_ip_address) for n in cluster.agents],
        public_slaves=[
            str(n.public_ip_address) for n in cluster.public_agents
        ],
        auth_user=auth_user,
    )
    enterprise_session.set_ca_cert()
    enterprise_session = enterprise_session.get_user_session(auth_user)
    return enterprise_session


def artifact_dir_format(test_name: str) -> str:
    """
    Create a common target test directory name format.
    """
    return test_name + '_' + str(datetime.now().isoformat().split('.')[0])


def dump_cluster_journals(cluster: Cluster, target_dir: Path) -> None:
    """
    Dump logs for each cluster node to the ``target_dir``. Logs are separated into directories per node.
    """
    target_dir.mkdir(parents=True)
    for role, nodes in (
        ('master', cluster.masters),
        ('agent', cluster.agents),
        ('public_agent', cluster.public_agents),
    ):
        for index, node in enumerate(nodes):
            node_str = (
                '{role}-{index}_{private_ip}'
            ).format(
                role=role,
                index=index,
                private_ip=node.private_ip_address,
            )
            node_dir = Path(target_dir) / node_str
            _dump_node_journals(node, node_dir)


def _dump_node_journals(node: Node, node_dir: Path) -> None:
    """
    Dump logs from the given cluster node to the ``node_dir``.

    Dumping the diagnostics bundle is unreliable in case that DC/OS
    components are broken. This is likely if ``wait_for_dcos_ee``
    times out. Instead this dumps the journal for each systemd unit
    started by DC/OS.
    """
    LOGGER.info('Dumping journals from {node}'.format(node=node))
    node_dir.mkdir(parents=True)
    try:
        _dump_stdout_to_file(node, ['journalctl'], node_dir / _log_filename('journal'))
    except CalledProcessError as exc:
        # Continue dumping further journals even if an error occurs.
        LOGGER.warn('Unable to dump journalctl: {exc}'.format(exc=str(exc)))

    for unit in _dcos_systemd_units(node):
        if unit.endswith('.service'):
            name = unit.split('.')[0]
            try:
                _dump_stdout_to_file(
                    node=node,
                    cmd=['journalctl', '-u', unit],
                    file_path=node_dir / _log_filename(name),
                )
            except CalledProcessError as exc:
                # Continue dumping further journals even if an error occurs.
                message = 'Unable to dump {unit} journal: {exc}'.format(
                    unit=unit,
                    exc=str(exc),
                )
                LOGGER.warn(message)


def _dump_stdout_to_file(node: Node, cmd: List[str], file_path: Path) -> None:
    """
    Dump ``stdout`` of the given command to ``file_path``.

    Raises:
        CalledProcessError: If an error occurs when running the given command.
    """
    chunk_size = 2048
    proc = node.popen(args=cmd)
    with open(str(file_path), 'wb') as dumpfile:
        while True:
            chunk = proc.stdout.read(chunk_size)
            if chunk:
                dumpfile.write(chunk)
            else:
                break
    proc.wait()
    if proc.returncode != 0:
        exception = CalledProcessError(
            returncode=proc.returncode,
            cmd=cmd,
            output=bytes(proc.stdout),
            stderr=bytes(proc.stderr),
        )
        message = (
            'Failed to complete "{cmd}": {exception}'
        ).format(
            cmd=cmd,
            exception=exception,
        )
        LOGGER.warn(message)
        raise exception


def dump_host_journal(target_dir: Path, unit: Optional[str] = None) -> None:
    """
    Dumps `journalctl` logs for a given unit (or all units) of the host
    that is running tests.

    This method is useful when debugging tests that run on TeamCity agent and
    are not behaving as expected.

    If unit name is not provided all the logs are dumped.
    """
    target_dir.mkdir(parents=True)
    chunk_size = 2048
    cmd = ['journalctl']
    if not unit:
        file_path = target_dir / _log_filename('journalctl')
    else:
        file_path = target_dir / _log_filename(str(unit))
        cmd.extend(['-u', unit])

    proc = Popen(cmd, stdout=PIPE)
    with open(str(file_path), 'wb') as f:
        while True:
            assert proc.stdout is not None
            chunk = proc.stdout.read(chunk_size)
            if chunk:
                f.write(chunk)
            else:
                break
    proc.wait()
    if proc.returncode != 0:
        exception = CalledProcessError(
            returncode=proc.returncode,
            cmd=cmd,
            output=proc.stdout.read(),
            stderr='' if proc.stderr is None else proc.stderr.read(),
        )
        message = (
            'Failed to complete "{cmd}": {exception}'
        ).format(
            cmd=cmd,
            exception=exception,
        )
        LOGGER.warn(message)
        raise exception


def _dcos_systemd_units(node: Node) -> List[str]:
    """
    Return all systemd services that are started up by DC/OS.
    """
    result = node.run(
        args=[
            'sudo', 'systemctl', 'show', '-p', 'Wants', 'dcos.target', '|',
            'cut', '-d=', '-f2'
        ],
        shell=True,
    )
    systemd_units_string = result.stdout.strip().decode()
    return str(systemd_units_string).split(' ')


def _log_filename(name: str) -> Path:
    """
    Returns a name of the file with `.log` extension.
    """
    return Path(name).with_suffix('.log')


cryptography_default_backend = cryptography.hazmat.backends.default_backend()


def _extract_private_key(keypair: rsa.RSAPrivateKeyWithSerialization) -> str:
    """
    Return the private key as a PEM-encoded string.
    """
    privkey_pem = keypair.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )  # type: bytes
    return privkey_pem.decode('ascii')


def generate_rsa_keypair() -> Tuple[str, str]:
    """
    Generate an RSA keypair with a key size of 2048 bits and an
    exponent of 65537. Serialize the public key in the the
    X.509 SubjectPublicKeyInfo/OpenSSL PEM public key format
    (RFC 5280). Serialize the private key in the PKCS#8 (RFC 3447)
    format.

    Returns:
        (private key, public key) 2-tuple, both unicode
        objects holding the serialized keys.
    """

    keypair = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=cryptography_default_backend,
    )
    private = _extract_private_key(keypair)

    public_key = keypair.public_key()
    pubkey_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public = pubkey_pem.decode('ascii')

    return private, public


def generate_csr(cn: str) -> Tuple[str, str]:
    """
    Generate a private key and a Certificate Signing Request.
    """
    keypair = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=cryptography_default_backend,
    )
    private = _extract_private_key(keypair)

    subject_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'US'),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, 'CA'),
        x509.NameAttribute(NameOID.LOCALITY_NAME, 'San Francisco'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Mesosphere, Inc.'),
        x509.NameAttribute(NameOID.COMMON_NAME, cn)
    ])

    csr = x509.CertificateSigningRequestBuilder().subject_name(
        subject_name
    ).sign(keypair, hashes.SHA256(), cryptography_default_backend)

    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode('ascii')

    return private, csr_pem
