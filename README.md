# Media Server Setup Script

A user-friendly, interactive Python script to deploy a complete media server stack using Docker.

Inspired by the [ezarr project](https://github.com/Luctia/ezarr) but written from scratch with a focus on user experience and guided setup.

## Features

- **Interactive Setup**: Step-by-step prompts guide you through the entire process
- **Service Selection**: Choose from 15+ services organized by category
- **Automatic User Management**: Creates dedicated users with proper permissions
- **Docker Compose Generation**: Automatically generates optimized configuration
- **Setup Guide**: Creates both terminal walkthrough and markdown documentation
- **Hardware Agnostic**: Works with any hardware configuration

## Prerequisites

- Ubuntu Server 22.04+ (or similar Debian-based distribution)
- Python 3.8+
- Docker and Docker Compose V2
  - Please ensure you follow the [Docker post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/) or the script will not work
- sudo privileges

## Quick Start

1. Clone or download this repository
2. Run the setup script:
   ```bash
   python3 setup.py
   ```

3. Follow the interactive prompts

## Supported Services

### Media Servers

  - **Jellyfin** - Free and open-source media server
  - **Plex** - Feature-rich media server (some features require Plex Pass)
  - **Emby** - Personal media server with live TV support

### *Arr Suite (Media Management)

  - **Sonarr** - TV show collection manager
  - **Radarr** - Movie collection manager
  - **Lidarr** - Music collection manager
  - **Readarr** - Book/audiobook collection manager
  - **Mylar3** - Comic book collection manager

### Indexers

  - **Prowlarr** - Unified indexer manager for all *arr apps
  - **Jackett** - Alternative indexer proxy

### Download Clients

  - **qBittorrent** - Torrent download client

### Companion Apps

  - **Bazarr** - Automatic subtitle downloader
  - **Seerr** - Request management for Plex and Jellyfin
  - **Tautulli** - Plex monitoring and statistics
  - **Audiobookshelf** - Audiobook and podcast server

### Dashboards & Utilities

  - **Homarr** - Customizable dashboard for all services
  - **FlareSolverr** - Cloudflare bypass proxy for indexers
  
### VPN Tunneling

  - **Gluetun** - Lightweight VPN client to tunnel docker containers
    - Please see [the setup guide](https://github.com/qdm12/gluetun-wiki?tab=readme-ov-file) for usage and modify `./templates/docker-services.yaml` directly before running `setup.py`
  
### Usenet

  - **NZBGet** - High-performance usenet download client
  - **SabNZBd** - Easy to use usenet download client

## Directory Structure

After setup, your directories will be organized as follows:

```plaintext
/opt/docker/              # (or your chosen Docker directory)
├── compose/
│   ├── docker-compose.yml
│   ├── .env
│   └── SETUP_GUIDE.md
├── sonarr/config/
├── radarr/config/
├── jellyfin/config/
└── ... (other services)

/srv/media/               # (or your chosen media directory)
├── downloads/
│   ├── incomplete/
│   └── complete/
├── movies/
├── tv/
├── music/
├── books/
└── comics/
```

## Post-Installation

After running the setup script:

  - Start your services: docker compose up -d
  - Follow the generated SETUP_GUIDE.md for service configuration
  - Configure each service through its web interface

Useful Commands

```Bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f

# Update all containers
docker compose pull
docker compose up -d

# Check status
docker compose ps
```

## Automatic Updates

The setup includes **Watchtower**, which automatically updates your containers daily.

# Troubleshooting

## Permission Issues

```Bash

sudo chown -R $(id -u):$(id -g) /path/to/docker/dir
sudo chown -R $(id -u):$(id -g) /path/to/media/dir
```

Docker Permission Denied

```Bash
sudo usermod -aG docker $USER
newgrp docker
```

## Container Won't Start
```Bash

docker compose logs container-name
```

# Acknowledgments

  - Inspired by [ezarr](https://github.com/Luctia/ezarr)
  - [TRaSH Guides](https://trash-guides.info/) for best practices
  - The *arr community for excellent documentation
