from anyio import to_thread
from fastmcp.server.auth import AccessToken, TokenVerifier
from sqlalchemy import select

from app.auth.security import hash_token
from app.db import new_session
from app.models import ApiToken


class ApiTokenVerifier(TokenVerifier):
    """Accept Plantasaurus API tokens (`pts_…`, created under Settings → API tokens)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return await to_thread.run_sync(self._verify, token)

    def _verify(self, token: str) -> AccessToken | None:
        with new_session() as db:
            api_token = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(token.strip())))
            if api_token is None or api_token.revoked_at is not None or not api_token.user.is_active:
                return None
            return AccessToken(
                token=token.strip(),
                client_id=f"api-token:{api_token.id}",
                subject=str(api_token.user_id),
                scopes=[],
            )
