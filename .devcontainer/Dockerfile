# Use the same base image as the project
FROM python:3.12-slim

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_DEBUG=True

# Set work directory
RUN mkdir -p /workspaces/RSS-TTS
WORKDIR /workspaces/RSS-TTS

# Install dependencies for development
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    git \
    redis-server \
    ffmpeg \
    procps \
    curl \
    vim \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN (type -p wget >/dev/null || (apt-get update && apt-get install wget -y)) \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    && cat $out | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt update \
    && apt install gh -y

# Install pip and dev tools
RUN pip install --upgrade pip \
    && pip install pre-commit black flake8 mypy isort pytest pytest-django

# Copy and install requirements
COPY requirements.txt requirements-test.txt ./
RUN pip install -r requirements.txt \
    && pip install -r requirements-test.txt

# Create a non-root user with sudo access
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Configure npm for global installs without requiring sudo
USER $USERNAME
RUN mkdir -p /home/$USERNAME/.npm-global \
    && npm config set prefix "/home/$USERNAME/.npm-global" \
    && echo "export PATH=/home/$USERNAME/.npm-global/bin:\$PATH" >> /home/$USERNAME/.bashrc \
    && echo "export PATH=/home/$USERNAME/.npm-global/bin:\$PATH" >> /home/$USERNAME/.profile
