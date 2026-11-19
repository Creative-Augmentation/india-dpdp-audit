# Expected rubric: Firebase deletion

- Identify that the supplied code/configuration does not establish deletion of descendants, Storage, backups or downstream copies. Treat unprovided operational/deployment evidence as unknown; do not assert that data definitely survives all other processes.
- Explain Auth deletion and document TTL do not prove complete recursive erasure; request mapped configuration and synthetic deletion verification including holds and exceptions.
- Do not classify the client API key placeholder alone as a secret leak or attempt access to a live project.
