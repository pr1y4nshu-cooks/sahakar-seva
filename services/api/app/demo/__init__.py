"""Synthetic judge-demo dataset (seeder + verifier). See docs/audits/JUDGE_DEMO_RUNBOOK.md.

Everything is created through the normal application services so quotes, ledger entries and hash-chained
events are genuine; the only synthetic parts are the people, places' sample details and the fact that a seed
script (not a human) triggered the acceptances. Rows are registered in ``demo_seed_records``.
"""
