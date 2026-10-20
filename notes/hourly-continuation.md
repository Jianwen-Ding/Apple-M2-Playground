# Local hourly continuation of the AGX goal

Owner requested an hourly continuation task on 2026-10-20. This CLI environment
has no native Scheduled-task tool; the installed Codex CLI's `queue` command
can submit a prompt to the existing thread through the local app-server.
`scripts/agx_hourly_continue.py` installs a local timer using that command.
It queues work into the same conversation, so it does not start another GPU
worker. Model and permission settings are inherited, with no overrides.

The interval is 3600 seconds from installation. A process lock prevents duplicate
timers. Before each enqueue, a read-only query of this installation's goal
database requires the selected goal to remain active. Paused, blocked, limited,
missing and completed states do not enqueue work. The prompt also requires
respecting later stop/pause instructions, hardware safety and recovery state.
Failed recovery leaves further work to host-side diagnosis/documentation.

Runtime configuration, next due time, last result, worker identity, lock and
log live in `/scratch/apple-m2-playground/hourly-continuation`. These files
contain no credentials. The timer requires this host and its Codex service
to remain available; it cannot survive a terminated host or resume a paused
goal. After a host restart it must be installed again. This is a local timer,
not a task registered in the ChatGPT Scheduled interface.

```sh
python3 -B scripts/agx_hourly_continue.py status
python3 -B scripts/agx_hourly_continue.py check
python3 -B scripts/agx_hourly_continue.py stop
# Restore after a host restart, using the intended active thread's actual ID:
python3 -B scripts/agx_hourly_continue.py install --thread THREAD_ID
```

`check` validates the current goal and queue plan without sending a prompt or
starting model/GPU work. Installation verifies the detached worker holds its
lock. Enqueue attempts use an argument vector, no shell, and a 30-second
timeout. Queue failures are logged and retried on the next hourly tick.

Official context: [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
distinguishes web/desktop scheduling from the CLI, which lacks its management
interface. A powered local machine is necessary for local project tasks.
