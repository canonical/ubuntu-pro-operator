## Building the charm

This charm is built for 4 targets:

- `ubuntu-advantage` for 16.04, 18.04, 20.04, and 22.04
- `ubuntu-advantage` for 24.04
- `ubuntu-pro` for 16.04, 18.04, 20.04, and 22.04
- `ubuntu-pro` for 24.04

These have corresponding directories in the `charms/` directory which include a specific `charmcraft.yaml` file for that target.

The contents of the charm are the same for each target.

The `Makefile` at the top level contains make targets that handle copying the charmcraft.yaml file for a particular build target into place, and building the charm for that target.

To build for all of them, you can run `make all`.

## Running the integration tests

The integration tests require a local juju environment that you can set up by running `juju bootstrap localhost dev-controller`. The juju bootstrap controller will use lxd on your machine and keeps its state separately. If juju's state gets out of sync with the lxd state (e.g. if you use lxd to delete a juju-controlled container), you can run `rm -rf ~/.local/share/juju/` to wipe the juju state before starting over.

You will also need the following environment variables set:

```bash
export PRO_CHARM_BUILD_TARGET="ubuntu-advantage"  # or ubuntu-advantage_noble, ubuntu-pro, ubuntu-pro_noble
export PRO_CHARM_TEST_TOKEN="your-ubuntu-pro-token"
export PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN="your-livepatch-staging-token"
```

Then you can run the integration tests with `tox run -e integration`.

## Uploading to Charmhub

After all 4 charms have been tested and built, you can upload them and release them to the edge channel of their respective charm names. It should look something like this:

```
charmcraft upload ./ubuntu-pro_ubuntu-16.04-amd64_ubuntu-18.04-amd64_ubuntu-20.04-amd64_ubuntu-22.04-amd64.charm --release edge
charmcraft upload ./ubuntu-pro_amd64.charm --release edge
```

Only after you are confident that the charms are working correctly, you can promote them to the stable channel. We generally ask a bug reporter to test that the charm in the edge channel is working correctly and fixes their problem before promoting them to stable.
