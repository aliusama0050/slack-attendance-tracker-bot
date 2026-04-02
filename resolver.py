import logging
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1 hour


class SlackUserResolver:
    """Resolves Slack user IDs and Jibble first names to canonical full names."""

    def __init__(self, token: str):
        self.client = WebClient(token=token)
        self._user_cache: dict[str, str] = {}  # user_id -> canonical name
        self._workspace_users: list[dict] = []
        self._name_lookup: dict[str, str] = {}  # lowercase variant -> canonical name
        self._cache_timestamp: float = 0

    def _canonical_name(self, user: dict) -> str:
        """Extract canonical name from Slack user object.
        Priority: display_name > real_name > username.
        """
        profile = user.get("profile", {})
        display = profile.get("display_name", "").strip()
        if display:
            return display
        real = profile.get("real_name", "").strip() or user.get("real_name", "").strip()
        if real:
            return real
        return user.get("name", "unknown")

    def _should_skip_user(self, user: dict) -> bool:
        """Check if user should be excluded from resolution."""
        return (
            user.get("deleted", False)
            or user.get("is_bot", False)
            or user.get("is_workflow_bot", False)
            or user.get("id") == "USLACKBOT"
        )

    def _refresh_cache_if_needed(self) -> None:
        """Fetch workspace user list if cache is stale (>1 hour old)."""
        if time.time() - self._cache_timestamp < CACHE_TTL and self._workspace_users:
            return

        logger.info("Refreshing Slack workspace user cache")
        users = []
        cursor = None

        try:
            while True:
                resp = self.client.users_list(cursor=cursor, limit=200)
                members = resp.get("members", [])
                users.extend(members)
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
        except SlackApiError:
            logger.exception("Failed to fetch Slack users list")
            return

        self._workspace_users = [u for u in users if not self._should_skip_user(u)]
        self._cache_timestamp = time.time()

        # Build lookup map: every name variant -> canonical name
        self._name_lookup.clear()
        for user in self._workspace_users:
            canonical = self._canonical_name(user)
            profile = user.get("profile", {})

            variants = [
                canonical,
                profile.get("display_name", ""),
                profile.get("real_name", ""),
                user.get("real_name", ""),
                user.get("name", ""),
                profile.get("first_name", ""),
                profile.get("last_name", ""),
            ]
            # Add all individual name parts from real_name
            real = profile.get("real_name", "") or user.get("real_name", "")
            if real:
                for part in real.split():
                    variants.append(part)

            for v in variants:
                v = v.strip()
                if v:
                    self._name_lookup[v.lower()] = canonical

        logger.info("Cached %d workspace users with %d name variants",
                     len(self._workspace_users), len(self._name_lookup))

    def resolve_user_id(self, user_id: str) -> str | None:
        """Resolve a Slack user_id to canonical name via users.info API."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            resp = self.client.users_info(user=user_id)
            user = resp.get("user", {})
        except SlackApiError:
            logger.exception("Failed to fetch user info for %s", user_id)
            return None

        if self._should_skip_user(user):
            return None

        name = self._canonical_name(user)
        self._user_cache[user_id] = name
        return name

    def resolve_jibble_name(self, first_name: str) -> str | None:
        """Match a Jibble first name against workspace users.

        Searches display_name, real_name, and first_name fields
        for a case-insensitive match.
        """
        self._refresh_cache_if_needed()

        key = first_name.strip().lower()
        if key in self._name_lookup:
            return self._name_lookup[key]

        # Fallback: prefix match on real_name
        for user in self._workspace_users:
            profile = user.get("profile", {})
            real = profile.get("real_name", "") or user.get("real_name", "")
            if real.lower().startswith(key):
                canonical = self._canonical_name(user)
                self._name_lookup[key] = canonical
                return canonical

        logger.warning("Could not resolve Jibble name: %s", first_name)
        return None
