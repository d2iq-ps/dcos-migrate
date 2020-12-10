#/bin/sh
set -euo pipefail

PARALLEL_DOWNLOADS=10
TARGET_DIR="./metronome-jobs"

function ask_confirm() {
  read -p "Proceed? [Y/n] " -n 1 -r;
  if ! [[ -z "$REPLY" || $REPLY =~ ^[Yy]$ ]]; then exit 0; fi
}

function downloadAll() {
  dcos job list --json \
    | ./get_ids.py \
    | xargs -P$PARALLEL_DOWNLOADS -L1 -I ID sh -c \
            "dcos job show ID > $TARGET_DIR/ID.json";
  echo "Downloaded to $TARGET_DIR"
}

function prepare() {
  if [ -z "$(which dcos)" ]; then echo "ERROR: Please install dcos-cli."; exit 1; fi

  mkdir -p ./metronome-jobs;

  CLUSTER_URL=`dcos config show | grep "core.dcos_url" | cut -f2 -d' '`
  echo "About to download all job specs from $CLUSTER_URL. This may take a while."
  ask_confirm
}

prepare
downloadAll
