#!/bin/sh
set -eu
mkdir -p /run/sshd /etc/ssh/host_keys
chmod 700 /etc/ssh/host_keys

# Persist host keys in the skinmaker-codex-ssh volume so image rebuilds do not
# change the SSH fingerprint.
if [ ! -s /etc/ssh/host_keys/ssh_host_ed25519_key ]; then
  ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/host_keys/ssh_host_ed25519_key
fi
if [ ! -s /etc/ssh/host_keys/ssh_host_rsa_key ]; then
  ssh-keygen -q -t rsa -b 3072 -N '' -f /etc/ssh/host_keys/ssh_host_rsa_key
fi
chmod 600 /etc/ssh/host_keys/ssh_host_ed25519_key /etc/ssh/host_keys/ssh_host_rsa_key

sshd -t

# Make the app work without a key even for non-interactive `ssh host cmd`.
# A user-customized file is left alone.
if [ ! -f /home/dev/.ssh/environment ]; then
  printf 'SKINMAKER_TRANSPORT=mock\n' > /home/dev/.ssh/environment
  chown dev:dev /home/dev/.ssh/environment
  chmod 600 /home/dev/.ssh/environment
fi

exec /usr/sbin/sshd -D -e
