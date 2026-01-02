## Recommended Setup Order

1. **Download Clients** (qBittorrent, SABnzbd) - Set up first
2. **Indexers** (Prowlarr or Jackett) - Configure your indexers
3. **Media Managers** (Radarr, Sonarr, etc.) - Connect to download clients
4. **Subtitle Manager** (Bazarr) - Connect to Radarr/Sonarr
5. **Media Server** (Jellyfin or Plex) - Set up libraries
6. **Request Manager** (Jellyseerr/Overseerr) - Connect to media server
7. **Dashboard** (Homarr) - Add all your services

## Automatic Updates

Watchtower automatically updates all containers daily at 5 AM.

## Useful Commands

```bash
# View all container logs
docker compose logs -f

# View specific container logs
docker logs -f &lt;container-name&gt;

# Restart all services
docker compose restart

# Stop all services
docker compose down

# Update all containers manually
docker compose pull &amp;&amp; docker compose up -d

# Check container status
docker compose ps
```
