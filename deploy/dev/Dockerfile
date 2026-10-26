# Codex devbox — Python 3.12 + Node 24 + Codex CLI + sshd.
#
# Build context is deploy/dev only (the project is bind-mounted at /workspace),
# so the image never contains the repo, .env, or model files.
FROM python:3.12-slim-bookworm

ARG CODEX_VERSION=0.164.0
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git openssh-server openssh-client \
        gnupg jq less nano procps ripgrep fd-find tmux unzip \
    && rm -rf /var/lib/apt/lists/*

# Node 24 (Codex CLI and the Vite frontend).
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI for PRs from inside the container.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Codex CLI. Pinned so the devbox is reproducible; bump deliberately.
RUN npm install -g "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

RUN useradd -m -u 1000 -s /bin/bash -p '*' dev \
    && mkdir -p /home/dev/.ssh /etc/ssh/authorized_keys \
    && chown -R dev:dev /home/dev \
    && chmod 700 /home/dev/.ssh \
    && chmod 755 /etc/ssh/authorized_keys

COPY sshd_config /etc/ssh/sshd_config
COPY profile.sh /etc/profile.d/skinmaker.sh
COPY entrypoint.sh /usr/local/bin/devbox-entrypoint
RUN mkdir -p /run/sshd \
    && chmod 644 /etc/profile.d/skinmaker.sh \
    && chmod +x /usr/local/bin/devbox-entrypoint \
    && printf '%s\n' \
        '[ -f /etc/profile.d/skinmaker.sh ] && . /etc/profile.d/skinmaker.sh' \
        '[ -t 1 ] && [ -d /workspace ] && cd /workspace' \
        >> /home/dev/.bashrc \
    && chown dev:dev /home/dev/.bashrc \
    && chmod 644 /home/dev/.bashrc \
    && ssh-keygen -A \
    && sshd -t

EXPOSE 22

ENTRYPOINT ["/usr/local/bin/devbox-entrypoint"]
