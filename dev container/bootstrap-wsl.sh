#!/usr/bin/env bash
set -euo pipefail

echo "== System information =="

. /etc/os-release

echo "Distribution: $PRETTY_NAME"
echo "User:         $USER"
echo

if [[ "${VERSION_ID}" != "24.04" ]]; then
    echo "WARNING: This bootstrap is intended for Ubuntu 24.04 LTS."
    echo "Detected: $PRETTY_NAME"
    echo
fi

echo
echo "apt update, base packages..."

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo apt-get install -y \
    curl \
    git \
    gnupg \
    jq \
    wget

echo
echo "Docker..."

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL \
    https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc

sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker
sudo systemctl --no-pager --full status docker || true

if getent group docker >/dev/null 2>&1; then
    if ! getent group docker | grep -qw "$USER"; then
        sudo usermod -aG docker "$USER"
        echo "Added $USER to docker group."
    else
        echo "$USER is already a member of docker group."
    fi
else
    echo "ERROR: docker group does not exist."
    exit 1
fi

echo
echo "PowerShell 7..."

. /etc/os-release
MS_DEB="/tmp/packages-microsoft-prod.deb"
wget -q \
    "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" \
    -O "$MS_DEB"

sudo dpkg -i "$MS_DEB"
rm -f "$MS_DEB"

sudo apt-get update
sudo apt-get install -y powershell

echo
echo "== Installed versions =="

git --version
docker --version
docker compose version
docker buildx version
pwsh -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion'



echo "Git config..."

CURRENT_GIT_NAME="$(git config --global user.name || true)"
CURRENT_GIT_EMAIL="$(git config --global user.email || true)"

read -r -p "Git user.name [${CURRENT_GIT_NAME}]: " GIT_NAME
GIT_NAME="${GIT_NAME:-$CURRENT_GIT_NAME}"

read -r -p "Git user.email [${CURRENT_GIT_EMAIL}]: " GIT_EMAIL
GIT_EMAIL="${GIT_EMAIL:-$CURRENT_GIT_EMAIL}"

if [[ -z "$GIT_NAME" ]]; then
    echo "ERROR: Git user.name must not be empty."
    exit 1
fi

if [[ -z "$GIT_EMAIL" ]]; then
    echo "ERROR: Git user.email must not be empty."
    exit 1
fi

git config --global user.name "$GIT_NAME"
git config --global user.email "$GIT_EMAIL"

echo
echo "Git configuration:"
echo "  user.name  = $(git config --global user.name)"
echo "  user.email = $(git config --global user.email)"

mkdir -p "$HOME/workspaces"

echo "============================================"
echo "WSL bootstrap complete."
echo
echo "Docker group membership requires a new login session."
echo
echo "From Windows PowerShell run:"
echo
echo "    wsl --shutdown"
echo
echo "Then reopen Ubuntu."
echo
echo "After reopening, verify:"
echo
echo "    id"
echo "    docker version"
echo "    docker run --rm hello-world"
echo "    docker compose version"
echo "    docker buildx version"
echo "    pwsh"
echo "============================================"