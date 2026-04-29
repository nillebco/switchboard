# Agent instructions for switchboard

## After making code changes

Always rebuild and redeploy the switchboard container before considering a task done:

```bash
docker compose up -d --build switchboard
```

Then verify the container started cleanly (no import or startup errors):

```bash
docker logs switchboard-switchboard-1 2>&1 | tail -20
```

And smoke-test the affected endpoint (example: list groups via Signal):

```bash
curl -s "http://localhost:8018/api/v1/send/groups?transport=signal" \
  -H "X-API-Key: ladonna-mobile-qualpiuvento-2024"
```

## Dependency changes

If you add a new Python dependency, add it to `pyproject.toml` under `[project] dependencies` before rebuilding — the Docker image installs from there.

## Commit and push

Only commit and push once the deployment is tested and working:

```bash
git add <files>
git commit -m "..."
git push
```
