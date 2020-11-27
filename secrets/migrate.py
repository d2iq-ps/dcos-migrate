import argparse
import json
import os
import re
import sys
from typing import List


def is_valid_dns_label(s: str) -> bool:
    # An alphanumeric (a-z, and 0-9) string, with a maximum length of 63 characters,
    # with the '-' character allowed anywhere except the first or last character
    parts = s.split('-')
    return len(s) <= 63 and all(p.isalnum() for p in parts) and parts[0] and parts[-1]


def is_valid_dns_subdomain(s: str) -> bool:
    # One or more lowercase rfc1035/rfc1123 labels separated by '.' with a maximum length of 253 characters
    return len(s) <= 253 and all(is_valid_dns_label(p) for p in s.split('.'))


_invalid_secret_key = re.compile('[^-._a-zA-Z0-9]')


def clean_key(s: str) -> str:
    # Replace DC/OS folders with dots
    s = s.replace('/', '.')
    # Replace other invalid characters with `_`
    # `folder/sec!ret` becomes `folder.sec_ret`
    return _invalid_secret_key.sub('_', s)


def run(argv: List[str]) -> None:
    parser = argparse.ArgumentParser(description='Migrate secrets from DC/OS to K8s.')
    parser.add_argument('--input', default=None, help='DC/OS secrets file')
    parser.add_argument('--output', default=None, help='K8s secrets file')
    parser.add_argument('--namespace', default='default', help='K8s secrets namespace')
    parser.add_argument('--name', required=True, help='K8s secrets name')

    args = parser.parse_args(argv)
    if not is_valid_dns_subdomain(args.name):
        sys.exit('Invalid K8s secret name')
    if not is_valid_dns_label(args.namespace):
        sys.exit('Invalid K8s secret namespace')

    if args.input is None:
        f = sys.stdin
    else:
        f = open(args.input)
    try:
        dcos_secrets = json.load(f)
    finally:
        if args.input is not None:
            f.close()

    k8s_data = {clean_key(secret['key']): secret['value'] for secret in dcos_secrets}
    k8s_secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "namespace": args.namespace.lower(),
            "name": args.name.lower(),
        },
        "type": "Opaque",
        "data": k8s_data,
    }

    if args.output is None:
        f = sys.stdout
    else:
        # To protect secrets open with read/write permissions only for owner
        f = os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT, 0o600), 'w')
    try:
        json.dump(k8s_secret, f, indent=2)
    finally:
        if args.output is not None:
            f.close()


def main() -> None:
    run(sys.argv)


if __name__ == '__main__':
    main()
