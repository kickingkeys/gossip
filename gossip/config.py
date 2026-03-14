"""Load and provide access to gossip configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


def _project_root() -> Path:
    """Return the project root directory (where gossip.yaml lives)."""
    return Path(__file__).resolve().parent.parent


@dataclass
class BotConfig:
    name: str = "gossipbot"
    personality: str = "messy_gossip_queen"


@dataclass
class GroupConfig:
    name: str = "the group"


@dataclass
class GossipConfig:
    inactivity_threshold_hours: float = 3.0
    check_interval_minutes: int = 30
    quiet_hours_start: int = 23
    quiet_hours_end: int = 9
    history_context_limit: int = 20
    chat_history_days: int = 2
    dossier_max_chars: int = 500


@dataclass
class DataConfig:
    db_path: str = "data/gossip.db"
    dossiers_dir: str = "data/dossiers"
    chat_dir: str = "data/chat"
    group_dynamics: str = "data/group.md"


@dataclass
class SourcesConfig:
    sync_interval_minutes: int = 30
    calendar_enabled: bool = True
    gmail_enabled: bool = False
    instagram_enabled: bool = False
    twitter_enabled: bool = False


@dataclass
class PortalConfig:
    host: str = "0.0.0.0"
    port: int = 3000


@dataclass
class Config:
    bot: BotConfig = field(default_factory=BotConfig)
    group: GroupConfig = field(default_factory=GroupConfig)
    gossip: GossipConfig = field(default_factory=GossipConfig)
    data: DataConfig = field(default_factory=DataConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    portal: PortalConfig = field(default_factory=PortalConfig)
    project_root: Path = field(default_factory=_project_root)

    def resolve_path(self, relative: str) -> Path:
        """Resolve a relative path against the project root."""
        return self.project_root / relative

    @property
    def db_path(self) -> Path:
        return self.resolve_path(self.data.db_path)

    @property
    def dossiers_dir(self) -> Path:
        return self.resolve_path(self.data.dossiers_dir)

    @property
    def chat_dir(self) -> Path:
        return self.resolve_path(self.data.chat_dir)

    @property
    def group_dynamics_path(self) -> Path:
        return self.resolve_path(self.data.group_dynamics)


_config: Config | None = None


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from gossip.yaml and environment."""
    global _config
    if _config is not None:
        return _config

    root = _project_root()

    # Load .env from config/ directory
    env_path = root / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Load gossip.yaml
    if config_path is None:
        config_path = root / "gossip.yaml"
    else:
        config_path = Path(config_path)

    raw: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

    cfg = Config(project_root=root)

    # Map YAML sections to dataclass fields
    if "bot" in raw:
        cfg.bot = BotConfig(**{k: v for k, v in raw["bot"].items() if k in BotConfig.__dataclass_fields__})
    if "group" in raw:
        cfg.group = GroupConfig(**{k: v for k, v in raw["group"].items() if k in GroupConfig.__dataclass_fields__})
    if "gossip" in raw:
        cfg.gossip = GossipConfig(**{k: v for k, v in raw["gossip"].items() if k in GossipConfig.__dataclass_fields__})
    if "data" in raw:
        cfg.data = DataConfig(**{k: v for k, v in raw["data"].items() if k in DataConfig.__dataclass_fields__})
    if "sources" in raw:
        cfg.sources = SourcesConfig(**{k: v for k, v in raw["sources"].items() if k in SourcesConfig.__dataclass_fields__})
    if "portal" in raw:
        cfg.portal = PortalConfig(**{k: v for k, v in raw["portal"].items() if k in PortalConfig.__dataclass_fields__})

    _config = cfg
    return cfg


def get_config() -> Config:
    """Get the loaded config, loading it if necessary."""
    return load_config()
