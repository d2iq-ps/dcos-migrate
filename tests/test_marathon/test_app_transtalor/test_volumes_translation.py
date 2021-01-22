import pytest

from dcos_migrate.plugins.marathon import app_translator

def test_host_path_volumes():
    settings = app_translator.Settings(
        app_translator.ContainerDefaults(
            image=None,
            working_dir=None,
        ),
        imported_k8s_secret_name = "dummy"
    )

    app = {
        "id": "app",
        "container": {
            "docker": {"image": "python"},
            "volumes": [
                {"containerPath": "/rw", "hostPath": "/volumes/rw", "mode": "RW"},
                {"containerPath": "/ro", "hostPath": "/volumes/ro", "mode": "RO"},
                {"containerPath": "/foo", "hostPath": "relative_to_sandbox", "mode": "RO"},
                {"containerPath": "foo", "persistent": {"size": 1024, "type": "root" }, "mode": "RO"},
            ],
        },
    }

    result, warnings = app_translator.translate_app(app, settings)

    template_spec = result['spec']['template']['spec']
    volumes = sorted(template_spec['volumes'], key = lambda v: v['name'])
    assert volumes == [
        {"name": "volume-0", 'hostPath': {"path": "/volumes/rw"}},
        {"name": "volume-1", 'hostPath': {"path": "/volumes/ro"}},
    ]

    mounts = sorted(template_spec['containers'][0]['volumeMounts'], key = lambda v: v['name'])
    assert mounts == [
        {"name": "volume-0", "mountPath": "/rw", "readOnly": False},
        {"name": "volume-1", "mountPath": "/ro", "readOnly": True},
    ]

    # For now, we do not translate volumes with a "hostPath" relative to
    # Mesos sandbox (which typically are a part of a persistent volume setup).
    # Persistent volumes themselves aren't translated either.
    volume_warnings = [w for w in warnings if "Cannot translate a volume" in w]
    assert len(volume_warnings) == 2
    assert any("relative_to_sandbox" in w for w in volume_warnings)
    assert any("persistent" in w for w in volume_warnings)


def test_host_path_volume_with_fetch():
    """
    Tests that emitting a volume for fetch artifacts does not interfere
    with a hostPath volume translation.
    """
    settings = app_translator.Settings(
        app_translator.ContainerDefaults(
            image=None,
            working_dir="/sandbox",
        ),
        imported_k8s_secret_name = "dummy"
    )

    app = {
        "id": "app",
        "container": {
            "docker": {"image": "python"},
            "volumes": [
                {"containerPath": "/ro", "hostPath": "/volumes/ro", "mode": "RO"},
            ],
        },
        "fetch": [{"uri": "http://foobar.baz/0xdeadbeef"}],
    }

    result, warnings = app_translator.translate_app(app, settings)
    template_spec = result['spec']['template']['spec']
    volumes = sorted(template_spec['volumes'], key = lambda v: v['name'])
    assert volumes == [
        {"name": "fetch-artifacts", 'emptyDir': {}},
        {"name": "volume-0", 'hostPath': {"path": "/volumes/ro"}},
    ]

    mounts = sorted(template_spec['containers'][0]['volumeMounts'], key = lambda v: v['name'])
    assert mounts == [
        {"name": "fetch-artifacts", "mountPath": "/sandbox"},
        {"name": "volume-0", "mountPath": "/ro", "readOnly": True},
    ]
