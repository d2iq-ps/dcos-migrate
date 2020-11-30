import base64
import json
import stat
import subprocess
from pathlib import Path

import pytest

from _pytest.fixtures import SubRequest
from cluster_helpers import wait_for_dcos_ee
from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.node import Output
from dcos_test_utils.dcos_cli import DcosCli
from passlib.hash import sha512_crypt

from secrets import backup, migrate

PRIVATE_KEY = """
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7zYQ8wdXCQQrj
jxNGIXAMQWYXW7krsT0gkH2jOv1M5kCIbFF9eJoJtj7zSzGBlsIVFzjls73ageqP
zACRxU7P4D/IfEomgyg6E1TayHfVwwGG+4wUBxvvFgaK2WlCpLThLjgoOnMrl3id
TZ4uVqxlhSSzG1+sygx6nZgBtQ2aS0Bdg6RZ2slI+00TR1Hngi/PKBVDkCRWFGH+
OJFUkGNLf4IQEQ4R1V143R5QIVG2eyxKEDbxM1xFimocLaOGomdRV4/FmQgn031T
olrITFwA7vywC/VflvC1Olvcf5iP93krQdqopZ9Ut8EFsFLWF8iiGCc6Dpdj35MJ
c8og4S1VAgMBAAECggEAOxPDbXlsTNc5Hax8W6tZHAHWo7Ju5ZezqvLJEvgThoVH
96JbYCT4D+YMl2wn/qP2GbxcYaXRK1OC/gkmhLSUvj/E0MSIbuUDWoGKR+iYCd52
NIgc4I/78ZH0LOmHezdkzxFDCSSZ5jSX9KPeBqWtRaJEkTMjPa+xjUDV+HOD++z1
BS5bSJY9DLkh2gH2IHk4ypla8z7QP+N1KiKrjyLWuHdyUWvcXZ77ae2rGL8Th6mD
64R189xfUhcXAk/iwc4MZGYFm8mnPwHHfUK/dO8pKURyHcG3FNsfEjssYE7Qnpkz
GzLujbcGDL7Ufq84UVk3hGOe9Zqm7p6rpTBN44hLAQKBgQD6FJgOldDIwIJdinGX
B+k9ODTs7sJGHhSEbQaOUcliq05DFXDH56PbgV48zZ5tJjG2d04jHpw5pkPo3ulG
GKIFe+O61sgp7cJ/FY+BCF/bvn+xYw1pOvA62wCqyvcfUljceqmMKmVyZePFm1D3
EglKKcRfvD6vn/kyuK6pEenhCQKBgQDAP4pTOIvehZ02bKyZ9ifh885um2nJ+C1M
9SI+ypIUpsWGypFmiAdGc1wMpKhKgKC8ZEl1xKdjNmRLFNlpbcr1ny7D7FdvwI94
1yEY1bJPrUFbXdWokn6HMgOq9ysVCdc3ApM371R+WF3AcC/8SvEUGzTXxJ8sGHfh
tUDec+sY7QKBgQCRYHtsrybqLQ8b9alG1TB/iDcsLTf+runaec6/2Ueq9k7OrJ4d
d8lHh5MS4a1hYjywB/cCb379/Gup6jvNpfA6I+Uk7kr6JN9WJWCA8C9ZfQqaQiy/
qaWRcVKX9tll+ebydNQvSU4kDJs2eq28k12XIWSpCrOeQO8Kz1Wpr2I4kQKBgH1N
7P7pMGFNfXbnxmhjhQNFQhvduEooNH6gmD2NE0HaoYyFo9fMedF1h13GRNqqlBm2
1Bqqnt+PqDc3061gHpWRt42EEkmInPsKXUwunRZJuvuuYYCKW2YLN1DL4YzI6Tm1
t/cRS2U+e3zeoqgywId2ZC7uvUCkgh7fYPSdYXLRAoGAewflDOdwWVyhrziFiB05
W/A4iv8qxmexNQ+PzYryrV0dxS9J5cQiXdv327tCHzFwWEIXsrbD0+lMy/ATTDnd
TsDMni+zjg7UxH2k1IHA8XuXaRWhuXNxpZ0WRXy5Fajy7C+UcpucJl/959uWjX+O
LGxI1AyMRRYWlk17of8h83o=
-----END PRIVATE KEY-----
"""


@pytest.fixture(scope='module')
def cli() -> DcosCli:
    return DcosCli.new_cli()


class TestSecrets:
    def test_secrets(
        self,
        artifact_path: Path,
        docker_backend: Docker,
        license_key_contents: str,
        request: SubRequest,
        log_dir: Path,
        superuser_username: str,
        superuser_password: str,
        cli: DcosCli,
        kind_path: Path,
        kubectl_path: Path,
        tmp_path: Path,
    ):
        config = {
            'superuser_username': superuser_username,
            'superuser_password_hash': sha512_crypt.hash(superuser_password),
            'security': 'strict',
            'fault_domain_enabled': 'false',
            'license_key_contents': license_key_contents,
        }

        with Cluster(cluster_backend=docker_backend, agents=0, public_agents=0) as cluster:
            master = next(iter(cluster.masters))
            c = {
                **cluster.base_config,
                **config,
            }
            print('X1c', c)
            cluster.install_dcos_from_path(
                dcos_installer=artifact_path,
                dcos_config=c,
                output=Output.LOG_AND_CAPTURE,
                ip_detect_path=docker_backend.ip_detect_path,
            )

            done = False
            while not done:
                try:
                    wait_for_dcos_ee(
                        cluster=cluster,
                        superuser_username=superuser_username,
                        superuser_password=superuser_password,
                        request=request,
                        log_dir=log_dir,
                    )
                    done = True
                except json.decoder.JSONDecodeError:
                    # File is not written atomically, so JSON parse can fail
                    config_result = master.run(
                        args=['cat', '/opt/mesosphere/etc/bootstrap-config.json'],
                    )
                    print('X2', config_result.stdout.decode())
                    wait_for_dcos_ee(
                        cluster=cluster,
                        superuser_username=superuser_username,
                        superuser_password=superuser_password,
                        request=request,
                        log_dir=log_dir,
                    )

            master_url = 'https://' + str(master.public_ip_address)

            cli.setup_enterprise(master_url, superuser_username, superuser_password)

            # key1: value1
            value1 = 'value1'
            cli.exec_command(
                ['dcos', 'security', 'secrets', 'create', '--value', value1, 'key1']
            )

            # folder/key2: value2
            value2 = 'value2\n'
            secret2 = tmp_path / 'file2'
            secret2.write_text(value2)
            cli.exec_command([
                'dcos',
                'security',
                'secrets',
                'create',
                '--text-file',
                str(secret2),
                'folder/key2'
            ])

            # folder/key3: value3 (binary)
            value3 = b'value\x85\xff3'
            secret3 = tmp_path / 'file3'
            secret3.write_bytes(value3)
            cli.exec_command([
                'dcos', 'security', 'secrets', 'create', '--file', str(secret3), 'folder/key3'
            ])

            # folder/sub/key4: sa-account-details
            secret4 = tmp_path / 'file.pem'
            secret4.write_text(PRIVATE_KEY)
            cli.exec_command([
                'dcos',
                'security',
                'secrets',
                'create-sa-secret',
                str(secret4),
                'dcos-service',
                'folder/sub/key4'
            ])

            url = backup.get_dcos_url(cli.path)
            token = backup.get_dcos_token(cli.path)
            trust = backup.get_dcos_truststore(url)

            s = backup.DCOSSecretsService(url, token, trust)

            # `list` returns all keys below the folder
            response = s.list('')
            assert response == ['folder/key2', 'folder/key3', 'folder/sub/key4', 'key1']

            response = s.list('folder')
            assert response == ['key2', 'key3', 'sub/key4']

            response = s.list('folder/sub')
            assert response == ['key4']

            response = s.list('fold')
            assert response == []

            response = s.list('not/a/folder')
            assert response == []

            response = s.get('', 'key1')
            assert response['path'] == ''
            assert response['key'] == 'key1'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value1

            response = s.get('', 'folder/key2')
            assert response['path'] == ''
            assert response['key'] == 'folder/key2'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value2

            response = s.get('', 'folder/key3')
            assert response['path'] == ''
            assert response['key'] == 'folder/key3'
            assert response['type'] == 'binary'
            assert base64.b64decode(response['value']) == value3

            response = s.get('', 'folder/sub/key4')
            assert response['path'] == ''
            assert response['key'] == 'folder/sub/key4'
            assert response['type'] == 'text'
            assert json.loads(base64.b64decode(response['value'])) == {
                "login_endpoint": "https://leader.mesos/acs/api/v1/auth/login",
                "private_key": PRIVATE_KEY,
                "scheme": "RS256",
                "uid": "dcos-service"
            }

            response = s.get('folder', 'key2')
            assert response['path'] == 'folder'
            assert response['key'] == 'key2'
            assert response['type'] == 'text'
            assert base64.b64decode(response['value']).decode('utf-8') == value2

            response = s.get('folder', 'key3')
            assert response['path'] == 'folder'
            assert response['key'] == 'key3'
            assert response['type'] == 'binary'
            assert base64.b64decode(response['value']) == value3

            response = s.get('folder', 'sub/key4')
            assert response['path'] == 'folder'
            assert response['key'] == 'sub/key4'
            assert response['type'] == 'text'
            assert json.loads(base64.b64decode(response['value'])) == {
                "login_endpoint": "https://leader.mesos/acs/api/v1/auth/login",
                "private_key": PRIVATE_KEY,
                "scheme": "RS256",
                "uid": "dcos-service"
            }

            response = s.get('folder/sub', 'key4')
            assert response['path'] == 'folder/sub'
            assert response['key'] == 'key4'
            assert response['type'] == 'text'
            assert json.loads(base64.b64decode(response['value'])) == {
                "login_endpoint": "https://leader.mesos/acs/api/v1/auth/login",
                "private_key": PRIVATE_KEY,
                "scheme": "RS256",
                "uid": "dcos-service"
            }

            dcosfile1 = tmp_path / 'output-1'
            backup.run(['--target-file', str(dcosfile1)])
            assert stat.S_IMODE(dcosfile1.stat().st_mode) == 0o600
            with dcosfile1.open() as f:
                response = json.load(f)
            keys = set(s['key'] for s in response)
            assert keys == {'key1', 'folder/key2', 'folder/key3', 'folder/sub/key4'}

            dcosfile2 = tmp_path / 'output-2'
            backup.run(['--path', 'folder', '--target-file', str(dcosfile2)])
            assert stat.S_IMODE(dcosfile2.stat().st_mode) == 0o600
            with dcosfile2.open() as f:
                response = json.load(f)
            keys = set(s['key'] for s in response)
            assert keys == {'key2', 'key3', 'sub/key4'}

            dcosfile3 = tmp_path / 'output-3'
            backup.run(['--path', 'folder/sub', '--target-file', str(dcosfile3)])
            assert stat.S_IMODE(dcosfile3.stat().st_mode) == 0o600
            with dcosfile3.open() as f:
                response = json.load(f)
            keys = set(s['key'] for s in response)
            assert keys == {'key4'}

        k8s_secret_name = 'mysecrets'
        k8sfile = tmp_path / 'output-1k'
        migrate.run([
            '--input', str(dcosfile1), '--output', str(k8sfile), '--name', k8s_secret_name
        ])
        assert stat.S_IMODE(k8sfile.stat().st_mode) == 0o600
        with k8sfile.open() as f:
            response = json.load(f)
        keys = response['data'].keys()
        assert keys == {'key1', 'folder.key2', 'folder.key3', 'folder.sub.key4'}

        kubeconfig_path = tmp_path / 'kubeconfig'
        subprocess.run([str(kind_path), 'create', 'cluster', '--kubeconfig', str(kubeconfig_path)])
        try:
            p = subprocess.run(
                [
                    str(kubectl_path),
                    '--kubeconfig',
                    str(kubeconfig_path),
                    '--context',
                    'kind-kind',
                    'apply',
                    '--filename',
                    str(k8sfile)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True
            )
            print('apply:', p.stdout)

            p = subprocess.run(
                [
                    str(kubectl_path),
                    '--kubeconfig',
                    str(kubeconfig_path),
                    '--context',
                    'kind-kind',
                    'get',
                    'secret',
                    k8s_secret_name,
                    '-o',
                    'jsonpath={.data.key1}'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True
            )
            assert base64.b64decode(p.stdout.decode('ascii')).decode('utf-8') == value1
        finally:
            subprocess.run([
                str(kind_path), 'delete', 'cluster', '--kubeconfig', str(kubeconfig_path)
            ])
