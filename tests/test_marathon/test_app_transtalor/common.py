from dcos_migrate.plugins.marathon import app_secrets

class DummyAppSecretMapping(app_secrets.AppSecretMapping):
    def get_reference():
        raise NotImplementedError()
