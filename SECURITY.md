# Security policy

## Supported versions

Fixes go into the latest version on `main`.

## Reporting a vulnerability

Please don't open a public issue. Report it privately instead: in the
repository, open **Security** and then **Report a vulnerability**, or go to
<https://github.com/PedroSartorello/BraggFlow/security/advisories/new>.

Describe the problem and how to reproduce it. If a file is needed, make it
with synthetic data (`examples/make_synthetic_data.py`); never attach real
experimental data.

## Scope

BraggFlow is meant to run on your own computer:

- the web app listens only on `127.0.0.1`;
- it answers only its own page: a request with another `Host` (a domain
  pointed at 127.0.0.1) or, for uploads and changes, from another site's
  page (`Origin`) is refused;
- it has no login;
- it reads and writes only its data folder.

Exposing it on a network, for example through a proxy, is not supported.
