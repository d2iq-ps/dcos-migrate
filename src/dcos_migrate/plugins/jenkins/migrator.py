from dcos_migrate.system import Migrator


class JenkinsMigrator(Migrator):
    """docstring for JenkinsMigrator."""

    def __init__(self, **kw):
        super(JenkinsMigrator, self).__init__(**kw)
        self.translate = {}
