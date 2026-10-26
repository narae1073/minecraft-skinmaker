#!/bin/sh
set -eu
mkdir -p /run/sshd

# Make the app work without a key even for non-interactive `ssh host cmd`.
# A user-customized file is left alone.
if [ ! -f /home/dev/.ssh/environment ]; then
  printf 'SKINMAKER_TRANSPORT=mock\n' > /home/dev/.ssh/environment
  chown dev:dev /home/dev/.ssh/environment
  chmod 600 /home/dev/.ssh/environment
fi

exec /usr/sbin/sshd -D -e
