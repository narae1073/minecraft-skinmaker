# Sourced by /etc/profile for SSH login shells inside the remote devbox.
# Loads the workspace .env and makes the app work without a Gemini key.
if [ -f /workspace/.env ]; then
  set -a
  . /workspace/.env
  set +a
fi
if [ "${SKINMAKER_TRANSPORT:-gemini}" = "gemini" ] && [ -z "${GEMINI_API_KEY:-}" ]; then
  export SKINMAKER_TRANSPORT=mock
fi
export TZ="${TZ:-Asia/Seoul}"
export LANG="${LANG:-C.UTF-8}"
