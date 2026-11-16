#!/bin/bash
# Runs the Juju 2.9 integration suite for 18.04 inside a throwaway LXD VM, so that
# Juju 2.9 and its tooling never touch the host's Juju.
#
# Usage: CHARM_PATH=<.charm file> PRO_CHARM_TEST_TOKEN=<token> run-in-vm.sh
# Optional: PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN, VM_NAME (default: juju29), KEEP_VM=1
set -euo pipefail

: "${CHARM_PATH:?set CHARM_PATH to the built ubuntu-pro_old .charm file}"
: "${PRO_CHARM_TEST_TOKEN:?set PRO_CHARM_TEST_TOKEN}"
VM_NAME="${VM_NAME:-juju29}"
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

if ! lxc info "$VM_NAME" >/dev/null 2>&1; then
    lxc launch ubuntu:22.04 "$VM_NAME" --vm -c limits.cpu=4 -c limits.memory=6GiB \
        -d root,size=30GiB
fi

# The VM agent takes a while to start after launch.
until lxc exec "$VM_NAME" -- true >/dev/null 2>&1; do sleep 5; done
lxc exec "$VM_NAME" -- cloud-init status --wait

# The marker lets a re-run resume after a failed provisioning (e.g. a snap store error).
if ! lxc exec "$VM_NAME" -- test -f /root/.provisioned; then
    lxc exec "$VM_NAME" -- bash -euxc '
        snap install juju --channel=2.9/stable --classic
        snap install charmcraft --classic
        apt-get update && apt-get install -y python3-venv
        python3 -m venv /root/toxenv && /root/toxenv/bin/pip install tox
        lxd init --auto
        juju controllers 2>/dev/null | grep -q spike || juju bootstrap localhost spike
        touch /root/.provisioned
    '
fi

lxc exec "$VM_NAME" -- rm -rf /root/repo
lxc exec "$VM_NAME" -- mkdir -p /root/repo
git -C "$REPO_ROOT" archive HEAD | lxc exec "$VM_NAME" -- tar -x -C /root/repo
lxc file push "$CHARM_PATH" "$VM_NAME/root/repo/charm.charm"

lxc exec "$VM_NAME" --cwd /root/repo \
    --env CHARM_PATH=/root/repo/charm.charm \
    --env PRO_CHARM_TEST_SERIES=bionic \
    --env PRO_CHARM_TEST_TOKEN="$PRO_CHARM_TEST_TOKEN" \
    --env PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN="${PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN:-}" \
    -- /root/toxenv/bin/tox run -e integration-legacy

if [ -z "${KEEP_VM:-}" ]; then
    lxc delete --force "$VM_NAME"
fi
