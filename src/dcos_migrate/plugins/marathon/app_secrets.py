import abc
import re
from typing import Optional
from collections import namedtuple

import dcos_migrate.utils as utils

from .common import InvalidAppDefinition, AdditionalFlagNeeded

SecretReference = namedtuple("SecretReference", ['secret_name', 'key'])


class AppSecretMapping(abc.ABC):
    """
    Provides a mapping from Marathon app's internal secret names
    to name(s) and keys in the migrated DCOS secret.
    """
    @abc.abstractmethod
    def get_reference(self, app_secret_name: str) -> SecretReference:
        pass


class MonolithicAppSecretMapping(AppSecretMapping):
    """
    A mapping that assumes that all the secrets used by the app were migrated
    as keys of a single K8s secret processed via `utils.dnsify()`.
    """
    def __init__(self, app: dict, imported_k8s_secret_name: Optional[str]):
        self._app_id = app.get('id')
        self._secrets = app.get('secrets', {})
        self._imported_k8s_secret_name = imported_k8s_secret_name

    def get_reference(self, app_secret_name: str) -> SecretReference:
        if self._imported_k8s_secret_name is None:
            raise AdditionalFlagNeeded(
                'The app {} is using secrets; please specify the'
                ' name of the imported DCOS secret and run again'.format(self._app_id))

        try:
            key = self._secrets[app_secret_name]['source']
        except KeyError:
            raise InvalidAppDefinition(
                'No source specified for a secret "{}"'.format(app_secret_name))

        return SecretReference(self._imported_k8s_secret_name, utils.dnsify(key))
