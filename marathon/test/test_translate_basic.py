from ..lib import app_translator
import os
import sys

import pytest

def test_sleep():
    container_defaults = app_translator.Settings(
        app_translator.ContainerDefaults(
            image="busybox",
            working_dir=".",
        ),
        imported_k8s_secret_name = "dummy"
    )

    hello_app = app_translator.load("test/resources/hello.json")[0]
    result, warnings = app_translator.translate_app(hello_app, container_defaults)

    assert(result['kind'] == "Deployment")
    assert(result['metadata']['name'] == "sleep")
    assert(result['metadata']['labels'] == {'app': 'sleep'})
    assert(result['spec']['replicas'] == 10)
    container = result['spec']['template']['spec']['containers'][0]

    assert(container['command'] == ['/bin/sh', '-c', 'sleep 3600'])
    assert(container['image'] == 'busybox')
    assert(container['resources'] == {'requests': {'cpu': 0.01, 'memory': '64Mi'}})
    assert(container['name'] == 'main')


def test_image_in_app_makes_image_default_unnecessary():
    settings = app_translator.Settings(
        app_translator.ContainerDefaults(
            image=None,
            working_dir=None,
        ),
        imported_k8s_secret_name = "dummy"
    )

    app = {"id":"app", "container": {"docker": {"image": "busybox"}}}
    result, _ = app_translator.translate_app(app, settings)
    assert result['spec']['template']['spec']['containers'][0]['image'] == "busybox"


def test_image_should_be_present_somewhere():
    settings = app_translator.Settings(
        app_translator.ContainerDefaults(
            image=None,
            working_dir=None,
        ),
        imported_k8s_secret_name = "dummy"
    )

    app = {"id":"app", "command": "sleep 300"}
    with pytest.raises(app_translator.AdditionalFlagNeeded, match=".*image.*"):
        app_translator.translate_app(app, settings)
