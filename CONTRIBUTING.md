## Building the charm

This charm is built for 4 targets:

- `ubuntu-advantage` for 16.04, 18.04, 20.04, and 22.04 (`charms/ubuntu-advantage`)
- `ubuntu-advantage` for 24.04 (`charms/ubuntu-advantage_noble`)
- `ubuntu-pro` for 16.04, 18.04, 20.04, and 22.04 (`charms/ubuntu-pro_old`)
- `ubuntu-pro` for 24.04 and 26.04 (`charms/ubuntu-pro`)

These have corresponding directories in the `charms/` directory which include a specific `charmcraft.yaml` file for that target.

The contents of the charm are the same for each target.

The `Makefile` at the top level contains make targets that handle copying the charmcraft.yaml file for a particular build target into place, and building the charm for that target.

The `ubuntu-pro` target uses a single multi-base `charmcraft.yaml` that covers both 24.04 and 26.04, so it is built with charmcraft 4.x and one `charmcraft pack` produces one `.charm` file per base. The 16.04–22.04 targets use the older `bases:` format and are built with charmcraft 3.x.

To build the `ubuntu-pro` charm, run `make ubuntu-pro`. To build any other target, run `make <target>`.

Make sure the right charmcraft is installed first: `make ubuntu-pro` requires charmcraft 4.x, while the 16.04–22.04 targets require charmcraft 3.x. You can install the matching channel with `sudo snap install charmcraft --classic --channel=4.x/stable` (or `--channel=3.x/stable`).

## Running the integration tests

The integration tests require a local juju environment that you can set up by running `juju bootstrap localhost dev-controller`. The juju bootstrap controller will use lxd on your machine and keeps its state separately. If juju's state gets out of sync with the lxd state (e.g. if you use lxd to delete a juju-controlled container), you can run `rm -rf ~/.local/share/juju/` to wipe the juju state before starting over.

You will also need the following environment variables set:

```bash
export PRO_CHARM_BUILD_TARGET="ubuntu-pro"  # or ubuntu-pro_old, ubuntu-advantage, ubuntu-advantage_noble
export PRO_CHARM_TEST_BASE="ubuntu@24.04"   # a base the build target supports
export PRO_CHARM_TEST_TOKEN="your-ubuntu-pro-token"
export PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN="your-livepatch-staging-token"  # optional
```

Then you can run the integration tests with `tox run -e integration`. Without `PRO_CHARM_TEST_LIVEPATCH_STAGING_TOKEN`, the test that enables Livepatch against the staging server is skipped.

The tests build the charm for `PRO_CHARM_BUILD_TARGET` and deploy it, with the `ubuntu` principal, on `PRO_CHARM_TEST_BASE`.

### Integration tests on pull requests

You don't need the tokens to contribute: the integration tests also run on every pull request, against `ubuntu-pro` on 24.04 and 26.04 and `ubuntu-pro_old` on 20.04 and 22.04. Because they use real Ubuntu Pro tokens, they start only after a maintainer has reviewed your changes, so the check shows as waiting until then.

16.04 and 18.04 are not tested, because Juju 3 cannot deploy charms on them. If your change affects those releases, say how you tested it in the pull request.

## Uploading to Charmhub

After the charms have been tested and built, you can upload them and release them to the edge channel of their respective charm names.

The `ubuntu-pro` target (24.04 and 26.04) produces one `.charm` file per base, so upload each of them. It should look something like this:

```
charmcraft upload ./ubuntu-pro_ubuntu-24.04-amd64.charm --release edge
charmcraft upload ./ubuntu-pro_ubuntu-26.04-amd64.charm --release edge
```

The 16.04–22.04 targets produce a single multi-base artifact that you can upload directly:

```
charmcraft upload ./ubuntu-pro_ubuntu-16.04-amd64_ubuntu-18.04-amd64_ubuntu-20.04-amd64_ubuntu-22.04-amd64.charm --release edge
```

Only after you are confident that the charms are working correctly, you can promote them to the stable channel. We generally ask a bug reporter to test that the charm in the edge channel is working correctly and fixes their problem before promoting them to stable.
