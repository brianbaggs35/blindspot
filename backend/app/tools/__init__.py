"""Tools: what an agent may run, described as data, and the one safe way to build its command line.

An agent never runs a command. It asks for a tool with a set of values; this package checks the
values against the tool's manifest and builds the argument list, never a shell string. Where a tool
runs (the runner) and whether this agent may use it (the permission policy) are separate steps
that use the result.
"""
