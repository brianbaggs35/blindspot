"""The agent runtime: a mission that works through a pentest's checklist.

The orchestrator is ordinary code that reads and writes the mission's rows in the database, so a
mission survives a restart and every rule that matters (the scope, the permission policy, the
budgets, the kill switch) is decided by code. The models are workers: each one is asked for one
typed answer at a time and has no way to change those rules.
"""
