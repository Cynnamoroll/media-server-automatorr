# Media Server Automatorr

An interactive Python script to deploy a complete media server stack using Docker Compose.

## Quick Start

**Prerequisites:** Ubuntu 22.04+, Python 3.8+, Docker & Docker Compose V2

```bash
# Clone and run
git clone https://github.com/Cynnamoroll/media-server-automatorr.git
cd media-server-automatorr
pip install PyYAML
python3 setup.py
```

## What It Does

- **Interactive Setup**: Guides you through service selection and configuration
- **15+ Services**: Jellyfin/Plex, Sonarr/Radarr, qBittorrent, Prowlarr, and more
- **VPN Integration**: Optional Gluetun VPN for secure downloads
- **Auto Configuration**: Generates docker-compose.yml and setup guides
- **User Management**: Creates proper permissions automatically

## Services Available

**Media Servers**: Jellyfin, Plex, Emby  
**Management**: Sonarr, Radarr, Lidarr, Readarr, Mylar3  
**Indexers**: Prowlarr, Jackett  
**Downloads**: qBittorrent, NZBGet, SABnzbd  
**Extras**: Bazarr, Seerr, Tautulli, Homarr, Audiobookshelf  
**Utilities**: Gluetun (VPN), FlareSolverr, Watchtower

## After Setup

```bash
cd /opt/docker/compose  # or your chosen directory
docker compose up -d    # Start services
docker compose ps       # Check status
```

Access your services at `http://your-server-ip:port` - the setup script creates a `SETUP_GUIDE.md` with specific ports and configuration steps.

## Common Issues

**Can't access services**: Check firewall, try server IP instead of localhost  
**Docker permission denied**: `sudo usermod -aG docker $USER` then logout/login  
**VPN not working**: Check `docker logs gluetun` and verify credentials  
***arr apps can't connect**: Use 'gluetun' as qBittorrent host if VPN enabled

## Directory Structure

```
/opt/docker/compose/     # Docker configs
├── docker-compose.yml  
├── .env
└── SETUP_GUIDE.md

/srv/media/              # Media files
├── downloads/
├── movies/
├── tv/
└── music/
```

## Inspiration

Built on concepts from [ezarr](https://github.com/Luctia/ezarr) with focus on user experience and guided setup.
