import argparse
import base64
import json
import os
import requests
import subprocess
import sys
import tempfile
import urllib
import urllib3
import warnings
from typing import Dict, List

DCOS = os.getenv("DCOS_CLI", "dcos")


class DCOSSecretsService:

    def __init__(self, url: str, token: str, trust: str):
        self.url = url + '/secrets/v1'
        self.auth = 'token=' + token
        self.trust = trust
        self.store = 'default'

    def list(self, path: str = '') -> List[str]:
        r = requests.get(
            self.url + '/secret/{store}/{path}?list=true'.format(
                store=urllib.parse.quote(self.store), path=urllib.parse.quote(path)
            ),
            headers={'Authorization': self.auth},
            verify=self.trust,
        )
        r.raise_for_status()
        return r.json()['array']

    def get(self, path: str, key: str) -> Dict[str, str]:
        # There are two types of secrets: text and binary.  Using `Accept: */*`
        # the returned `Content-Type` will be `application/octet-stream` for
        # binary secrets and `application/json` for text secrets.
        #
        # Returns the secret as:
        # {
        #   "path": "...",
        #   "key": "...",
        #   "type": "{text|binary}",
        #   "value": "base64(value)"
        # }
        full_path = (path + '/' + key).strip('/')
        url = self.url + '/secret/{store}/{path}'.format(
            store=urllib.parse.quote(self.store), path=urllib.parse.quote(full_path)
        )
        r = requests.get(
            url,
            headers={'Authorization': self.auth, 'Accept': '*/*'},
            verify=self.trust,
        )
        r.raise_for_status()
        content_type = r.headers['Content-Type']
        if content_type == 'application/octet-stream':
            response = {
                'type': 'binary',
                'value': base64.b64encode(r.content).decode('ascii')
            }
        else:
            assert content_type == 'application/json', content_type
            response = r.json()
            response['type'] = 'text'
            # Always encode the secret as base64, even when it is safe UTF-8 text.
            # This obscures the values to prevent unintentional exposure.
            response['value'] = base64.b64encode(response['value'].encode('utf-8')).decode('ascii')
        # Always add the `path` and `key` values to the JSON response
        response['path'] = path
        response['key'] = key
        return response


def get_dcos_truststore(dcos_url: str) -> str:
    # Download the CA certificate for the cluster to verify subsequent connections. Since we don't
    # yet have the CA certificate, this request cannot be verified (and hence is insecure).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(dcos_url + '/ca/dcos-ca.crt', verify=False)
    r.raise_for_status()
    cert = r.text
    return cert


def get_dcos_token(dcos_cli: str) -> str:
    p = subprocess.run(
        [dcos_cli, 'config', 'show', 'core.dcos_acs_token'],
        stdout=subprocess.PIPE,
        timeout=10 * 60,
        check=True,
        encoding='ascii',
    )
    return p.stdout.strip()


def get_dcos_url(dcos_cli: str) -> str:
    p = subprocess.run(
        [dcos_cli, 'config', 'show', 'core.dcos_url'],
        stdout=subprocess.PIPE,
        timeout=10 * 60,
        check=True,
        encoding='ascii',
    )
    return p.stdout.strip().rstrip('/')


def run(argv: List[str]) -> None:
    parser = argparse.ArgumentParser(description='Backup secrets from DC/OS secrets service.')
    parser.add_argument('--path', default='', help='secrets namespace to export')
    parser.add_argument('--target-file', default=None, help="path of the target file")

    args = parser.parse_args(argv)
    path = args.path

    url = get_dcos_url(DCOS)
    token = get_dcos_token(DCOS)
    trust = get_dcos_truststore(url)

    with tempfile.NamedTemporaryFile('w+', encoding='utf-8') as certf:
        certf.write(trust)
        certf.flush()
        s = DCOSSecretsService(url, token, certf.name)
        secrets = []
        for key in s.list(path):
            secrets.append(s.get(path, key))

        if args.target_file is None:
            f = sys.stdout
        else:
            # To protect secrets open with read/write permissions only for owner
            f = os.fdopen(os.open(args.target_file, os.O_WRONLY | os.O_CREAT, 0o600), 'w')
        try:
            json.dump(secrets, f, indent=2, sort_keys=True)
        finally:
            if args.target_file is not None:
                f.close()


def main() -> None:
    run(sys.argv[1:])


if __name__ == '__main__':
    main()
