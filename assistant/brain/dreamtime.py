"""Decide whether now is a good time to run heavier batch jobs (organize,
drift check, health scan) and which ones fit in the window — orchestration
only. This module never spawns anything itself (ALLOWED_IMPORTS bans
subprocess for the whole assistant); the caller outside this layer is
responsible for actually invoking whichever jobs get chosen.
"""
# The 0/1 knapsack engine moved to brain/personal/ with the day-planning
# tools it was built for; dreamtime (the assistant's OWN batch-window
# scheduler, shell-native) still reuses the algorithm. This is the only
# root->personal import in the brain layer and it imports an engine, not
# a personal-surface function.
from .personal.planner import knapsack


def eligible(idle_minutes, on_ac_power, cpu_load_percent, min_idle=5, max_load=30):
    return idle_minutes >= min_idle and on_ac_power and cpu_load_percent <= max_load


def schedule(jobs, budget_min):
    """jobs: [{"id", "minutes", "value"}], value = how much you'd want it run
    now (e.g. staleness of that job's last run). Reuses the 0/1 knapsack
    planner. Returns the chosen job ids, highest-value first.
    """
    chosen, _, _ = knapsack(jobs, budget_min)
    by_id = {j["id"]: j for j in jobs}
    return sorted(chosen, key=lambda jid: -by_id[jid]["value"])
