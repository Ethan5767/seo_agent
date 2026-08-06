# The four tools v3 §5 says are in the container, and nothing else: Python (the
# pipeline), git (checkout/branch/commit), gh (the PR), Claude Code (the writer).
#
# The value here is NOT isolation — it is that the dependencies get declared now
# instead of discovered missing on a new box in six months. No compose, no
# registry, no orchestration until the worker actually moves off your machine.
# Moving hosts is then `scp` + `docker run`.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg nodejs npm \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /engine
COPY . /engine
RUN pip install --no-cache-dir .

# No credentials are baked in. git and gh authenticate with the operator's own
# mounted config; the model authenticates with ANTHROPIC_API_KEY from the
# environment. There is nothing in this image for a leak to take.
#
#   docker build -t seo-agent .
#   docker run --rm -it -v "$PWD/../acme-roofing-site:/client" \
#     -e ANTHROPIC_API_KEY -v "$HOME/.config/gh:/root/.config/gh:ro" \
#     seo-agent wf-site-health --project /client
WORKDIR /client
CMD ["wf-site-plan", "--project", "/client"]
