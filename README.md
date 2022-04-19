# Ubuntu Advantage charm

## Description

This charm enables Ubuntu Advantage (https://ubuntu.com/advantage) subscriptions.

## Usage

Be sure to replace `<token>` with a valid value from [the Ubuntu Advantage website](https://ubuntu.com/advantage).

    juju deploy ubuntu
    juju deploy ubuntu-advantage --config token=<token>
    juju add-relation ubuntu ubuntu-advantage
