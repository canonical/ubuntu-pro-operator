# Ubuntu Pro Operator

This operator/charm enables Ubuntu Pro (https://ubuntu.com/pro) subscriptions.

It is published under two names: `ubuntu-pro` and `ubuntu-advantage`. The `ubuntu-advantage` name is kept to avoid breaking existing deployments of this charm.

The `ubuntu-advantage` charm has been officially deprecated and will not recieve any updates. All new features and updates will be made to the `ubuntu-pro-operator`.

This charm is maintained by the Ubuntu Pro team within Commercial Systems at Canonical.

## Usage

Be sure to replace `<token>` with a valid value from
[the Ubuntu Pro website](https://ubuntu.com/pro):

```
juju deploy ubuntu
juju deploy ubuntu-advantage --config token=<token>
juju add-relation ubuntu ubuntu-advantage
```

## Development

This charm is developed at https://github.com/canonical/ubuntu-pro-operator.

It is currently released to the `edge` channel manually.

It is published at https://charmhub.io/ubuntu-advantage, and at https://charmhub.io/ubuntu-pro but it is
not publicly findable via search in charmhub.

## Proxy config

By default, this charm will pick up the proxy configuration from the Juju
model. If you want to use a different proxy instead for the units, you can
override that with configs `override-http-proxy` and `override-https-proxy`.

Please note that in all cases, the Ubuntu Pro client will check if these proxy
configs are valid. If it cannot use them (e.g., proxy is not reachable), you
will most likely get a `hook failed: "config-changed"` message. You can check
the causes with `juju debug-log`.
