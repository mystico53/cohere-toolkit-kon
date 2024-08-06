from typing import ClassVar, Dict, List, Optional, Union

from pydantic import BaseModel

from backend.database_models import Group as DBGroup
from backend.database_models import User as DBUser


class Meta(BaseModel):
    resourceType: str
    created: str
    lastModified: str


class Name(BaseModel):
    givenName: str
    familyName: str


class BaseUser(BaseModel):
    userName: str
    active: bool

    schemas: list[str]


class GroupMember(BaseModel):
    value: str
    display: str


class BaseGroup(BaseModel):
    schemas: list[str]
    members: list[GroupMember]
    displayName: str


class CreateGroup(BaseGroup):
    pass


class Email(BaseModel):
    primary: bool
    value: str
    type: str


class CreateUser(BaseUser):
    name: Name
    emails: Optional[List[Email]] = None
    externalId: str


class UpdateUser(BaseUser):
    emails: Optional[List[Email]] = None
    name: Name


class Operation(BaseModel):
    op: str
    value: dict[str, bool]


class GroupOperation(BaseModel):
    op: str
    path: Optional[str] = None
    value: Union[Dict[str, str], list[Dict[str, str]]]


class PatchUser(BaseModel):
    schemas: list[str]
    Operations: list[Operation]


class PatchGroup(BaseModel):
    schemas: list[str]
    Operations: list[GroupOperation]


class Group(BaseGroup):
    id: str
    displayName: str
    meta: Meta

    @staticmethod
    def from_db_group(db_group: DBGroup) -> "Group":
        return Group(
            id=db_group.id,
            displayName=db_group.display_name,
            members=[
                GroupMember(value=ua.user_id, display=ua.display)
                for ua in db_group.user_associations
            ],
            meta=Meta(
                resourceType="Group",
                created=db_group.created_at.isoformat(),
                lastModified=db_group.updated_at.isoformat(),
            ),
            schemas=["urn:ietf:params:scim:schemas:core:2.0:Group"],
        )


class User(BaseUser):
    id: str
    externalId: str
    meta: Meta

    @staticmethod
    def from_db_user(db_user: DBUser) -> "User":
        return User(
            id=db_user.id,
            userName=db_user.user_name,
            active=db_user.active,
            externalId=db_user.external_id,
            meta=Meta(
                resourceType="User",
                created=db_user.created_at.isoformat(),
                lastModified=db_user.updated_at.isoformat(),
            ),
            schemas=["urn:ietf:params:scim:schemas:core:2.0:User"],
        )


class BaseListResponse(BaseModel):
    schemas: ClassVar[list[str]] = [
        "urn:ietf:params:scim:api:messages:2.0:ListResponse"
    ]
    totalResults: int
    startIndex: int
    itemsPerPage: int


class ListUserResponse(BaseListResponse):
    Resources: list[User]


class ListGroupResponse(BaseListResponse):
    Resources: list[Group]
