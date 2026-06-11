# ADAM example datasets

This directory contains versioned CSV examples used to train and test ADAM models.

## CSV format

Each file must:

- use UTF-8 encoding;
- contain the exact header `text,label`;
- contain one user request and its intent per row;
- contain at least two distinct intents.

Runtime uploads are stored separately in `core/adam/files` and must not replace
the versioned examples in this directory.
