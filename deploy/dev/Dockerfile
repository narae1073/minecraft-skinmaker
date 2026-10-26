# Remote devbox — Python 3.12 + Node 24 + git/gh + sshd.
#
# The Windows Codex GUI adds this container as a remote project over SSH; the
# image does not install the Codex CLI by default. If the GUI turns out to need
# a remote helper, build with INSTALL_CODEX=1.
#
# Build context is deploy/dev only (the project is bind-mounted at /home/dev/workspace),
# so the image never contains the repo, .env, or model files.
FROM python:3.12-slim-bookworm

ARG INSTALL_CODEX=0
ARG CODEX_VERSION=0.164.0
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git openssh-server openssh-client \
        gnupg jq less nano procps ripgrep fd-find rsync tmux unzip \
    && rm -rf /var/lib/apt/lists/*

# Node 24 for the Vite frontend.
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

# No Codex CLI by default: the Windows GUI adds the remote project itself.
# INSTALL_CODEX=1 is an opt-in fallback if the GUI asks for a remote helper.
RUN if [ "$INSTALL_CODEX" = "1" ]; then \
        npm install -g "@openai/codex@${CODEX_VERSION}" \
        && npm cache clean --force; \
    fi

RUN useradd -m -u 1000 -s /bin/bash -p '*' dev \
    && mkdir -p /home/dev/.ssh /etc/ssh/authorized_keys /etc/ssh/host_keys \
    && chown -R dev:dev /home/dev \
    && chmod 700 /home/dev/.ssh /etc/ssh/host_keys \
    && chmod 755 /etc/ssh/authorized_keys

COPY sshd_config /etc/ssh/sshd_config
COPY profile.sh /etc/profile.d/skinmaker.sh
COPY entrypoint.sh /usr/local/bin/devbox-entrypoint
RUN mkdir -p /run/sshd /etc/ssh/host_keys \
    && chmod 700 /etc/ssh/host_keys \
    && chmod 644 /etc/profile.d/skinmaker.sh \
    && chmod +x /usr/local/bin/devbox-entrypoint \
    && printf '%s\n' \
        '[ -f /etc/profile.d/skinmaker.sh ] && . /etc/profile.d/skinmaker.sh' \
        '[ -t 1 ] && [ -d /home/dev/workspace ] && cd /home/dev/workspace' \
        >> /home/dev/.bashrc \
    && chown dev:dev /home/dev/.bashrc \
    && chmod 644 /home/dev/.bashrc

EXPOSE 22

ENTRYPOINT ["/usr/local/bin/devbox-entrypoint"]
