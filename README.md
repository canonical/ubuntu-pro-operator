# Ubuntu Advantage charm

## Description

This charm enables Ubuntu Advantage (https://ubuntu.com/advantage) subscriptions

## Usage

Be sure to replace `<token>` with a valid value from https://ubuntu.com/advantage

    juju deploy cs:ubuntu
    juju deploy cs:~ubuntu-advantage-charmers/ubuntu-advantage --config ubuntu-advantage-token=<token>
    juju add-relation ubuntu ubuntu-advantage

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
