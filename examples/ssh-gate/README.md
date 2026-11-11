# SSH gate pattern

`gate` is a template, not part of the bus. Use it when a remote agent needs to do a few fixed things on your machine (read a status, drop a note) and must not get a shell. See the docstring at the top of `gate` and adapt the verbs.
