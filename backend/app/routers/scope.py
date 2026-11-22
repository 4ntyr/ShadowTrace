"""The `scope` query parameter: everything, or only the user's favourite groups."""

from enum import Enum

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Favourite, User
from ..security import current_user_optional


class Scope(str, Enum):
    all = "all"
    favourites = "favourites"


class ScopeCtx:
    def __init__(self, scope: Scope, user: User | None, favourite_ids: set[int]):
        self.scope, self.user, self.favourite_ids = scope, user, favourite_ids

    @property
    def restrict(self) -> set[int] | None:
        """Group ids to restrict to, or None for no restriction."""
        return self.favourite_ids if self.scope == Scope.favourites else None


def scope_ctx(
    scope: Scope = Query(Scope.all),
    user: User | None = Depends(current_user_optional),
    db: Session = Depends(get_db),
) -> ScopeCtx:
    fav = set()
    if user is not None:
        fav = set(db.scalars(select(Favourite.group_id).where(Favourite.user_id == user.id)))
    if scope == Scope.favourites and user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login to use favourites")
    return ScopeCtx(scope, user, fav)
