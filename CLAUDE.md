# swf-common-lib

Start from the SWF workspace guide, `../swf-testbed/CLAUDE.md`
(<https://github.com/BNLNPPS/swf-testbed/blob/main/CLAUDE.md>): the
system, the workspace, how to work, production and collaboration. This
file adds what is particular to swf-common-lib, the library shared by the
swf applications and their agents: the agent base class (`BaseAgent`),
logging, the swf-monitor REST client, and the MQ and Rucio clients
(`README.md`).

- A core repository: developed on the current `infra/baseline-vNN`
  branch together with swf-testbed and swf-monitor, released to `main`
  with them.
- Every agent of the testbed and of production runs on this code, so a
  change here is a change to all of them; the agent lifecycle (startup,
  heartbeat, reconnection, shutdown) is documented in swf-testbed
  `docs/agent-management.md`.
- Tests: `./run_tests.sh`.
