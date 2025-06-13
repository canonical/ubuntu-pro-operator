# ubuntu-pro-operator

This charm enables Ubuntu Pro (https://ubuntu.com/pro) subscriptions.

The Pro-charm is the latest version of the charm supporting Ubuntu Pro, and
replaces the previous `ubuntu-advantage` charm which will not receive further updates.

This charm is maintained by the Ubuntu Pro Client team within the Server team at
Canonical.

## Usage

Be sure to replace `<token>` with a valid value from
[the Ubuntu Pro website](https://ubuntu.com/pro):

    juju deploy ubuntu
    juju deploy ubuntu-advantage --config token=<token>
    juju add-relation ubuntu ubuntu-advantage

## Development

It is currently published at https://charmhub.io/ubuntu-pro, but it is
not promulgated.

## Proxy config

By default, this charm will pick up the proxy configuration from the Juju
model. If you want to use a different proxy instead for the units, you can
override that with configs `override-http-proxy` and `override-https-proxy`.

Please note that in all cases, the Ubuntu Pro client will check if these proxy
configs are valid. If it cannot use them (e.g., proxy is not reachable), you
will most likely get a `hook failed: "config-changed"` message. You can check
the causes with `juju debug-log`.
