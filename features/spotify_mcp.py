"""
Feature: Spotify MCP Controller
Description: High-fidelity Spotify playback, search, queue, and playlist manager powered by Spotify MCP Server.
Triggers: play on spotify, play song on spotify, pause spotify, resume spotify, skip song on spotify, next song on spotify, spotify volume, what song is playing, now playing on spotify, spotify playlists
"""

from typing import Any, Dict
from actions.spotify_controller import spotify_mcp_controller, is_spotify_configured

FEATURE_METADATA = {
    "name": "spotify_mcp",
    "aliases": ["spotify", "spotify_player", "spotify_controller", "spotify_music"],
    "description": (
        "Controls official Spotify playback, searches songs/artists/albums, manages queue, "
        "adjusts volume, and checks now-playing status via Spotify MCP Server."
    ),
    "triggers": [
        "play on spotify",
        "play music on spotify",
        "play song on spotify",
        "play track on spotify",
        "pause spotify",
        "resume spotify",
        "skip song on spotify",
        "next song on spotify",
        "previous song on spotify",
        "spotify volume",
        "what song is playing",
        "what is playing on spotify",
        "now playing on spotify",
        "spotify playlists",
        "my spotify playlists",
        "spotify queue",
        "spotify devices",
        "authenticate spotify",
        "connect spotify",
    ],
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "search_play | play | pause | resume | next | previous | set_volume | volume_up | volume_down | get_now_playing | get_playlists | get_queue | get_devices | auth",
            },
            "query": {
                "type": "STRING",
                "description": "Song, artist, album, or playlist name to search and play",
            },
            "volume": {
                "type": "NUMBER",
                "description": "Volume percentage (0-100)",
            },
        },
    },
    "version": "1.0.0",
    "active": True,
}


def execute(**kwargs) -> Dict[str, Any]:
    """Executes Spotify MCP action and returns a formatted result."""
    # Determine action from parameters or kwargs
    action = kwargs.get("action", "search_play")
    query = kwargs.get("query", "")
    volume = kwargs.get("volume")

    # If action is search_play but no query is given in kwargs, check if query was passed under another key
    if not query:
        for k in ("song", "track", "music", "title", "artist"):
            if k in kwargs and kwargs[k]:
                query = kwargs[k]
                break

    params = {
        "action": action,
        "query": query,
    }
    if volume is not None:
        params["volume"] = volume

    result_text = spotify_mcp_controller(parameters=params)

    return {
        "title": "Spotify MCP Controller",
        "summary": result_text,
        "spoken_narrative": result_text,
        "configured": is_spotify_configured(),
    }
