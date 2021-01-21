#!/usr/bin/env groovy

@Library("sec_ci_libs@v2-latest") _

def aws_id = string(credentialsId: "1ddc25d8-0873-4b6f-949a-ae803b074e7a", variable: "AWS_ACCESS_KEY_ID")
def aws_key = string(credentialsId: "875cfce9-90ca-4174-8720-816b4cb7f10f", variable: "AWS_SECRET_ACCESS_KEY")

pipeline {
  agent none
  environment {
    DCOS_LICENSE = credentials('8667643a-6ad9-426e-b761-27b4226983ea')
    DCOS_EE_URL = credentials('0b513aad-e0e0-4a82-95f4-309a80a02ff9')
  }
  stages {
    stage("Unit Test") {
      parallel {
        stage("Marathon") {
          agent {
            dockerfile true
          }
          steps {
            // don't know why yet, but the runtime on CI does some magic with virtualenvs and as a quickfix we put a seemingly redundant `pipenv install` here.
            sh 'pipenv install && cd marathon && pipenv run pytest'
          }
        }
        stage("Metronome") {
          agent {
            dockerfile true
          }
          steps {
            // don't know why yet, but the runtime on CI does some magic with virtualenvs and as a quickfix we put a seemingly redundant `pipenv install` here.
            sh 'pipenv install && pipenv run pytest --doctest-modules metronome'
          }
        }
      }
    }

    stage("Integration Test") {
      agent {
        label "mesos-ec2-debian-9"
      }
      steps {
        sh 'sudo apt-get update'
        sh 'sudo apt-get install -y python3-dev python3-venv python3-wheel'
        sh 'curl --output tests/dcos_generate_config.ee.sh ${DCOS_EE_URL}'
        sh 'tests/run-tests.sh -v'
      }
    }
  }
}
