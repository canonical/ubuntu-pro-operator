# charm-ubuntu-advantage

This charm enables Ubuntu Pro (https://ubuntu.com/pro) subscriptions.

Despite the rename of Ubuntu Advantage to Ubuntu Pro, the "ubuntu-advantage"
name remains to avoid breaking  existing deployments of this charm.

This charm is maintained by the Ubuntu Pro team within Commercial Systems at
Canonical.

## Usage

Be sure to replace `<token>` with a valid value from
[the Ubuntu Pro website](https://ubuntu.com/pro):

    juju deploy ubuntu
    juju deploy ubuntu-advantage --config token=<token>
    juju add-relation ubuntu ubuntu-advantage

## Development

This charm is developed at https://code.launchpad.net/charm-ubuntu-advantage.

It is released to the `edge` channel via a recipe:
https://launchpad.net/~ubuntu-advantage-charmers/charm-ubuntu-advantage/+charm/ubuntu-advantage.

It is currently published at https://charmhub.io/ubuntu-advantage, but it is
not promulgated.

In the past, it was also published as https://charmhub.io/ubuntu-pro (also
not promulgated), but that was discontinued until proper support for charm
renames is introduced.
