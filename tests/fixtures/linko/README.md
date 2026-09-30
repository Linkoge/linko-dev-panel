This is a fixed test fixture, not a production copy of the Linko repository.

`catalogue.py`, `mounts.svg`, and the small `wall-L.avif` image (stored here as
`sample.avif`) were copied from the existing Linko checkout at commit
`555141db68d1b723f65b453a08a56cab34daaeff`. The generator
is intentionally unmodified, including its legacy `fcntl` import, so tests
exercise the same Windows adapter used for real checkouts. The catalogue,
product JSON, and small HTML template are deterministic test data.

Tests copy these files into temporary directories. They never write into the
user's Linko checkout or require a sibling checkout to exist.
